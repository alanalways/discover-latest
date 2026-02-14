"""Gemini AI service with stage1 grounding + stage2 synthesis."""

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
GEMINI_REPAIR_TIMEOUT_SEC = max(6, int(os.environ.get("GEMINI_REPAIR_TIMEOUT_SEC", "18")))

INTRO_LINE = "\u6211\u662f DiscoverLatest AI\u3002"
S1 = "\u4e00\u3001\u5e02\u5834\u60c5\u5883\u8207\u7d50\u8ad6 \U0001F50E"
S2 = "\u4e8c\u3001\u95dc\u9375\u50ac\u5316\u8207\u57fa\u672c\u9762 \U0001F9F1"
S3 = "\u4e09\u3001\u4ea4\u6613\u7b56\u7565\u8207\u57f7\u884c \U0001F9ED"
S4 = "\u56db\u3001\u98a8\u96aa\u8207\u5931\u6548\u689d\u4ef6 \u26A0\uFE0F"
S5 = "\u4e94\u3001\u63a5\u4e0b\u4f86\u8981\u8ffd\u8e64\u7684\u4e8b\u4ef6 \U0001F4C5"
SMC_HEADER = "SMC \u7d50\u69cb\u5224\u8b80 \U0001F9E0"

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

    multi = os.environ.get("GEMINI_API_KEYS", "")
    if multi:
        keys = [k.strip() for k in multi.split(",") if k.strip()]
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
            "Use Google Search grounding and return strict JSON only. "
            '{"market_cap": number|null, "pe_ratio": number|null, "pb_ratio": number|null, '
            '"dividend_yield": number|null, "as_of": string|null}. '
            "market_cap must be absolute numeric value. dividend_yield is percentage numeric value. "
            f"symbol={normalized_symbol}, market={market}, company={company_name or normalized_symbol}."
        )

        def _run():
            client = genai.Client(api_key=api_key)
            return client.models.generate_content(
                model=MODEL_GROUNDING,
                contents=prompt,
                config=types.GenerateContentConfig(
                    tools=[types.Tool(google_search=types.GoogleSearch())],
                    temperature=0.1,
                    max_output_tokens=240,
                ),
            )

        sources: List[Dict[str, str]] = []
        ex = ThreadPoolExecutor(max_workers=1)
        f = ex.submit(_run)
        try:
            response = f.result(timeout=16)
        except FuturesTimeoutError:
            f.cancel()
            return {"success": False, "metrics": {}, "sources": [], "error": "grounding_timeout"}
        except Exception as e:
            return {"success": False, "metrics": {}, "sources": [], "error": type(e).__name__}
        finally:
            ex.shutdown(wait=False, cancel_futures=True)

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
            parts.append(f"Symbol={symbol} Name={stock_info.get('name', symbol)}")
            parts.append(
                "Snapshot="
                f"Price:{stock_info.get('price')},"
                f"ChangePct:{stock_info.get('change_percent')},"
                f"PE:{stock_info.get('pe_ratio')},"
                f"PB:{stock_info.get('pb_ratio')},"
                f"DY:{stock_info.get('dividend_yield')},"
                f"MarketCap:{stock_info.get('market_cap')}"
            )
        if prediction_summary:
            parts.append(f"Technical={prediction_summary}")
        if smc_summary:
            parts.append(f"SMC={smc_summary}")
        if macro_data:
            parts.append(f"Macro={macro_data}")
        return "\n".join(parts)

    @staticmethod
    def _sanitize_analysis_text(text: str) -> str:
        out = (text or "").replace("\r\n", "\n").strip()
        if not out:
            return ""

        out = re.sub(r"(?m)^\s*[-*]{3,}\s*$", "", out)
        out = out.replace("***", "").replace("**", "").replace("#", "").replace("`", "")
        out = re.sub(r"(?im)^\s*section\s*1\b.*$", S1, out)
        out = re.sub(r"(?im)^\s*section\s*2\b.*$", S2, out)
        out = re.sub(r"(?im)^\s*section\s*3\b.*$", S3, out)
        out = re.sub(r"(?im)^\s*section\s*4\b.*$", S4, out)
        out = re.sub(r"(?im)^\s*section\s*5\b.*$", S5, out)
        out = re.sub(r"(?im)^\s*section\s*6\b.*$", SMC_HEADER, out)

        lines: List[str] = []
        for raw in out.split("\n"):
            line = raw.strip()
            if not line:
                lines.append("")
                continue
            line = re.sub(r"^[-*]+\s*", "", line)
            line = re.sub(r"^\d+\)\s*", "", line)
            line = re.sub(r"^\d+\.\s*", "", line)
            if line.startswith("- "):
                lines.append(line)
            elif re.match(r"^[一二三四五六七八九十]+、", line) or line.startswith("SMC"):
                lines.append(line)
            else:
                lines.append(f"- {line}")

        out = "\n".join(lines)
        out = re.sub(r"\n{3,}", "\n\n", out).strip()
        if not out.startswith(INTRO_LINE):
            out = INTRO_LINE + "\n" + out
        return out.strip()

    @staticmethod
    def _ensure_smc_section(text: str, smc_summary: str) -> str:
        out = (text or "").strip()
        if not out:
            return out
        if re.search(r"(SMC|BOS|CHoCH)", out, flags=re.IGNORECASE):
            return out

        summary = (smc_summary or "").strip() or "Trend=neutral | BOS=0 | CHoCH=0 | ActiveOB=0 | OpenFVG=0 | Liquidity(B/S)=0/0"
        items = [seg.strip() for seg in summary.split("|") if seg.strip()]
        if not items:
            items = ["Trend=neutral", "BOS=0", "CHoCH=0"]
        bullet_lines = "\n".join(f"- {seg}" for seg in items[:6])
        return f"{out}\n\n{SMC_HEADER}\n{bullet_lines}".strip()

    @staticmethod
    def _analysis_cache_key(symbol: str, tier: str, context: str, user_question: str) -> str:
        raw = "|".join(
            [
                str(symbol or "").strip().upper(),
                str(tier or "free").strip().lower(),
                str(user_question or "").strip(),
                str(context or "").strip(),
            ]
        )
        return f"{time.strftime('%Y-%m-%d')}:{hashlib.sha256(raw.encode('utf-8')).hexdigest()}"

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
            return dict(payload) if isinstance(payload, dict) else None

    def _write_analysis_cache(self, key: str, payload: Dict[str, Any]) -> None:
        if GEMINI_ANALYSIS_CACHE_TTL_SEC <= 0:
            return
        with _analysis_cache_lock:
            _analysis_cache[key] = {"ts": time.time(), "payload": dict(payload)}

    @staticmethod
    def _tier_instruction(tier: str) -> str:
        common = (
            "Language: Traditional Chinese only.\n"
            f"First line must be exactly: {INTRO_LINE}\n"
            "Use concise bullet points and a few emoji for readability.\n"
            "Do not use markdown separators or star emphasis such as --- ** *.\n"
            "Must include all six sections and SMC block."
        )
        t = str(tier or "free").strip().lower()
        if t == "premium":
            return common + "\nDepth: Premium. Include scenario probabilities, trigger prices, and portfolio hedging ideas."
        if t == "pro":
            return common + "\nDepth: Pro. Include two scenarios, position sizing hints, and sector-relative view."
        return common + "\nDepth: Free. Keep concise but complete and actionable."

    @staticmethod
    def _quality_ok(text: str, tier: str) -> bool:
        t = (text or "").strip()
        if not t:
            return False

        tier_norm = str(tier or "free").strip().lower()
        min_len = 220 if tier_norm == "free" else (280 if tier_norm == "pro" else 340)
        if len(t) < min_len:
            return False

        required = [
            re.escape(INTRO_LINE),
            r"一、.*市場.*結論",
            r"二、.*催化.*基本面",
            r"三、.*策略.*執行",
            r"四、.*風險.*失效",
            r"五、.*追蹤.*事件",
            r"SMC\s*結構判讀",
        ]
        hits = sum(1 for p in required if re.search(p, t, flags=re.IGNORECASE))
        if hits < 6:
            return False
        if re.search(r"(?im)^\s*section\s*[1-6]\b", t):
            return False
        if "---" in t or "**" in t:
            return False
        return t.count("- ") >= 8

    @staticmethod
    def _build_fallback_from_grounding(symbol: str, grounding_text: str, tier: str) -> str:
        summary = (grounding_text or "").strip() or "No external grounding summary."
        tier_norm = str(tier or "free").lower()

        lines = [
            INTRO_LINE,
            S1,
            f"- {symbol} is evaluated with internal data first; avoid oversized position before structure confirms.",
            S2,
            f"- Grounding notes: {summary}",
            S3,
            "- Use staged entries and wait for price-volume confirmation near key levels.",
            S4,
            "- Invalidate quickly if key support breaks and cannot recover.",
            S5,
            "- Track earnings, guidance, rates, and sector demand updates.",
            SMC_HEADER,
            "- Trend/BOS/CHoCH/OB/FVG/Liquidity are included in this pass.",
        ]
        if tier_norm in {"pro", "premium"}:
            lines.append("- Advanced: monitor divergence between momentum and structure.")
        if tier_norm == "premium":
            lines.append("- Scenario probability: base 50%, bull 30%, bear 20%.")
        return "\n".join(lines)

    def _background_retry_stage2(self, symbol: str, final_prompt: str) -> None:
        def _task() -> None:
            try:
                key = self._get_api_key()
                if not key:
                    return
                from google import genai

                client = genai.Client(api_key=key)
                response = client.models.generate_content(model=MODEL_FINAL, contents=final_prompt)
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
            started = time.time()
            context = self._build_context(symbol, stock_info, smc_summary, prediction_summary, macro_data)
            cache_key = self._analysis_cache_key(symbol, tier, context, user_question)
            cached = self._read_analysis_cache(cache_key)
            if cached and self._quality_ok(str(cached.get("analysis") or ""), tier):
                payload = dict(cached)
                payload["cached"] = True
                return payload

            stage1_timeout = False
            grounding_text = ""
            grounding_sources: List[Dict[str, str]] = []

            stage1_prompt = (
                "You are preparing evidence notes for a stock analyst. "
                "Use Google Search grounding if available. "
                "Return 4-6 concise bullet points in Traditional Chinese. "
                f"symbol={symbol}\n"
                f"context:\n{context}\n"
                f"user_question={user_question or 'N/A'}"
            )

            def _run_stage1():
                client = genai.Client(api_key=self._get_api_key() or api_key)
                try:
                    return client.models.generate_content(
                        model=MODEL_GROUNDING,
                        contents=stage1_prompt,
                        config=types.GenerateContentConfig(
                            tools=[types.Tool(google_search=types.GoogleSearch())],
                            temperature=0.2,
                            max_output_tokens=700,
                        ),
                    )
                except Exception:
                    return client.models.generate_content(
                        model=MODEL_GROUNDING,
                        contents=stage1_prompt,
                        config=types.GenerateContentConfig(temperature=0.2, max_output_tokens=700),
                    )

            print(f"[Gemini] Stage 1 starting for {symbol}...")
            stage1_started = time.time()
            ex1 = ThreadPoolExecutor(max_workers=1)
            f1 = ex1.submit(_run_stage1)
            try:
                stage1_resp = f1.result(timeout=GEMINI_TIMEOUT_STAGE1)
                grounding_text = stage1_resp.text.strip() if stage1_resp and getattr(stage1_resp, "text", None) else ""
                candidates = getattr(stage1_resp, "candidates", None) or []
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
                print(f"[Gemini] Stage 1 completed for {symbol} in {time.time() - stage1_started:.1f}s")
            except FuturesTimeoutError:
                f1.cancel()
                stage1_timeout = True
                grounding_text = "Grounding timeout."
                print(f"[Gemini] Stage 1 TIMEOUT after {GEMINI_TIMEOUT_STAGE1}s")
            except Exception as e:
                grounding_text = f"Grounding failed: {type(e).__name__}"
                print(f"[Gemini] Stage 1 error: {type(e).__name__}: {e}")
            finally:
                ex1.shutdown(wait=False, cancel_futures=True)

            stage1_ms = int((time.time() - stage1_started) * 1000)
            tier_instruction = self._tier_instruction(tier)
            max_tokens = 900 if str(tier).lower() == "free" else (1200 if str(tier).lower() == "pro" else 1500)
            grounding_compact = (grounding_text or "").strip()
            if len(grounding_compact) > 2400:
                grounding_compact = grounding_compact[:2400]

            final_prompt = (
                f"{tier_instruction}\n\n"
                "Output template (must follow):\n"
                f"{INTRO_LINE}\n"
                f"{S1}\n"
                "- ...\n"
                f"{S2}\n"
                "- ...\n"
                f"{S3}\n"
                "- ...\n"
                f"{S4}\n"
                "- ...\n"
                f"{S5}\n"
                "- ...\n"
                f"{SMC_HEADER}\n"
                "- Trend: ...\n"
                "- BOS: ...\n"
                "- CHoCH: ...\n"
                "- Active OB: ...\n"
                "- Open FVG: ...\n"
                "- Liquidity(B/S): ...\n\n"
                f"symbol={symbol}\n"
                f"context:\n{context}\n\n"
                f"grounding:\n{grounding_compact}\n\n"
                f"smc_summary:\n{smc_summary}\n\n"
                f"user_question={user_question or 'N/A'}"
            )

            def _run_stage2():
                last_err: Optional[Exception] = None
                for attempt in range(3):
                    try:
                        key2 = self._get_api_key() or api_key
                        c2 = genai.Client(api_key=key2)
                        return c2.models.generate_content(
                            model=MODEL_FINAL,
                            contents=final_prompt,
                            config=types.GenerateContentConfig(temperature=0.35, max_output_tokens=max_tokens),
                        )
                    except Exception as e:
                        last_err = e
                        msg = str(e).lower()
                        transient = (
                            "503" in msg
                            or "unavailable" in msg
                            or "overloaded" in msg
                            or "deadline" in msg
                            or "timeout" in msg
                        )
                        if transient and attempt < 2:
                            time.sleep(1.2 * (attempt + 1))
                            continue
                        raise
                if last_err:
                    raise last_err
                raise RuntimeError("stage2_failed")

            print(f"[Gemini] Stage 2 starting for {symbol}...")
            stage2_started = time.time()
            ex2 = ThreadPoolExecutor(max_workers=1)
            f2 = ex2.submit(_run_stage2)
            try:
                stage2_resp = f2.result(timeout=GEMINI_TIMEOUT_STAGE2)
                analysis = stage2_resp.text.strip() if stage2_resp and getattr(stage2_resp, "text", None) else ""
                analysis = self._ensure_smc_section(self._sanitize_analysis_text(analysis), smc_summary)

                used_fallback = False
                if not self._quality_ok(analysis, tier):
                    print(f"[Gemini] Stage 2 quality gate failed for {symbol}; running repair pass...")
                    repair_prompt = (
                        f"{tier_instruction}\n"
                        "The previous output is incomplete. Rewrite it fully in Traditional Chinese.\n"
                        "Keep all six sections and SMC fields. No markdown separators.\n\n"
                        f"symbol={symbol}\n"
                        f"context:\n{context}\n\n"
                        f"grounding:\n{grounding_compact}\n\n"
                        f"smc_summary:\n{smc_summary}\n\n"
                        f"previous_output:\n{analysis}\n"
                    )

                    def _run_repair():
                        key3 = self._get_api_key() or api_key
                        c3 = genai.Client(api_key=key3)
                        return c3.models.generate_content(
                            model=MODEL_FINAL,
                            contents=repair_prompt,
                            config=types.GenerateContentConfig(temperature=0.25, max_output_tokens=max_tokens + 180),
                        )

                    ex3 = ThreadPoolExecutor(max_workers=1)
                    f3 = ex3.submit(_run_repair)
                    try:
                        repair_resp = f3.result(timeout=GEMINI_REPAIR_TIMEOUT_SEC)
                        repair_text = repair_resp.text.strip() if repair_resp and getattr(repair_resp, "text", None) else ""
                        repair_text = self._ensure_smc_section(self._sanitize_analysis_text(repair_text), smc_summary)
                        if self._quality_ok(repair_text, tier):
                            analysis = repair_text
                    except Exception:
                        pass
                    finally:
                        ex3.shutdown(wait=False, cancel_futures=True)

                if not self._quality_ok(analysis, tier):
                    used_fallback = True
                    analysis = self._build_fallback_from_grounding(symbol, grounding_text, tier)
                    analysis = self._ensure_smc_section(self._sanitize_analysis_text(analysis), smc_summary)

                quality_pass = self._quality_ok(analysis, tier)
                if not analysis:
                    return {
                        "success": False,
                        "error": "empty_stage2_output",
                        "analysis": "",
                        "grounding_sources": grounding_sources,
                        "quality_pass": False,
                        "timings": {
                            "stage1_ms": stage1_ms,
                            "stage2_ms": int((time.time() - stage2_started) * 1000),
                            "total_ms": int((time.time() - started) * 1000),
                        },
                    }

                print(f"[Gemini] Stage 2 completed for {symbol}, {len(analysis)} chars")
                payload = {
                    "success": True,
                    "analysis": analysis,
                    "grounding_sources": grounding_sources,
                    "model_used": MODEL_FINAL,
                    "grounding_model": MODEL_GROUNDING,
                    "quality_pass": quality_pass,
                    "degraded": used_fallback,
                    "error": None,
                    "timings": {
                        "stage1_ms": stage1_ms,
                        "stage2_ms": int((time.time() - stage2_started) * 1000),
                        "total_ms": int((time.time() - started) * 1000),
                        "stage1_timeout": stage1_timeout,
                    },
                }
                if quality_pass:
                    self._write_analysis_cache(cache_key, payload)
                return payload
            except FuturesTimeoutError:
                f2.cancel()
                print(f"[Gemini] Stage 2 TIMEOUT after {GEMINI_TIMEOUT_STAGE2}s")
                fallback = self._build_fallback_from_grounding(symbol, grounding_text, tier)
                fallback = self._ensure_smc_section(self._sanitize_analysis_text(fallback), smc_summary)
                if fallback:
                    self._background_retry_stage2(symbol, final_prompt)
                quality_pass = self._quality_ok(fallback, tier)
                payload = {
                    "success": bool(fallback),
                    "degraded": bool(fallback),
                    "error": f"stage2_timeout_{GEMINI_TIMEOUT_STAGE2}s",
                    "analysis": fallback,
                    "grounding_text": grounding_text,
                    "grounding_sources": grounding_sources,
                    "quality_pass": quality_pass,
                    "timings": {
                        "stage1_ms": stage1_ms,
                        "stage2_ms": int((time.time() - stage2_started) * 1000),
                        "total_ms": int((time.time() - started) * 1000),
                        "stage2_timeout": True,
                    },
                }
                if quality_pass:
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
                    "quality_pass": False,
                    "timings": {
                        "stage1_ms": stage1_ms,
                        "stage2_ms": int((time.time() - stage2_started) * 1000),
                        "total_ms": int((time.time() - started) * 1000),
                    },
                }
            finally:
                ex2.shutdown(wait=False, cancel_futures=True)

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
            "Use Traditional Chinese only.\n"
            "You are DiscoverLatest AI. Keep tone professional and concise.\n"
            "Do not use markdown separators or star emphasis.\n"
            f"Context:\n{context_str}\n\n"
            f"History:\n{chr(10).join(rendered_history)}\n\n"
            f"User: {user_message}\n"
            "Reply with practical investment discussion, risk-aware and specific."
        )

        try:
            client = genai.Client(api_key=api_key)
            response = client.models.generate_content(model=MODEL_FINAL, contents=prompt)
            reply = (getattr(response, "text", "") or "").strip()
            if not reply:
                return {"success": False, "error": "empty_chat_output"}
            return {"success": True, "reply": self._sanitize_analysis_text(reply)}
        except Exception as e:
            print(f"[Gemini] Chat error: {e}")
            return {"success": False, "error": str(e)}


gemini_service = GeminiService()
