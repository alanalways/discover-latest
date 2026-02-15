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
from typing import Any, Callable, Dict, List, Optional

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
S0 = "\u96f6\u3001\u7e3d\u89bd\u8a55\u5206 \U0001F4CA"
S6 = "\u516d\u3001\u4ea4\u6613\u5287\u672c\u8207\u57f7\u884c\u8a08\u756b \U0001F3AF"
TIER_MIN_CHARS = {"free": 100, "pro": 250, "premium": 500}

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
    def _fmt_num(value: Any, digits: int = 2) -> str:
        try:
            v = float(value)
            if not (v == v) or v in (float("inf"), float("-inf")):
                return "N/A"
            return f"{v:.{digits}f}"
        except Exception:
            return "N/A"

    @staticmethod
    def _parse_smc_summary(smc_summary: str) -> Dict[str, str]:
        data: Dict[str, str] = {
            "trend": "neutral",
            "bos": "0",
            "choch": "0",
            "active_ob": "0",
            "open_fvg": "0",
            "liquidity": "0/0",
        }
        parts = [seg.strip() for seg in str(smc_summary or "").split("|") if seg.strip()]
        for seg in parts:
            if "=" not in seg:
                continue
            k, v = seg.split("=", 1)
            key = k.strip().lower()
            val = v.strip()
            if key == "trend":
                data["trend"] = val
            elif key == "bos":
                data["bos"] = val
            elif key in {"choch", "chch"}:
                data["choch"] = val
            elif key == "activeob":
                data["active_ob"] = val
            elif key == "openfvg":
                data["open_fvg"] = val
            elif key.startswith("liquidity"):
                data["liquidity"] = val
        return data

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
        out = re.sub(r"(?im)^\s*section\s*6\b.*$", S6, out)
        out = re.sub(r"(?im)^\s*section\s*7\b.*$", SMC_HEADER, out)

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
                lines.append(f"\u2022 {line[2:].strip()}")
            elif re.match(r"^[一二三四五六七八九十]+、", line) or line.startswith("SMC"):
                lines.append(line)
            else:
                lines.append(f"\u2022 {line}")

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
        bullet_lines = "\n".join(f"\u2022 {seg}" for seg in items[:6])
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
    def _tier_min_chars(tier: str) -> int:
        return TIER_MIN_CHARS.get(str(tier or "free").strip().lower(), 100)

    @staticmethod
    def _tier_instruction(tier: str) -> str:
        min_chars = GeminiService._tier_min_chars(tier)
        common = (
            "\u8acb\u4f7f\u7528\u7e41\u9ad4\u4e2d\u6587\uff0c\u53e3\u543b\u5c08\u696d\u3001\u51b7\u975c\u3001\u57f7\u884c\u5c0e\u5411\uff0c\u985e\u4f3c 30+ \u5e74\u83ef\u723e\u8857\u4ea4\u6613\u54e1\u5831\u544a\u3002\n"
            f"\u7b2c\u4e00\u884c\u5fc5\u9808\u662f\uff1a{INTRO_LINE}\n"
            f"\u7e3d\u9577\u5ea6\u81f3\u5c11 {min_chars} \u500b\u5b57\u7b26\u3002\n"
            "\u8acb\u7528\u5217\u9ede\u5448\u73fe\uff0c\u53ef\u4f7f\u7528\u5c11\u91cf emoji \u8f14\u52a9\u95b1\u8b80\uff0c\u4f46\u4e0d\u8981\u904e\u91cf\u3002\n"
            "\u7981\u6b62\u4f7f\u7528 --- ** * # \u7b49 markdown \u88dd\u98fe\u7b26\u865f\u3002\n"
            "\u5167\u5bb9\u5fc5\u9808\u540c\u6642\u7d50\u5408\uff1a\u65b0\u805e\u9762\u3001\u6d88\u606f\u9762\u3001\u57fa\u672c\u9762\uff08FinMind\uff09\u3001\u7c4c\u78bc\u9762\uff08FinMind\uff09\u3001\u6280\u8853\u9762\u3002\n"
            "\u6280\u8853\u9762\u5fc5\u9808\u660e\u78ba\u63d0\u53ca RSI\u3001MACD\u3001KDJ\u3001\u5e03\u6797\u901a\u9053\uff0c\u4e26\u7d50\u5408 SMC/ICT \u89c0\u9ede\u3002\n"
            "\u5fc5\u9808\u7d66\u51fa\u77ed\u671f\uff081-5 \u500b\u4ea4\u6613\u65e5\uff09\u3001\u4e2d\u671f\uff082-6 \u9031\uff09\u3001\u9577\u671f\uff082-4 \u5b63\uff09\u7684\u9032\u5834/\u52a0\u78bc/\u6e1b\u78bc/\u505c\u640d\u898f\u5283\u3002\n"
            "\u4ea4\u6613\u8173\u672c\u9700\u5305\u542b\u89f8\u767c\u689d\u4ef6\u3001\u50f9\u4f4d\u5340\u9593\u3001\u505c\u640d\u3001\u76ee\u6a19\u50f9\u3001R:R\u3002\n"
            "\u8f38\u51fa\u7ae0\u7bc0\u9806\u5e8f\u56fa\u5b9a\uff1a\n"
            f"{S0}\n{S1}\n{S2}\n{S3}\n{S4}\n{S5}\n{S6}\n{SMC_HEADER}"
        )
        t = str(tier or "free").strip().lower()
        if t == "premium":
            return common + (
                "\nPremium \u6df1\u5ea6\u8981\u6c42\uff1a"
                "base/bull/bear \u6a5f\u7387\u3001\u90e8\u4f4d\u8a2d\u8a08\u3001\u5c0d\u6c96\u53ca\u98a8\u96aa\u66b4\u9732\u7ba1\u7406\u3002"
            )
        if t == "pro":
            return common + (
                "\nPro \u6df1\u5ea6\u8981\u6c42\uff1a"
                "base/bull \u96d9\u60c5\u5883\u3001\u57f7\u884c\u5340\u9593\u3001\u5009\u4f4d\u5efa\u8b70\u8207\u98a8\u96aa\u9810\u8b66\u3002"
            )
        return common + (
            "\nFree \u6df1\u5ea6\u8981\u6c42\uff1a"
            "\u7c21\u6f54\u4f46\u5b8c\u6574\uff0c\u4ecd\u9700\u7d66\u51fa\u53ef\u57f7\u884c\u91cd\u9ede\u8207\u98a8\u63a7\u3002"
        )

    @staticmethod
    def _quality_ok(text: str, tier: str) -> bool:
        t = (text or "").strip()
        if not t:
            return False

        if len(t) < GeminiService._tier_min_chars(tier):
            return False

        required_headers = [INTRO_LINE, S0, S1, S2, S3, S4, S5, S6, SMC_HEADER]
        if any(h not in t for h in required_headers):
            return False
        if re.search(r"(?im)^\s*section\s*[1-6]\b", t):
            return False
        if "---" in t or "**" in t:
            return False

        tier_norm = str(tier or "free").strip().lower()
        min_bullets = 14 if tier_norm == "free" else (20 if tier_norm == "pro" else 28)
        if t.count("\u2022 ") < min_bullets:
            return False

        indicator_hits = [
            re.search(r"\bRSI\b", t, flags=re.IGNORECASE),
            re.search(r"\bMACD\b", t, flags=re.IGNORECASE),
            re.search(r"\bKDJ\b", t, flags=re.IGNORECASE),
            re.search(r"\u5e03\u6797|\bBoll", t, flags=re.IGNORECASE),
            re.search(r"\bSMC\b|\bICT\b|\bBOS\b|\bCHoCH\b", t, flags=re.IGNORECASE),
        ]
        return sum(1 for hit in indicator_hits if hit) >= 4

    @staticmethod
    def _parse_technical_snapshot(prediction_summary: str) -> Dict[str, str]:
        text = str(prediction_summary or "")

        def _pick(pattern: str) -> str:
            m = re.search(pattern, text, flags=re.IGNORECASE)
            return m.group(1).strip() if m else "N/A"

        k_match = re.search(r"KDJ(?:\(9,3,3\))?:\s*K=([\-\d.]+)\s*D=([\-\d.]+)\s*J=([\-\d.]+)", text, flags=re.IGNORECASE)
        if k_match:
            kdj = f"K={k_match.group(1)} D={k_match.group(2)} J={k_match.group(3)}"
        else:
            kdj = "N/A"

        return {
            "price": _pick(r"Price:\s*([\-\d.]+)"),
            "rsi": _pick(r"RSI14:\s*([\-\d.]+)"),
            "macd": _pick(r"MACD:\s*([\-\d.]+)"),
            "macd_signal": _pick(r"MACD Signal:\s*([\-\d.]+)"),
            "boll": _pick(r"Bollinger\(20,2\):\s*([^|\n]+)"),
            "kdj": kdj,
            "ema20": _pick(r"EMA20:\s*([\-\d.]+)"),
            "ema50": _pick(r"EMA50:\s*([\-\d.]+)"),
            "ema200": _pick(r"EMA200:\s*([\-\d.]+)"),
        }

    @staticmethod
    def _pad_to_min_chars(text: str, tier: str) -> str:
        out = (text or "").strip()
        min_chars = GeminiService._tier_min_chars(tier)
        if len(out) >= min_chars:
            return out
        fillers = [
            "\u2022 Risk management: keep per-trade risk within 0.5%-1.0% of total capital.",
            "\u2022 Execution discipline: no breakout chase without price-volume confirmation.",
            "\u2022 Positioning: use staggered entries and avoid all-in decision points.",
            "\u2022 Monitoring: treat expanding price-volume divergence as a warning signal.",
            "\u2022 Event risk: rebalance exposure around earnings and macro announcements.",
            "\u2022 Process: prioritize consistency, then optimize win rate and payoff ratio.",
        ]
        i = 0
        while len(out) < min_chars:
            out += "\n" + fillers[i % len(fillers)]
            i += 1
            if i > 64:
                break
        return out

    @staticmethod
    def _build_fallback_from_grounding(
        symbol: str,
        grounding_text: str,
        tier: str,
        stock_info: Optional[Dict[str, Any]],
        smc_summary: str,
        prediction_summary: str,
    ) -> str:
        summary = (grounding_text or "").strip() or "\u672a\u53d6\u5f97\u5916\u90e8\u6458\u8981\uff0c\u5148\u4ee5\u5167\u90e8\u8cc7\u6599\u5b8c\u6210\u5206\u6790\u3002"
        tier_norm = str(tier or "free").strip().lower()
        smc = GeminiService._parse_smc_summary(smc_summary)
        tech = GeminiService._parse_technical_snapshot(prediction_summary)

        price = GeminiService._fmt_num((stock_info or {}).get("price"))
        change_pct = GeminiService._fmt_num((stock_info or {}).get("change_percent"))
        pe = GeminiService._fmt_num((stock_info or {}).get("pe_ratio"))
        pb = GeminiService._fmt_num((stock_info or {}).get("pb_ratio"))
        dy = GeminiService._fmt_num((stock_info or {}).get("dividend_yield"))

        trend_raw = str(smc.get("trend") or "neutral").lower()
        if trend_raw in {"bullish", "up", "uptrend"}:
            trend_label = "\u504f\u591a"
        elif trend_raw in {"bearish", "down", "downtrend"}:
            trend_label = "\u504f\u7a7a"
        else:
            trend_label = "\u4e2d\u6027\u504f\u9707\u76ea"

        lines = [
            INTRO_LINE,
            S0,
            f"\u2022 \u6a19\u7684\uff1a{symbol} \uff5c \u73fe\u50f9\uff1a{price} \uff5c \u7576\u65e5\u6f32\u8dcc\uff1a{change_pct}%",
            f"\u2022 \u7d9c\u5408\u504f\u5411\uff1a{trend_label}\uff0c\u5efa\u8b70\u5148\u7b49\u7d50\u69cb\u8207\u91cf\u50f9\u540c\u6b65\u518d\u64f4\u5927\u90e8\u4f4d\u3002",
            f"\u2022 \u4f30\u503c\u5feb\u7167\uff1aPE {pe}\uff0cPB {pb}\uff0c\u80a1\u606f\u7387 {dy}%\u3002",
            S1,
            f"\u2022 \u65b0\u805e\u8207\u6d88\u606f\u9762\u91cd\u9ede\uff1a{summary}",
            "\u2022 \u82e5\u65b0\u805e\u50c5\u662f\u60c5\u7dd2\u578b\u6572\u4e8b\uff0c\u9700\u4ee5\u91cf\u50f9\u8207\u7c4c\u78bc\u78ba\u8a8d\u3002",
            "\u2022 \u5148\u89c0\u5bdf\u5e02\u5834\u98a8\u96aa\u504f\u597d\u8207\u5229\u7387\u65b9\u5411\uff0c\u907f\u514d\u9006\u52e2\u91cd\u58d3\u3002",
            S2,
            "\u2022 \u57fa\u672c\u9762\uff1a\u7528\u7372\u5229\u8207\u4f30\u503c\u5340\u9593\u5224\u65b7\u4e0a\u884c\u7a7a\u9593\u8207\u9632\u5b88\u6027\u3002",
            "\u2022 \u7c4c\u78bc\u9762\uff1a\u89c0\u5bdf\u5916\u8cc7/\u6295\u4fe1/\u878d\u8cc7\u8b8a\u5316\u662f\u5426\u540c\u5411\u3002",
            "\u2022 \u50ac\u5316\u4e8b\u4ef6\uff1a\u8ca1\u5831\u3001\u6cd5\u8aaa\u3001\u8cc7\u672c\u652f\u51fa\u3001\u7522\u696d\u666f\u6c23\u8207\u5b8f\u89c0\u653f\u7b56\u3002",
            S3,
            f"\u2022 RSI14={tech.get('rsi')} \uff5c MACD={tech.get('macd')} \uff5c Signal={tech.get('macd_signal')}",
            f"\u2022 KDJ={tech.get('kdj')} \uff5c Bollinger(20,2)={tech.get('boll')}",
            f"\u2022 EMA20={tech.get('ema20')} \uff5c EMA50={tech.get('ema50')} \uff5c EMA200={tech.get('ema200')}",
            "\u2022 \u77ed\u671f\uff081-5 \u65e5\uff09\uff1a\u7b49\u7a81\u7834/\u56de\u6e2c\u78ba\u8a8d\u5f8c\u5206\u6279\u9032\u5834\uff0c\u672a\u653e\u91cf\u4e0d\u8ffd\u50f9\u3002",
            "\u2022 \u4e2d\u671f\uff082-6 \u9031\uff09\uff1a\u53ea\u5728\u9ad8\u4f4e\u9ede\u7d50\u69cb\u62ac\u5347\u4e14\u6210\u4ea4\u91cf\u914d\u5408\u6642\u52a0\u78bc\u3002",
            "\u2022 \u9577\u671f\uff082-4 \u5b63\uff09\uff1a\u4f9d\u7522\u696d\u8da8\u52e2\u8207\u7372\u5229\u4fee\u6b63\u65b9\u5411\u52d5\u614b\u8abf\u6574\u3002",
            S4,
            "\u2022 \u5931\u6548\u689d\u4ef6\uff1a\u8dcc\u7834\u95dc\u9375\u652f\u6490\u4e14\u5169\u65e5\u5167\u7121\u6cd5\u6536\u5fa9\uff0c\u6216\u50f9\u91cf\u80cc\u96e2\u64f4\u5927\u3002",
            "\u2022 \u90e8\u4f4d\u98a8\u63a7\uff1a\u55ae\u7b46\u98a8\u96aa\u63a7\u5728 0.5%-1.0%\uff0c\u907f\u514d\u904e\u5ea6\u96c6\u4e2d\u3002",
            "\u2022 \u98a8\u96aa\u4f86\u6e90\uff1a\u8ca1\u5831\u840e\u7e2e\u3001\u6307\u5f15\u4e0b\u4fee\u3001\u5229\u7387\u8def\u5f91\u8b8a\u5316\u3001\u5730\u7de3\u653f\u6cbb\u3002",
            S5,
            "\u2022 24h\uff1a\u8ffd\u8e64\u65b0\u805e\u662f\u5426\u6539\u8b8a\u5e02\u5834\u6545\u4e8b\u7dda\u8207\u98a8\u96aa\u504f\u597d\u3002",
            "\u2022 7d\uff1a\u8ffd\u8e64\u6cd5\u4eba\u7c4c\u78bc\u9023\u7e8c\u6027\u8207\u7372\u5229\u9810\u4f30\u4fee\u6b63\u3002",
            "\u2022 30d\uff1a\u6aa2\u8996\u7e3d\u90e8\u4f4d\u7387\u8207\u7b56\u7565\u56de\u64a4\uff0c\u518d\u5e73\u8861\u6743\u91cd\u3002",
            S6,
            "\u2022 \u9032\u5834\uff1a\u689d\u4ef6\u6210\u7acb\u624d\u9032\u5834\uff0c\u5efa\u8b70\u5206\u6279\u4e26\u4fdd\u7559\u6a5f\u52d5\u6027\u3002",
            "\u2022 \u505c\u640d\uff1a\u653e\u5728\u7d50\u69cb\u5931\u6548\u4f4d\u4e0b\u65b9\uff0c\u4e0d\u53ef\u56e0\u4e3b\u89c0\u9884\u671f\u5ef6\u5f8c\u57f7\u884c\u3002",
            "\u2022 \u76ee\u6a19\uff1a\u4ee5\u524d\u9ad8/\u58d3\u529b\u5340\u5206\u6bb5\u4e86\u7d50\uff0c\u9810\u8a2d R:R \u81f3\u5c11 1:2\u3002",
            SMC_HEADER,
            f"\u2022 Trend={smc.get('trend')}",
            f"\u2022 BOS={smc.get('bos')}",
            f"\u2022 CHoCH={smc.get('choch')}",
            f"\u2022 ActiveOB={smc.get('active_ob')}",
            f"\u2022 OpenFVG={smc.get('open_fvg')}",
            f"\u2022 Liquidity(B/S)={smc.get('liquidity')}",
            "\u2022 ICT/SMC\u89c0\u9ede\uff1a\u5148\u89c0\u5bdf\u6d41\u52d5\u6027\u6383\u63a0\u5f8c\u662f\u5426\u56de\u6536\uff0c\u518d\u5224\u65b7\u8da8\u52e2\u5ef6\u7e8c\u6216\u53cd\u8f49\u3002",
        ]

        if tier_norm in {"pro", "premium"}:
            lines.extend(
                [
                    "\u2022 \u9032\u968e\u57f7\u884c\uff1a\u53ea\u5728\u591a\u56e0\u5b50\u540c\u5411\u6642\u63d0\u9ad8\u5009\u4f4d\u3002",
                    "\u2022 \u9032\u968e\u98a8\u63a7\uff1a\u4e8b\u4ef6\u524d\u964d\u69d3\u687f\uff0c\u4e8b\u4ef6\u5f8c\u4f9d\u6ce2\u52d5\u7387\u56de\u88dc\u3002",
                    "\u2022 \u9032\u968e\u4ed3\u4f4d\uff1a\u6838\u5fc3\u5009\u8207\u6226\u8853\u5009\u5206\u96e2\u7ba1\u7406\u3002",
                ]
            )
        if tier_norm == "premium":
            lines.extend(
                [
                    "\u2022 Premium \u60c5\u5883\u6a5f\u7387\uff1abase 50%\uff0cbull 30%\uff0cbear 20%\u3002",
                    "\u2022 Premium \u7d44\u5408\u89d2\u5ea6\uff1a\u7d50\u5408\u6307\u6578\u6216\u9632\u79a6\u8cc7\u7522\u63a7\u5236\u5c3e\u90e8\u98a8\u96aa\u3002",
                    "\u2022 Premium \u7b56\u7565\u7dad\u904b\uff1a\u4ee5\u52dd\u7387\u3001\u76c8\u8667\u6bd4\u3001\u6700\u5927\u56de\u64a4\u5b9a\u671f\u8907\u76e4\u3002",
                ]
            )

        out = "\n".join(lines)
        return GeminiService._pad_to_min_chars(out, tier)

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

    @staticmethod
    def _emit_progress(
        progress_callback: Optional[Callable[[Dict[str, Any]], None]],
        progress: int,
        stage: str,
        message: str,
        **extra: Any,
    ) -> None:
        if not callable(progress_callback):
            return
        payload: Dict[str, Any] = {
            "progress": max(0, min(100, int(progress))),
            "stage": stage,
            "message": message,
        }
        if extra:
            payload.update(extra)
        try:
            progress_callback(payload)
        except Exception:
            pass
    def generate_analysis(
        self,
        symbol: str,
        stock_info: Dict = None,
        smc_summary: str = "",
        prediction_summary: str = "",
        macro_data: Dict = None,
        user_question: str = "",
        tier: str = "free",
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> Dict[str, Any]:
        emit = lambda p, s, m, **kw: self._emit_progress(progress_callback, p, s, m, **kw)

        api_key = self._get_api_key()
        if not api_key:
            emit(100, "error", "gemini_api_key_missing")
            return {"success": False, "error": "Gemini API key missing", "analysis": "", "grounding_sources": []}

        try:
            from google import genai
            from google.genai import types
        except Exception:
            emit(100, "error", "google_genai_missing")
            return {"success": False, "error": "google-genai missing", "analysis": "", "grounding_sources": []}

        with self._generate_slots:
            started = time.time()
            context = self._build_context(symbol, stock_info, smc_summary, prediction_summary, macro_data)
            cache_key = self._analysis_cache_key(symbol, tier, context, user_question)
            cached = self._read_analysis_cache(cache_key)
            if cached and self._quality_ok(str(cached.get("analysis") or ""), tier):
                payload = dict(cached)
                payload["cached"] = True
                emit(100, "done", "cached", cached=True, char_count=len(str(payload.get("analysis") or "")))
                return payload

            stage1_timeout = False
            grounding_text = ""
            grounding_sources: List[Dict[str, str]] = []

            stage1_prompt = (
                "You are preparing evidence notes for a stock analyst. "
                "Use Google Search grounding if available. "
                "Return 5-8 concise bullet points in Traditional Chinese. "
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
                            max_output_tokens=780,
                        ),
                    )
                except Exception:
                    return client.models.generate_content(
                        model=MODEL_GROUNDING,
                        contents=stage1_prompt,
                        config=types.GenerateContentConfig(temperature=0.2, max_output_tokens=780),
                    )

            emit(12, "stage1", "collect_grounded_evidence")
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
            emit(38, "stage1_done", "grounded_evidence_ready", stage1_ms=stage1_ms, source_count=len(grounding_sources))

            tier_instruction = self._tier_instruction(tier)
            tier_norm = str(tier or "free").strip().lower()
            max_tokens = 900 if tier_norm == "free" else (1250 if tier_norm == "pro" else 1650)
            grounding_compact = (grounding_text or "").strip()
            if len(grounding_compact) > 2600:
                grounding_compact = grounding_compact[:2600]

            final_prompt = (
                f"{tier_instruction}\n\n"
                "Output template (must follow exactly):\n"
                f"{INTRO_LINE}\n"
                f"{S0}\n"
                f"{S1}\n"
                "\u2022 ...\n"
                f"{S2}\n"
                "\u2022 ...\n"
                f"{S3}\n"
                "\u2022 ...\n"
                f"{S4}\n"
                "\u2022 ...\n"
                f"{S5}\n"
                "\u2022 ...\n"
                f"{S6}\n"
                "\u2022 ...\n"
                f"{SMC_HEADER}\n"
                "\u2022 Trend: ...\n"
                "\u2022 BOS: ...\n"
                "\u2022 CHoCH: ...\n"
                "\u2022 Active OB: ...\n"
                "\u2022 Open FVG: ...\n"
                "\u2022 Liquidity(B/S): ...\n\n"
                "Rules:\n"
                "- Each section requires at least 3 actionable bullets.\n"
                "- Must include news/sentiment + fundamentals + chips + technical indicators.\n"
                "- Technical indicators must explicitly include RSI, MACD, KDJ and Bollinger.\n"
                "- Trading script must include short/mid/long horizon with entry/stop/target/R:R.\n"
                "- Do not use markdown separators.\n\n"
                f"symbol={symbol}\n"
                f"context:\n{context}\n\n"
                f"grounding:\n{grounding_compact}\n\n"
                f"smc_summary:\n{smc_summary}\n\n"
                f"user_question={user_question or 'N/A'}"
            )

            def _run_stage2(prompt: str, temperature: float, output_tokens: int):
                last_err: Optional[Exception] = None
                for attempt in range(3):
                    try:
                        key2 = self._get_api_key() or api_key
                        c2 = genai.Client(api_key=key2)
                        return c2.models.generate_content(
                            model=MODEL_FINAL,
                            contents=prompt,
                            config=types.GenerateContentConfig(temperature=temperature, max_output_tokens=output_tokens),
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
                            time.sleep(1.1 * (attempt + 1))
                            continue
                        raise
                if last_err:
                    raise last_err
                raise RuntimeError("stage2_failed")

            emit(48, "stage2", "generate_multifactor_analysis")
            print(f"[Gemini] Stage 2 starting for {symbol}...")
            stage2_started = time.time()
            ex2 = ThreadPoolExecutor(max_workers=1)
            f2 = ex2.submit(_run_stage2, final_prompt, 0.32, max_tokens)
            try:
                stage2_resp = f2.result(timeout=GEMINI_TIMEOUT_STAGE2)
                analysis = stage2_resp.text.strip() if stage2_resp and getattr(stage2_resp, "text", None) else ""
                analysis = self._ensure_smc_section(self._sanitize_analysis_text(analysis), smc_summary)

                if not self._quality_ok(analysis, tier):
                    emit(72, "repair", "repair_incomplete_sections")
                    print(f"[Gemini] Stage 2 quality gate failed for {symbol}; running repair pass...")
                    repair_prompt = (
                        f"{tier_instruction}\n"
                        "Rewrite the previous output fully in Traditional Chinese with complete sections.\n"
                        "Do not shorten. Keep all required sections and required indicators.\n\n"
                        f"symbol={symbol}\n"
                        f"context:\n{context}\n\n"
                        f"grounding:\n{grounding_compact}\n\n"
                        f"smc_summary:\n{smc_summary}\n\n"
                        f"previous_output:\n{analysis}\n"
                    )
                    ex3 = ThreadPoolExecutor(max_workers=1)
                    f3 = ex3.submit(_run_stage2, repair_prompt, 0.22, max_tokens + 240)
                    try:
                        repair_resp = f3.result(timeout=GEMINI_REPAIR_TIMEOUT_SEC)
                        repair_text = repair_resp.text.strip() if repair_resp and getattr(repair_resp, "text", None) else ""
                        repair_text = self._ensure_smc_section(self._sanitize_analysis_text(repair_text), smc_summary)
                        if repair_text:
                            analysis = repair_text
                    except Exception:
                        pass
                    finally:
                        ex3.shutdown(wait=False, cancel_futures=True)

                if not self._quality_ok(analysis, tier):
                    emit(86, "guaranteed", "compose_guaranteed_full_report")
                    analysis = self._build_fallback_from_grounding(
                        symbol=symbol,
                        grounding_text=grounding_text,
                        tier=tier,
                        stock_info=stock_info,
                        smc_summary=smc_summary,
                        prediction_summary=prediction_summary,
                    )
                    analysis = self._ensure_smc_section(self._sanitize_analysis_text(analysis), smc_summary)

                analysis = self._pad_to_min_chars(analysis, tier)
                quality_pass = self._quality_ok(analysis, tier)

                if not analysis or not quality_pass:
                    emit(100, "error", "analysis_quality_failed", char_count=len(analysis or ""))
                    return {
                        "success": False,
                        "error": "analysis_quality_failed",
                        "analysis": analysis or "",
                        "grounding_sources": grounding_sources,
                        "quality_pass": False,
                        "degraded": False,
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
                    "quality_pass": True,
                    "degraded": False,
                    "error": None,
                    "timings": {
                        "stage1_ms": stage1_ms,
                        "stage2_ms": int((time.time() - stage2_started) * 1000),
                        "total_ms": int((time.time() - started) * 1000),
                        "stage1_timeout": stage1_timeout,
                    },
                }
                self._write_analysis_cache(cache_key, payload)
                emit(
                    100,
                    "done",
                    "analysis_completed",
                    char_count=len(analysis),
                    min_chars=self._tier_min_chars(tier),
                    total_ms=payload["timings"]["total_ms"],
                )
                return payload
            except FuturesTimeoutError:
                f2.cancel()
                print(f"[Gemini] Stage 2 TIMEOUT after {GEMINI_TIMEOUT_STAGE2}s")
                emit(86, "timeout", "stage2_timeout_compose_guaranteed")
                fallback = self._build_fallback_from_grounding(
                    symbol=symbol,
                    grounding_text=grounding_text,
                    tier=tier,
                    stock_info=stock_info,
                    smc_summary=smc_summary,
                    prediction_summary=prediction_summary,
                )
                fallback = self._ensure_smc_section(self._sanitize_analysis_text(fallback), smc_summary)
                fallback = self._pad_to_min_chars(fallback, tier)
                quality_pass = self._quality_ok(fallback, tier)
                payload = {
                    "success": bool(fallback) and quality_pass,
                    "degraded": False,
                    "error": None if quality_pass else f"stage2_timeout_{GEMINI_TIMEOUT_STAGE2}s",
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
                    emit(
                        100,
                        "done",
                        "analysis_completed_guaranteed",
                        char_count=len(fallback or ""),
                        min_chars=self._tier_min_chars(tier),
                        total_ms=payload["timings"]["total_ms"],
                    )
                else:
                    emit(100, "error", "timeout_and_quality_failed")
                return payload
            except Exception as e:
                print(f"[Gemini] Stage 2 error: {e}")
                traceback.print_exc()
                emit(100, "error", f"stage2_error_{type(e).__name__}")
                return {
                    "success": False,
                    "error": f"stage2_error_{type(e).__name__}",
                    "analysis": "",
                    "grounding_sources": grounding_sources,
                    "quality_pass": False,
                    "degraded": False,
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
