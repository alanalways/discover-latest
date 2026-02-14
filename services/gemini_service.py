"""Gemini AI service with two-stage generation and timeout-safe fallback."""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from typing import Any, Dict, List, Optional

from config.models import MODEL_FINAL, MODEL_GROUNDING

GEMINI_TIMEOUT_STAGE1 = int(os.environ.get("GEMINI_TIMEOUT_STAGE1", "30"))
GEMINI_TIMEOUT_STAGE2 = int(os.environ.get("GEMINI_TIMEOUT_STAGE2", "45"))
GEMINI_MAX_CONCURRENT = max(1, int(os.environ.get("GEMINI_MAX_CONCURRENT", "2")))
GEMINI_ANALYSIS_CACHE_TTL_SEC = max(0, int(os.environ.get("GEMINI_ANALYSIS_CACHE_TTL_SEC", "300")))

_key_pool: List[str] = []
_key_index = 0
_key_lock = threading.Lock()

_metrics_cache: Dict[str, Dict[str, Any]] = {}
_metrics_cache_lock = threading.Lock()
_analysis_cache: Dict[str, Dict[str, Any]] = {}
_analysis_cache_lock = threading.Lock()


def _load_key_pool() -> List[str]:
    global _key_pool
    if _key_pool:
        return _key_pool

    multi_keys = os.environ.get("GEMINI_API_KEYS", "")
    if multi_keys:
        keys = [k.strip() for k in multi_keys.split(",") if k.strip()]
        if keys:
            _key_pool = keys
            print(f"[Gemini] Loaded {len(keys)} API keys from GEMINI_API_KEYS")
            return _key_pool

    single = os.environ.get("GEMINI_API_KEY", "").strip()
    if single:
        _key_pool = [single]
        print("[Gemini] Loaded 1 API key from GEMINI_API_KEY")
        return _key_pool

    try:
        from adapters.supabase_adapter import supabase_adapter

        vault_keys = supabase_adapter.get_gemini_keys()
        if vault_keys:
            _key_pool = [k for k in vault_keys if isinstance(k, str) and k.strip()]
            if _key_pool:
                print(f"[Gemini] Loaded {len(_key_pool)} API keys from Supabase Vault")
                return _key_pool
    except Exception:
        pass

    print("[Gemini] No API keys found")
    return []


def _get_next_key() -> str:
    global _key_index
    pool = _load_key_pool()
    if not pool:
        return ""
    with _key_lock:
        key = pool[_key_index % len(pool)]
        _key_index += 1
    return key


class GeminiService:
    def __init__(self):
        self._generate_slots = threading.Semaphore(GEMINI_MAX_CONCURRENT)

    def _get_api_key(self) -> str:
        return _get_next_key()

    def is_available(self) -> bool:
        return bool(_load_key_pool())

    @staticmethod
    def _safe_float(value: Any) -> Optional[float]:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            v = float(value)
            return v if v == v and v not in (float("inf"), float("-inf")) else None
        text = str(value).strip().replace(",", "")
        if not text:
            return None
        if text.endswith("%"):
            text = text[:-1].strip()
        units = {"K": 1e3, "M": 1e6, "B": 1e9, "T": 1e12}
        mul = units.get(text[-1:].upper())
        if mul:
            text = text[:-1].strip()
        try:
            base = float(text)
            v = base * mul if mul else base
            return v if v == v and v not in (float("inf"), float("-inf")) else None
        except Exception:
            return None

    @staticmethod
    def _extract_json_object(text: str) -> Dict[str, Any]:
        if not text:
            return {}
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
            cleaned = re.sub(r"\s*```$", "", cleaned)
        try:
            parsed = json.loads(cleaned)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            pass
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start >= 0 and end > start:
            snippet = cleaned[start : end + 1]
            try:
                parsed = json.loads(snippet)
                return parsed if isinstance(parsed, dict) else {}
            except Exception:
                return {}
        return {}

    def ground_company_metrics(self, symbol: str, market: str = "TW", company_name: str = "") -> Dict[str, Any]:
        normalized_symbol = str(symbol or "").strip().upper()
        cache_key = f"{time.strftime('%Y-%m-%d')}:{normalized_symbol}"
        with _metrics_cache_lock:
            cached = _metrics_cache.get(cache_key)
            if isinstance(cached, dict):
                return cached

        api_key = self._get_api_key()
        if not api_key:
            return {"success": False, "metrics": {}, "sources": [], "error": "no_api_key"}

        try:
            from google import genai
            from google.genai import types
        except Exception:
            return {"success": False, "metrics": {}, "sources": [], "error": "google_genai_missing"}

        prompt = (
            "Use Google Search grounding and return JSON only. "
            '{"market_cap": number|null, "pe_ratio": number|null, "pb_ratio": number|null, '
            '"dividend_yield": number|null, "as_of": string|null}. '
            "market_cap must be absolute number, dividend_yield is percentage number. "
            f"symbol={normalized_symbol}, market={market}, company={company_name or normalized_symbol}."
        )

        def _run():
            client = genai.Client(api_key=api_key)
            return client.models.generate_content(
                model=MODEL_GROUNDING,
                contents=prompt,
                config=types.GenerateContentConfig(
                    tools=[types.Tool(google_search=types.GoogleSearch())]
                ),
            )

        sources: List[Dict[str, str]] = []
        response = None
        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(_run)
        try:
            response = future.result(timeout=16)
        except FuturesTimeoutError:
            future.cancel()
            return {"success": False, "metrics": {}, "sources": [], "error": "grounding_timeout"}
        except Exception as e:
            return {"success": False, "metrics": {}, "sources": [], "error": type(e).__name__}
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

        text_out = response.text if response and getattr(response, "text", None) else ""
        candidates = getattr(response, "candidates", None) or []
        if candidates:
            gm = getattr(candidates[0], "grounding_metadata", None)
            chunks = getattr(gm, "grounding_chunks", None) if gm else None
            for chunk in (chunks or []):
                web = getattr(chunk, "web", None)
                if web:
                    sources.append(
                        {
                            "title": str(getattr(web, "title", "") or ""),
                            "uri": str(getattr(web, "uri", "") or ""),
                        }
                    )

        parsed = self._extract_json_object(text_out)
        metrics = {
            "market_cap": self._safe_float(parsed.get("market_cap")),
            "pe_ratio": self._safe_float(parsed.get("pe_ratio")),
            "pb_ratio": self._safe_float(parsed.get("pb_ratio")),
            "dividend_yield": self._safe_float(parsed.get("dividend_yield")),
            "as_of": parsed.get("as_of"),
        }
        result = {"success": True, "metrics": metrics, "sources": sources[:8]}
        with _metrics_cache_lock:
            _metrics_cache[cache_key] = result
        return result

    def _build_context(
        self,
        symbol: str,
        stock_info: Optional[Dict[str, Any]],
        smc_summary: str,
        prediction_summary: str,
        macro_data: Optional[Dict[str, Any]],
    ) -> str:
        parts: List[str] = []
        if stock_info:
            name = stock_info.get("name", symbol)
            price = stock_info.get("price", 0)
            chg = stock_info.get("change_percent", 0)
            parts.append(f"Symbol: {symbol} ({name}), Price: {price}, Change: {chg}%")
            parts.append(
                "Valuation: "
                f"PE={stock_info.get('pe_ratio')}, PB={stock_info.get('pb_ratio')}, "
                f"DividendYield={stock_info.get('dividend_yield')}, MarketCap={stock_info.get('market_cap')}"
            )
        if smc_summary:
            parts.append(f"SMC: {smc_summary}")
        if prediction_summary:
            parts.append(f"Technical Snapshot: {prediction_summary}")
        if macro_data:
            score = macro_data.get("score")
            light = macro_data.get("light")
            date = macro_data.get("date")
            parts.append(f"Macro ({date}): score={score}, regime={light}")
        return "\n".join(parts)

    @staticmethod
    def _analysis_cache_key(
        symbol: str,
        tier: str,
        context: str,
        user_question: str,
    ) -> str:
        raw = "|".join(
            [
                str(symbol or "").strip().upper(),
                str(tier or "free").strip().lower(),
                str(user_question or "").strip(),
                str(context or "").strip(),
            ]
        )
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        return f"{time.strftime('%Y-%m-%d')}:{digest}"

    def _read_analysis_cache(self, key: str) -> Optional[Dict[str, Any]]:
        if GEMINI_ANALYSIS_CACHE_TTL_SEC <= 0:
            return None
        now = time.time()
        with _analysis_cache_lock:
            row = _analysis_cache.get(key)
            if not isinstance(row, dict):
                return None
            ts = float(row.get("ts") or 0.0)
            if ts <= 0 or (now - ts) > GEMINI_ANALYSIS_CACHE_TTL_SEC:
                _analysis_cache.pop(key, None)
                return None
            payload = row.get("payload")
            if isinstance(payload, dict):
                return dict(payload)
            return None

    def _write_analysis_cache(self, key: str, payload: Dict[str, Any]) -> None:
        if GEMINI_ANALYSIS_CACHE_TTL_SEC <= 0:
            return
        with _analysis_cache_lock:
            _analysis_cache[key] = {"ts": time.time(), "payload": dict(payload)}

    @staticmethod
    def _tier_instructions(tier: str) -> str:
        base = (
            "請用繁體中文輸出，文風專業、精簡但完整，避免空泛。\n"
            "每段先講結論再講理由，並適度加入 emoji 幫助快速閱讀（不要過量）。\n"
            "若資料不足，明確寫出『資料不足』與替代判讀方式。\n"
            "第一行固定寫：我是 DiscoverLatest AI。\n"
            "不要使用問候語，不要寫『你好』。\n"
            "禁止使用這些符號與格式：---、***、**、##。\n"
            "列點只使用「• 」字元。"
        )
        tier_norm = str(tier or "free").strip().lower()
        if tier_norm == "premium":
            return (
                base
                + "\nPremium 層級要求：提供完整結構（行情結論、關鍵驅動、風險情境、交易計畫、觀察清單），"
                "給出進出區間與倉位分配建議（保守/中性/積極三檔）。"
            )
        if tier_norm == "pro":
            return (
                base
                + "\nPro 層級要求：提供中等深度（行情結論、2-3 個關鍵驅動、主要風險、操作策略），"
                "含短中期兩種節奏建議。"
            )
        return (
            base
            + "\nFree 層級要求：聚焦最重要的結論、風險與一個可執行策略，"
            "保持短版但具體，保留升級可見差異。"
        )

    @staticmethod
    def _build_fallback_from_grounding(symbol: str, grounding_text: str, tier: str) -> str:
        text = (grounding_text or "").strip()
        if not text:
            return ""
        tier_hint = {
            "free": "目前先提供快版重點，升級可解鎖更完整策略拆解。",
            "pro": "目前先提供快版重點，稍後可補更完整情境推演。",
            "premium": "目前先提供快版重點，稍後可補完整高階策略版。",
        }.get(str(tier or "free").lower(), "目前先提供快版重點。")
        return (
            f"⚡ {symbol} 即時分析（降級模式）\n"
            "由於深度整理階段逾時，先提供可用重點：\n\n"
            f"{text}\n\n"
            f"🧭 補充：{tier_hint}"
        )

    def _background_retry_stage2(self, symbol: str, final_prompt: str) -> None:
        def _task():
            try:
                key = self._get_api_key()
                if not key:
                    return
                from google import genai

                client = genai.Client(api_key=key)
                response = client.models.generate_content(
                    model=MODEL_FINAL,
                    contents=final_prompt,
                )
                text = (getattr(response, "text", "") or "").strip()
                if text:
                    print(f"[Gemini] Background retry completed for {symbol}, {len(text)} chars")
                else:
                    print(f"[Gemini] Background retry completed for {symbol}, empty output")
            except Exception as e:
                print(f"[Gemini] Background retry failed for {symbol}: {type(e).__name__}: {e}")

        threading.Thread(target=_task, daemon=True).start()

    def generate_analysis(
        self,
        symbol: str,
        stock_info: Dict = None,
        smc_summary: str = "",
        prediction_summary: str = "",
        macro_data: Dict = None,
        user_question: str = "",
        tier: str = "free",
    ) -> Dict[str, Any]:
        api_key = self._get_api_key()
        if not api_key:
            return {"success": False, "error": "Gemini API key missing", "analysis": "", "grounding_sources": []}

        try:
            from google import genai
            from google.genai import types
        except Exception:
            return {"success": False, "error": "google-genai missing", "analysis": "", "grounding_sources": []}

        with self._generate_slots:
            t0 = time.time()
            context = self._build_context(symbol, stock_info, smc_summary, prediction_summary, macro_data)
            cache_key = self._analysis_cache_key(symbol, tier, context, user_question)
            cached = self._read_analysis_cache(cache_key)
            if cached:
                cached_payload = dict(cached)
                cached_payload["cached"] = True
                return cached_payload
            client = genai.Client(api_key=api_key)

            grounding_prompt = (
                "你是金融研究助理。請先蒐集最新可驗證市場資訊，使用繁體中文輸出 4-6 點條列。\n"
                "每點格式：事件 / 對股價可能影響 / 時間性（短中長）。\n"
                f"symbol={symbol}\n{context}\n"
                f"{('user_question=' + user_question) if user_question else ''}"
            )

            def _run_stage1():
                try:
                    return client.models.generate_content(
                        model=MODEL_GROUNDING,
                        contents=grounding_prompt,
                        config=types.GenerateContentConfig(
                            tools=[types.Tool(google_search=types.GoogleSearch())]
                        ),
                    )
                except Exception:
                    return client.models.generate_content(
                        model=MODEL_GROUNDING,
                        contents=grounding_prompt,
                    )

            stage1_started = time.time()
            grounding_text = ""
            grounding_sources: List[Dict[str, str]] = []
            print(f"[Gemini] Stage 1 starting for {symbol}...")

            executor1 = ThreadPoolExecutor(max_workers=1)
            future1 = executor1.submit(_run_stage1)
            stage1_timeout = False
            try:
                stage1_response = future1.result(timeout=GEMINI_TIMEOUT_STAGE1)
                grounding_text = (
                    stage1_response.text.strip()
                    if stage1_response and getattr(stage1_response, "text", None)
                    else ""
                )
                print(f"[Gemini] Stage 1 completed for {symbol} in {time.time() - stage1_started:.1f}s")

                candidates = getattr(stage1_response, "candidates", None) or []
                if candidates:
                    gm = getattr(candidates[0], "grounding_metadata", None)
                    chunks = getattr(gm, "grounding_chunks", None) if gm else None
                    for chunk in (chunks or []):
                        web = getattr(chunk, "web", None)
                        if web:
                            grounding_sources.append(
                                {
                                    "title": str(getattr(web, "title", "") or ""),
                                    "uri": str(getattr(web, "uri", "") or ""),
                                }
                            )
            except FuturesTimeoutError:
                future1.cancel()
                grounding_text = "Grounding timeout, fallback to local context."
                stage1_timeout = True
                print(f"[Gemini] Stage 1 TIMEOUT after {GEMINI_TIMEOUT_STAGE1}s")
            except Exception as e:
                grounding_text = "Grounding failed, fallback to local context."
                print(f"[Gemini] Stage 1 error: {type(e).__name__}: {e}")
            finally:
                executor1.shutdown(wait=False, cancel_futures=True)

            stage1_ms = int((time.time() - stage1_started) * 1000)
            tier_instruction = self._tier_instructions(tier)
            max_tokens = 700 if str(tier).lower() == "free" else (900 if str(tier).lower() == "pro" else 1150)
            grounding_compact = (grounding_text or "").strip()
            if len(grounding_compact) > 2200:
                grounding_compact = grounding_compact[:2200] + "\n（以下略）"
            final_prompt = (
                "你是資深投資研究助理。請根據 context 與 grounding 產出可執行分析。\n"
                f"{tier_instruction}\n\n"
                f"symbol={symbol}\n"
                f"context:\n{context}\n\n"
                f"grounding:\n{grounding_compact}\n\n"
                "請固定輸出以下章節：\n"
                "1) 📌 核心結論\n"
                "2) 🔍 關鍵驅動（2-4 點）\n"
                "3) ⚠️ 主要風險\n"
                "4) 🎯 操作建議（含停損/觀察條件）\n"
                "5) 📅 接下來要追蹤的事件\n"
            )

            print(f"[Gemini] Stage 2 starting for {symbol}...")

            def _run_stage2():
                last_err: Optional[Exception] = None
                for attempt in range(3):
                    try:
                        key2 = self._get_api_key() or api_key
                        c2 = genai.Client(api_key=key2)
                        return c2.models.generate_content(
                            model=MODEL_FINAL,
                            contents=final_prompt,
                            config=types.GenerateContentConfig(
                                temperature=0.35,
                                max_output_tokens=max_tokens,
                            ),
                        )
                    except Exception as e:
                        last_err = e
                        msg = str(e).lower()
                        if ("503" in msg or "unavailable" in msg or "overloaded" in msg) and attempt < 2:
                            time.sleep(1.1 * (attempt + 1))
                            continue
                        raise
                if last_err:
                    raise last_err
                raise RuntimeError("stage2_failed")

            stage2_started = time.time()
            executor2 = ThreadPoolExecutor(max_workers=1)
            future2 = executor2.submit(_run_stage2)
            try:
                stage2_response = future2.result(timeout=GEMINI_TIMEOUT_STAGE2)
                analysis = (
                    stage2_response.text.strip()
                    if stage2_response and getattr(stage2_response, "text", None)
                    else ""
                )
                if not analysis:
                    return {
                        "success": False,
                        "error": "empty_stage2_output",
                        "analysis": "",
                        "grounding_sources": grounding_sources,
                        "timings": {
                            "stage1_ms": stage1_ms,
                            "stage2_ms": int((time.time() - stage2_started) * 1000),
                            "total_ms": int((time.time() - t0) * 1000),
                        },
                    }
                print(f"[Gemini] Stage 2 completed for {symbol}, {len(analysis)} chars")
                payload = {
                    "success": True,
                    "analysis": analysis,
                    "grounding_sources": grounding_sources,
                    "model_used": MODEL_FINAL,
                    "grounding_model": MODEL_GROUNDING,
                    "error": None,
                    "timings": {
                        "stage1_ms": stage1_ms,
                        "stage2_ms": int((time.time() - stage2_started) * 1000),
                        "total_ms": int((time.time() - t0) * 1000),
                        "stage1_timeout": stage1_timeout,
                    },
                }
                self._write_analysis_cache(cache_key, payload)
                return payload
            except FuturesTimeoutError:
                future2.cancel()
                print(f"[Gemini] Stage 2 TIMEOUT after {GEMINI_TIMEOUT_STAGE2}s")
                fallback = self._build_fallback_from_grounding(symbol, grounding_text, tier)
                if fallback:
                    self._background_retry_stage2(symbol, final_prompt)
                payload = {
                    "success": bool(fallback),
                    "degraded": bool(fallback),
                    "error": f"stage2_timeout_{GEMINI_TIMEOUT_STAGE2}s",
                    "analysis": fallback,
                    "grounding_text": grounding_text,
                    "grounding_sources": grounding_sources,
                    "timings": {
                        "stage1_ms": stage1_ms,
                        "stage2_ms": int((time.time() - stage2_started) * 1000),
                        "total_ms": int((time.time() - t0) * 1000),
                        "stage2_timeout": True,
                    },
                }
                if fallback:
                    self._write_analysis_cache(cache_key, payload)
                return payload
            except Exception as e:
                print(f"[Gemini] Stage 2 error: {e}")
                traceback.print_exc()
                return {
                    "success": False,
                    "error": f"stage2_error_{type(e).__name__}",
                    "analysis": "",
                    "grounding_sources": grounding_sources,
                    "timings": {
                        "stage1_ms": stage1_ms,
                        "stage2_ms": int((time.time() - stage2_started) * 1000),
                        "total_ms": int((time.time() - t0) * 1000),
                    },
                }
            finally:
                executor2.shutdown(wait=False, cancel_futures=True)

    def generate_chat_response(
        self,
        history: List[Dict],
        user_message: str,
        context_str: str = "",
        tier: str = "free",
    ) -> Dict[str, Any]:
        api_key = self._get_api_key()
        if not api_key:
            return {"success": False, "error": "Gemini API key missing"}
        if tier == "free":
            return {"success": False, "error": "Free plan does not support follow-up chat"}

        try:
            from google import genai
        except Exception:
            return {"success": False, "error": "google-genai missing"}

        max_turns = 10 if tier == "premium" else 3
        active_history = history[-(max_turns * 2) :] if history else []
        rendered_history = []
        for item in active_history:
            role = str(item.get("role", "user"))
            parts = item.get("parts") or []
            text = ""
            if isinstance(parts, list):
                text = " ".join(str(p) for p in parts)
            rendered_history.append(f"{role}: {text}")

        prompt = (
            "你是 DiscoverLatest 的投資分析助理。\n"
            f"Context:\n{context_str}\n\n"
            f"History:\n{chr(10).join(rendered_history)}\n\n"
            f"User: {user_message}\n"
            "請用繁體中文、專業精簡回覆。"
        )

        try:
            client = genai.Client(api_key=api_key)
            response = client.models.generate_content(model=MODEL_FINAL, contents=prompt)
            reply = (getattr(response, "text", "") or "").strip()
            if not reply:
                return {"success": False, "error": "empty_chat_output"}
            return {"success": True, "reply": reply}
        except Exception as e:
            print(f"[Gemini] Chat error: {e}")
            return {"success": False, "error": str(e)}


gemini_service = GeminiService()
