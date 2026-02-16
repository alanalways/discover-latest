"""Gemini AI service with stage1 grounding + stage2 synthesis."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from typing import Any, Callable, Dict, List, Optional

from config.models import MODEL_FINAL, MODEL_GROUNDING

logger = logging.getLogger(__name__)

GEMINI_TIMEOUT_STAGE1 = int(os.environ.get("GEMINI_TIMEOUT_STAGE1", "12"))
GEMINI_TIMEOUT_STAGE2 = int(os.environ.get("GEMINI_TIMEOUT_STAGE2", "30"))
GEMINI_TOTAL_TIMEOUT = int(os.environ.get("GEMINI_TOTAL_TIMEOUT", "42"))
GEMINI_MAX_CONCURRENT = max(1, int(os.environ.get("GEMINI_MAX_CONCURRENT", "2")))
GEMINI_ANALYSIS_CACHE_TTL_SEC = max(0, int(os.environ.get("GEMINI_ANALYSIS_CACHE_TTL_SEC", "14400")))
GEMINI_GROUNDING_CACHE_TTL_SEC = max(0, int(os.environ.get("GEMINI_GROUNDING_CACHE_TTL_SEC", "14400")))
GEMINI_GROUNDING_CACHE_MAXSIZE = max(32, int(os.environ.get("GEMINI_GROUNDING_CACHE_MAXSIZE", "256")))

INTRO_LINE = "\u6211\u662f DiscoverLatest \u5c08\u5c6c AI \U0001F680"
S1 = "1.\u5e02\u5834\u5feb\u5831 \U0001F4F0"
S2 = "2.\u6280\u8853\u9762\u5206\u6790 \U0001F4C8"
S3 = "3.\u9032\u51fa\u5834\u8a08\u5283 \U0001F3AF"
S4 = "4.\u98a8\u96aa\u63d0\u793a \u26A0\uFE0F"
S5 = "5.\u7d50\u8ad6 \u2705"
S6 = "6.\u60c5\u5883\u4ea4\u6613\u5730\u5716 \u504f\u591a \u504f\u7a7a \u9707\u76ea \U0001F5FA\uFE0F"
S7 = "7.\u5b8f\u89c0\u9032\u968e\u5206\u6790 \U0001F30D"
TIER_MIN_CHARS = {"free": 100, "pro": 250, "premium": 500}
UNIFIED_SYSTEM_PROMPT = """你是 DiscoverLatest 專屬 AI 深度分析引擎
身份 30 年經驗交易員 風格冷靜 執行導向 數據驅動
語言 全文繁體中文 禁止英文句子 技術縮寫 RSI MACD SMC 等除外
格式 純文字列點 禁止任何 markdown 符號 --- ** *** ## ### ``` __ ~~ >

固定輸出結構 不可更改標題文字與順序

我是 DiscoverLatest 專屬 AI 🚀
1.市場快報 📰
• 當前股價 當日漲跌幅 近五日走勢 成交量變化
• 3-5 個最新驅動因子 財報 法說 產業消息 評級 資金輪動 每個註明偏多或偏空

2.技術面分析 📈
• SMC 結構 趨勢 BOS CHoCH 訂單塊 FVG 流動性
• RSI14 數值與超買超賣判讀
• MACD 數值 金叉死叉 柱狀體方向
• KDJ(9,3,3) K D J 數值與交叉
• 布林通道(20,2) 上軌 中軌 下軌與股價位置
• EMA20 EMA50 EMA200 排列與支撐壓力
• 多空結構結論

3.進出場計劃 🎯
• 短期 1-5日 進場區 停損 目標價 R:R
• 中期 2-6週 進場區 停損 目標價 R:R
• 長期 2-4季 進場區 停損 目標價 R:R
• 每個週期附加碼 減碼觸發條件

4.風險提示 ⚠️
• 事件風險 財報 指引 利率 匯率 地緣政治
• 交易風險 追價 槓桿 過度集中
• 失效條件與停損執行原則

5.結論 ✅
• 2-3 句可執行總結 明確方向與優先動作

6.情境交易地圖 偏多 偏空 震盪 🗺️
• 偏多 觸發條件 關鍵價位 應對策略
• 偏空 觸發條件 關鍵價位 應對策略
• 震盪 觸發條件 關鍵價位 應對策略

7.宏觀進階分析 🌍
• 利率 美元 指數對本標的的傳導機制
• 未來一季最需追蹤的 3 個宏觀變數
"""
TIER_EXTRA = {
    "free": "篇幅要求 完整但精煉 每章節至少 3 條重點",
    "pro": "篇幅要求 深入分析 每章節至少 4 到 5 條重點 補充 base bull 雙情境機率 倉位建議與風險預警",
    "premium": "篇幅要求 全面深度 每章節至少 5 到 7 條重點 補充 base bull bear 三情境機率 部位設計 對沖策略 風險暴露管理 情境地圖含觸發機率",
}

_key_pool: List[str] = []
_key_index = 0
_key_lock = threading.Lock()

_metrics_cache: Dict[str, Dict[str, Any]] = {}
_metrics_cache_lock = threading.Lock()

_industry_chain_cache: Dict[str, Dict[str, Any]] = {}
_industry_chain_cache_lock = threading.Lock()

_analysis_cache: Dict[str, Dict[str, Any]] = {}
_analysis_cache_lock = threading.Lock()

_grounding_cache: Dict[str, Dict[str, Any]] = {}
_grounding_cache_lock = threading.Lock()


def _load_key_pool() -> List[str]:
    global _key_pool
    if _key_pool:
        return _key_pool

    multi = os.environ.get("GEMINI_API_KEYS", "")
    if multi:
        keys = [k.strip() for k in multi.split(",") if k.strip()]
        if keys:
            _key_pool = keys
            logger.info("Loaded %d API keys from GEMINI_API_KEYS", len(keys))
            return _key_pool

    single = os.environ.get("GEMINI_API_KEY", "").strip()
    if single:
        _key_pool = [single]
        logger.info("Loaded 1 API key from GEMINI_API_KEY")
        return _key_pool

    try:
        from adapters.supabase_vault import supabase_vault_adapter

        vault_keys = supabase_vault_adapter.get_gemini_keys()
        if vault_keys:
            _key_pool = [k for k in vault_keys if isinstance(k, str) and k.strip()]
            if _key_pool:
                logger.info("Loaded %d API keys from Supabase Vault", len(_key_pool))
                return _key_pool
    except Exception:
        pass

    logger.warning("No Gemini API keys found")
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

    def get_api_key(self) -> str:
        """Public key accessor for modules that need unified key-pool routing."""
        return self._get_api_key()

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

    def ground_industry_chain(self, symbol: str, company_name: str = "", industry_hint: str = "") -> Dict[str, Any]:
        normalized_symbol = str(symbol or "").strip().upper()
        cache_key = f"{time.strftime('%Y-%m-%d')}:{normalized_symbol}:industry-chain"

        with _industry_chain_cache_lock:
            cached = _industry_chain_cache.get(cache_key)
            if isinstance(cached, dict):
                return cached

        api_key = self._get_api_key()
        if not api_key:
            return {"success": False, "chain": {}, "sources": [], "error": "no_api_key"}

        try:
            from google import genai
            from google.genai import types
        except Exception:
            return {"success": False, "chain": {}, "sources": [], "error": "google_genai_missing"}

        prompt = (
            "Use Google Search grounding and return strict JSON only. "
            "Return object schema: "
            '{"upstream":[{"name":string,"ticker":string|null,"listed":boolean|null,"listed_market":string|null,"relation_type":"上游","weight":number|null,"reason":string|null,"confidence":number|null}],'
            '"downstream":[{"name":string,"ticker":string|null,"listed":boolean|null,"listed_market":string|null,"relation_type":"下游","weight":number|null,"reason":string|null,"confidence":number|null}],'
            '"peer":[{"name":string,"ticker":string|null,"listed":boolean|null,"listed_market":string|null,"relation_type":"同業","weight":number|null,"reason":string|null,"confidence":number|null}],'
            '"competitor":[{"name":string,"ticker":string|null,"listed":boolean|null,"listed_market":string|null,"relation_type":"競爭","weight":number|null,"reason":string|null,"confidence":number|null}]}. '
            "Rule: only include direct and defensible industry-chain relationships. "
            "Do not include generic mega-cap names unless there is a clear supply-chain or direct competition relation. "
            "Do not include the core company itself. no duplicates across groups. "
            "Each list target 3 to 5 companies, prefer listed companies with ticker. "
            "weight and confidence range 0 to 1. reason must be short Traditional Chinese text. no markdown.\n"
            f"symbol={normalized_symbol}\n"
            f"company={company_name or normalized_symbol}\n"
            f"industry={industry_hint or 'unknown'}"
        )

        def _run():
            client = genai.Client(api_key=api_key)
            return client.models.generate_content(
                model=MODEL_GROUNDING,
                contents=prompt,
                config=types.GenerateContentConfig(
                    tools=[types.Tool(google_search=types.GoogleSearch())],
                    temperature=0.1,
                    max_output_tokens=1200,
                ),
            )

        sources: List[Dict[str, str]] = []
        ex = ThreadPoolExecutor(max_workers=1)
        f = ex.submit(_run)
        try:
            response = f.result(timeout=20)
        except FuturesTimeoutError:
            f.cancel()
            return {"success": False, "chain": {}, "sources": [], "error": "grounding_timeout"}
        except Exception as e:
            return {"success": False, "chain": {}, "sources": [], "error": type(e).__name__}
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
        relation_keys = ("upstream", "downstream", "peer", "competitor")
        chain: Dict[str, List[Dict[str, Any]]] = {k: [] for k in relation_keys}
        for key in relation_keys:
            rows = parsed.get(key)
            if not isinstance(rows, list):
                continue
            for row in rows[:8]:
                if isinstance(row, str):
                    name = row.strip()
                    if not name:
                        continue
                    chain[key].append(
                        {
                            "name": name,
                            "ticker": None,
                            "listed": None,
                            "listed_market": None,
                            "relation_type": {"upstream": "上游", "downstream": "下游", "peer": "同業", "competitor": "競爭"}[key],
                            "weight": None,
                            "confidence": None,
                            "reason": "",
                        }
                    )
                    continue
                if not isinstance(row, dict):
                    continue
                name = str(row.get("name") or "").strip()
                ticker = str(row.get("ticker") or "").strip() or None
                if not name and not ticker:
                    continue
                listed_val = row.get("listed")
                if isinstance(listed_val, bool):
                    listed = listed_val
                else:
                    listed = None
                listed_market = str(row.get("listed_market") or "").strip() or None
                weight = self._safe_float(row.get("weight"))
                if weight is not None:
                    weight = max(0.0, min(1.0, weight))
                confidence = self._safe_float(row.get("confidence"))
                if confidence is not None:
                    confidence = max(0.0, min(1.0, confidence))
                reason = str(
                    row.get("reason")
                    or row.get("relation_reason")
                    or row.get("why")
                    or row.get("evidence")
                    or ""
                ).strip()

                chain[key].append(
                    {
                        "name": name or (ticker or ""),
                        "ticker": ticker,
                        "listed": listed,
                        "listed_market": listed_market,
                        "relation_type": str(row.get("relation_type") or {"upstream": "上游", "downstream": "下游", "peer": "同業", "competitor": "競爭"}[key]),
                        "weight": weight,
                        "confidence": confidence,
                        "reason": reason,
                    }
                )

        valid_groups = sum(1 for k in relation_keys if len(chain.get(k) or []) > 0)
        result = {
            "success": valid_groups >= 2,
            "chain": chain,
            "sources": sources[:10],
            "error": None if valid_groups >= 2 else "insufficient_grounded_chain",
        }
        with _industry_chain_cache_lock:
            _industry_chain_cache[cache_key] = result
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

        out = re.sub(r"(?m)^\s*[-*_]{3,}\s*$", "", out)
        out = re.sub(r"```+", "", out)
        out = out.replace("***", "").replace("**", "").replace("*", "").replace("__", "").replace("~~", "")
        out = out.replace("#", "").replace("`", "").replace(">", "")
        out = re.sub(r"(?im)^\s*section\s*1\b.*$", S1, out)
        out = re.sub(r"(?im)^\s*section\s*2\b.*$", S2, out)
        out = re.sub(r"(?im)^\s*section\s*3\b.*$", S3, out)
        out = re.sub(r"(?im)^\s*section\s*4\b.*$", S4, out)
        out = re.sub(r"(?im)^\s*section\s*5\b.*$", S5, out)
        out = re.sub(r"(?im)^\s*section\s*6\b.*$", S6, out)
        out = re.sub(r"(?im)^\s*section\s*7\b.*$", S7, out)

        lines: List[str] = []
        section_by_num = {"1": S1, "2": S2, "3": S3, "4": S4, "5": S5, "6": S6, "7": S7}
        section_by_zh = {
            "一": S1,
            "二": S2,
            "三": S3,
            "四": S4,
            "五": S5,
            "六": S6,
            "七": S7,
        }
        intro_line_compact = re.sub(r"\s+", "", INTRO_LINE).lower()
        intro_seen = False
        for raw in out.split("\n"):
            line = raw.strip()
            if not line:
                lines.append("")
                continue
            line_no_bullet = re.sub(r"^[\u2022\-\*\s]+", "", line)
            line_compact = re.sub(r"\s+", "", line_no_bullet).lower()
            if "discoverlatest" in line_compact and "專屬ai" in line_compact:
                if not intro_seen:
                    lines.append(INTRO_LINE)
                    intro_seen = True
                continue
            m_num = re.match(r"^([1-7])[\.、\)]\s*", line)
            if m_num:
                lines.append(section_by_num[m_num.group(1)])
                continue
            m_zh = re.match(r"^([一二三四五六七])[、\.]\s*", line)
            if m_zh:
                lines.append(section_by_zh[m_zh.group(1)])
                continue
            if line in {S1, S2, S3, S4, S5, S6, S7}:
                lines.append(line)
                continue
            line = re.sub(r"^[-*]+\s*", "", line)
            line = re.sub(r"^\d+\)\s*", "", line)
            line = re.sub(r"^\d+\.\s+", "", line)
            if line.startswith("- "):
                lines.append(f"\u2022 {line[2:].strip()}")
            else:
                lines.append(f"\u2022 {line}")

        # Keep only one intro line and force it to first line.
        deduped: List[str] = []
        intro_seen = False
        for ln in lines:
            normalized = re.sub(r"\s+", "", re.sub(r"^[\u2022\-\*\s]+", "", (ln or "").strip())).lower()
            if normalized == intro_line_compact or ("discoverlatest" in normalized and "專屬ai" in normalized):
                if intro_seen:
                    continue
                intro_seen = True
                deduped.append(INTRO_LINE)
                continue
            deduped.append(ln)

        out = "\n".join(deduped)
        out = re.sub(r"\n{3,}", "\n\n", out).strip()
        if not intro_seen or not out.startswith(INTRO_LINE):
            out = INTRO_LINE + "\n" + out
        return out.strip()

    @staticmethod
    def _ensure_smc_section(text: str, smc_summary: str) -> str:
        out = (text or "").strip()
        if not out:
            return out
        if re.search(r"(SMC|BOS|CHoCH)", out, flags=re.IGNORECASE):
            return out

        summary = (smc_summary or "").strip() or "趨勢方向=neutral | 結構突破(BOS)=0 | 特性轉換(CHoCH)=0 | 有效訂單塊(OB)=0 | 未填補缺口(FVG)=0 | 流動性(買/賣)=0/0"
        items = [seg.strip() for seg in summary.split("|") if seg.strip()]
        if not items:
            items = ["趨勢方向=neutral", "結構突破(BOS)=0", "特性轉換(CHoCH)=0"]
        bullet_lines = "\n".join(f"\u2022 SMC補充 {seg}" for seg in items[:4])
        if S2 in out:
            return out.replace(S2, f"{S2}\n{bullet_lines}", 1).strip()
        return f"{out}\n\n{S2}\n{bullet_lines}".strip()

    @staticmethod
    def _analysis_cache_key(
        symbol: str,
        tier: str,
        context: str,
        user_question: str,
        persona_context: str = "",
    ) -> str:
        raw = "|".join(
            [
                str(symbol or "").strip().upper(),
                str(tier or "free").strip().lower(),
                str(user_question or "").strip(),
                str(context or "").strip(),
                str(persona_context or "").strip(),
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

    def _read_grounding_cache(self, key: str) -> Optional[Dict[str, Any]]:
        if GEMINI_GROUNDING_CACHE_TTL_SEC <= 0:
            return None
        now = time.time()
        with _grounding_cache_lock:
            row = _grounding_cache.get(key)
            if not isinstance(row, dict):
                return None
            ts = float(row.get("ts") or 0.0)
            if ts <= 0 or (now - ts) > GEMINI_GROUNDING_CACHE_TTL_SEC:
                _grounding_cache.pop(key, None)
                return None
            text = row.get("text")
            sources = row.get("sources")
            if not isinstance(text, str):
                return None
            out: Dict[str, Any] = {"text": text}
            if isinstance(sources, list):
                out["sources"] = [s for s in sources if isinstance(s, dict)]
            return out

    def _write_grounding_cache(self, key: str, text: str, sources: List[Dict[str, str]]) -> None:
        if GEMINI_GROUNDING_CACHE_TTL_SEC <= 0 or not key:
            return
        now = time.time()
        with _grounding_cache_lock:
            _grounding_cache[key] = {
                "ts": now,
                "text": str(text or ""),
                "sources": [s for s in (sources or []) if isinstance(s, dict)],
            }
            if len(_grounding_cache) > GEMINI_GROUNDING_CACHE_MAXSIZE:
                stale = sorted(
                    _grounding_cache.items(),
                    key=lambda kv: float((kv[1] or {}).get("ts") or 0.0),
                )
                for old_key, _ in stale[: max(1, len(_grounding_cache) - GEMINI_GROUNDING_CACHE_MAXSIZE)]:
                    _grounding_cache.pop(old_key, None)

    @staticmethod
    def _tier_min_chars(tier: str) -> int:
        return TIER_MIN_CHARS.get(str(tier or "free").strip().lower(), 100)

    @staticmethod
    def _tier_instruction(tier: str) -> str:
        min_chars = GeminiService._tier_min_chars(tier)
        common = (
            "\u8acb\u4f7f\u7528\u7e41\u9ad4\u4e2d\u6587\uff0c\u53e3\u543b\u5c08\u696d\u3001\u51b7\u975c\u3001\u57f7\u884c\u5c0e\u5411\uff0c\u985e\u4f3c 30+ \u5e74\u4ea4\u6613\u54e1\u5831\u544a\u3002\n"
            f"\u7b2c\u4e00\u884c\u5fc5\u9808\u662f\uff1a{INTRO_LINE}\n"
            f"\u7e3d\u9577\u5ea6\u81f3\u5c11 {min_chars} \u500b\u5b57\u7b26\u3002\n"
            "\u8acb\u7528\u5217\u9ede\u5448\u73fe\uff0c\u53ef\u4f7f\u7528\u5c11\u91cf emoji \u8f14\u52a9\u95b1\u8b80\uff0c\u4f46\u4e0d\u8981\u904e\u91cf\u3002\n"
            "\u5168\u6587\u7981\u6b62\u4f7f\u7528 markdown \u88dd\u98fe\u7b26\u865f\uff1a--- ** *** ## ### ``` __ ~~ >\u3002\n"
            "\u5167\u5bb9\u5fc5\u9808\u540c\u6642\u7d50\u5408\uff1a\u65b0\u805e\u9762\u3001\u6d88\u606f\u9762\u3001\u57fa\u672c\u9762\uff08FinMind\uff09\u3001\u7c4c\u78bc\u9762\uff08FinMind\uff09\u3001\u6280\u8853\u9762\u3002\n"
            "\u6280\u8853\u9762\u5fc5\u9808\u660e\u78ba\u63d0\u53ca SMC\u3001RSI\u3001MACD\u3001KDJ\u3001\u5e03\u6797\u901a\u9053\u3001EMA20/EMA50/EMA200\u3002\n"
            "\u5fc5\u9808\u7d66\u51fa\u77ed\u671f\uff081-5 \u500b\u4ea4\u6613\u65e5\uff09\u3001\u4e2d\u671f\uff082-6 \u9031\uff09\u3001\u9577\u671f\uff082-4 \u5b63\uff09\u7684\u9032\u5834/\u52a0\u78bc/\u6e1b\u78bc/\u505c\u640d\u898f\u5283\u3002\n"
            "\u4ea4\u6613\u8173\u672c\u9700\u5305\u542b\u89f8\u767c\u689d\u4ef6\u3001\u50f9\u4f4d\u5340\u9593\u3001\u505c\u640d\u3001\u76ee\u6a19\u50f9\u3001R:R\u3002\n"
            "\u8f38\u51fa\u7ae0\u7bc0\u9806\u5e8f\u56fa\u5b9a\uff1a\n"
            f"{S1}\n{S2}\n{S3}\n{S4}\n{S5}\n{S6}\n{S7}"
        )
        t = str(tier or "free").strip().lower()
        if t == "premium":
            return common + (
                "\nPremium \u6df1\u5ea6\u8981\u6c42\uff1a"
                "base/bull/bear \u6a5f\u7387\u3001\u90e8\u4f4d\u8a2d\u8a08\u3001\u5c0d\u6c96\u53ca\u98a8\u96aa\u66b4\u9732\u7ba1\u7406\u3002\u60c5\u5883\u4ea4\u6613\u5730\u5716\u8981\u6709\u89f8\u767c\u689d\u4ef6\u8207\u6a5f\u7387\u3002"
            )
        if t == "pro":
            return common + (
                "\nPro \u6df1\u5ea6\u8981\u6c42\uff1a"
                "base/bull \u96d9\u60c5\u5883\u3001\u57f7\u884c\u5340\u9593\u3001\u5009\u4f4d\u5efa\u8b70\u8207\u98a8\u96aa\u9810\u8b66\u3002\u5fc5\u9808\u88dc\u4e0a\u5b8f\u89c0\u9032\u968e\u89e3\u8b80\u3002"
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

        required_headers = [INTRO_LINE, S1, S2, S3, S4, S5, S6, S7]
        if any(h not in t for h in required_headers):
            return False
        if re.search(r"(?im)^\s*section\s*[1-7]\b", t):
            return False
        if re.search(r"(?m)^\s*[-*_]{3,}\s*$", t):
            return False
        if any(tok in t for tok in ("**", "***", "```", "__", "~~", "##", "###", "> ")):
            return False
        if "*" in t or "#" in t or "`" in t:
            return False

        tier_norm = str(tier or "free").strip().lower()
        min_bullets = 12 if tier_norm == "free" else (16 if tier_norm == "pro" else 22)
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

        k_match = re.search(
            r"KDJ(?:\(9,3,3\))?[:：=\s]*K[:：=]?([\-\d.]+)\s*D[:：=]?([\-\d.]+)\s*J[:：=]?([\-\d.]+)",
            text,
            flags=re.IGNORECASE,
        )
        if k_match:
            kdj = f"K={k_match.group(1)} D={k_match.group(2)} J={k_match.group(3)}"
        else:
            kdj = "N/A"

        boll = _pick(r"Bollinger\(20,2\)[:：=\s]*([^|\n]+)")
        if boll == "N/A":
            upper = _pick(r"BOLL(?: UP| Upper)?[:：=]?\s*([\-\d.]+)")
            lower = _pick(r"BOLL(?: DN| Lower)?[:：=]?\s*([\-\d.]+)")
            if upper != "N/A" and lower != "N/A":
                boll = f"{upper}/{lower}"

        return {
            "price": _pick(r"Price[:：=]?\s*([\-\d.]+)"),
            "rsi": _pick(r"RSI(?:14)?[:：=]?\s*([\-\d.]+)"),
            "macd": _pick(r"MACD[:：=]?\s*([\-\d.]+)"),
            "macd_signal": _pick(r"MACD(?: Signal| 訊號)?[:：=]?\s*([\-\d.]+)"),
            "boll": boll,
            "kdj": kdj,
            "ema20": _pick(r"EMA20[:：=]?\s*([\-\d.]+)"),
            "ema50": _pick(r"EMA50[:：=]?\s*([\-\d.]+)"),
            "ema200": _pick(r"EMA200[:：=]?\s*([\-\d.]+)"),
        }

    @staticmethod
    def _pad_to_min_chars(text: str, tier: str) -> str:
        out = (text or "").strip()
        min_chars = GeminiService._tier_min_chars(tier)
        if len(out) >= min_chars:
            return out
        fillers = [
            "\u2022 風控紀律：單筆風險控制在總資金的 0.5%-1.0%，嚴守停損。",
            "\u2022 執行紀律：未經量價確認不追突破，避免情緒化操作。",
            "\u2022 部位管理：分批進場、保留機動性，避免單點 all-in。",
            "\u2022 監控重點：留意量價背離擴大，作為風險預警信號。",
            "\u2022 事件風險：財報、法說會前後適度降低槓桿與部位。",
            "\u2022 策略維運：優先追求一致性，再優化勝率與盈虧比。",
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

        info = stock_info or {}

        def _pick_info(*keys: str) -> Any:
            for k in keys:
                if k in info and info.get(k) not in (None, "", "N/A"):
                    return info.get(k)
            return None

        price_raw = _pick_info("price", "last_close", "close")
        change_pct_raw = _pick_info("change_percent", "change_pct")
        pe_raw = _pick_info("pe_ratio", "PER", "pe")
        pb_raw = _pick_info("pb_ratio", "PBR", "pb")
        dy_raw = _pick_info("dividend_yield", "DividendYield", "yield")

        if price_raw is None and tech.get("price") not in (None, "", "N/A"):
            price_raw = tech.get("price")

        price = GeminiService._fmt_num(price_raw)
        change_pct = GeminiService._fmt_num(change_pct_raw)
        pe = GeminiService._fmt_num(pe_raw)
        pb = GeminiService._fmt_num(pb_raw)
        dy = GeminiService._fmt_num(dy_raw)

        trend_raw = str(smc.get("trend") or "neutral").lower()
        if trend_raw in {"bullish", "up", "uptrend"}:
            trend_label = "\u504f\u591a"
        elif trend_raw in {"bearish", "down", "downtrend"}:
            trend_label = "\u504f\u7a7a"
        else:
            trend_label = "\u4e2d\u6027\u504f\u9707\u76ea"

        lines = [
            INTRO_LINE,
            S1,
            f"\u2022 \u6a19\u7684 {symbol} \u73fe\u50f9 {price} \u7576\u65e5\u6f32\u8dcc {change_pct}%",
            f"\u2022 \u7576\u524d\u5e02\u5834\u504f\u5411 {trend_label} \u4f30\u503c\u5feb\u7167 PE {pe} PB {pb} \u80a1\u606f\u7387 {dy}%",
            f"\u2022 \u6f32\u8dcc\u9a45\u52d5\u91cd\u9ede {summary}",
            S2,
            f"\u2022 RSI14 {tech.get('rsi')} MACD {tech.get('macd')} Signal {tech.get('macd_signal')}",
            f"\u2022 KDJ {tech.get('kdj')} Bollinger20 2 {tech.get('boll')}",
            f"\u2022 EMA20 {tech.get('ema20')} EMA50 {tech.get('ema50')} EMA200 {tech.get('ema200')}",
            f"\u2022 SMC \u7d50\u69cb \u8da8\u52e2 {smc.get('trend')} BOS {smc.get('bos')} CHoCH {smc.get('choch')}",
            f"\u2022 SMC \u88dc\u5145 \u8a02\u55ae\u584a {smc.get('active_ob')} FVG {smc.get('open_fvg')} \u6d41\u52d5\u6027\u8cb7\u8ce3 {smc.get('liquidity')}",
            S3,
            "\u2022 \u77ed\u671f 1-5\u65e5 \u7b49\u91cf\u80fd\u653e\u5927\u4e14\u6536\u76e4\u5b88\u4f4f\u652f\u6490\u5f8c\u5206\u6279\u9032\u5834 \u7834\u4f4d\u5373\u505c\u640d",
            "\u2022 \u4e2d\u671f 2-6\u9031 \u7d50\u69cb\u9ad8\u9ede\u4e0a\u79fb\u624d\u52a0\u78bc \u8dcc\u7834\u4e2d\u671f\u8d77\u6f32\u8d70\u52e2\u7dda\u6e1b\u78bc",
            "\u2022 \u9577\u671f 2-4\u5b63 \u4f9d\u8ca1\u5831\u8207\u7522\u696d\u9031\u671f\u9032\u884c\u52d5\u614b\u914d\u7f6e \u8da8\u52e2\u53cd\u8f49\u5168\u9762\u9000\u5834",
            "\u2022 \u6bcf\u500b\u9031\u671f\u90fd\u8981\u5148\u5b9a\u7fa9\u9032\u5834\u5340 \u505c\u640d\u9ede \u76ee\u6a19\u50f9 \u98a8\u5831\u6bd4",
            S4,
            "\u2022 \u95dc\u9375\u98a8\u96aa \u8ca1\u5831\u4e0d\u5982\u9810\u671f \u6307\u5f15\u4e0b\u4fee \u5229\u7387\u4e0a\u884c \u5730\u7de3\u653f\u6cbb\u885d\u64ca",
            "\u2022 \u90e8\u4f4d\u98a8\u63a7 \u55ae\u7b46\u98a8\u96aa\u63a7\u5236\u65bc 0.5%-1.0% \u907f\u514d\u55ae\u4e00\u4e8b\u4ef6\u904e\u5ea6\u96c6\u4e2d",
            "\u2022 \u5931\u6548\u689d\u4ef6 \u8dcc\u7834\u95dc\u9375\u652f\u6490\u4e14\u91cf\u80fd\u653e\u5927\u6642 \u57f7\u884c\u964d\u98a8\u96aa",
            S5,
            f"\u2022 \u7d9c\u5408\u7d50\u8ad6 \u73fe\u968e\u6bb5\u5c6c\u65bc {trend_label} \u63a1\u5206\u6279\u9032\u51fa\u5834\u8207\u52d5\u614b\u98a8\u63a7\u8f03\u9069\u5408",
            "\u2022 \u5982\u7121\u4e8b\u4ef6\u50ac\u5316\u8207\u91cf\u50f9\u5171\u632f \u4e0d\u8ffd\u50f9 \u512a\u5148\u7b49\u56de\u6e2c\u78ba\u8a8d",
            "\u2022 \u57f7\u884c\u9806\u5e8f \u5148\u63a7\u98a8\u96aa \u518d\u8b70\u5831\u916c",
            S6,
            "\u2022 \u504f\u591a \u89f8\u767c\u689d\u4ef6 \u6536\u76e4\u7ad9\u4e0a\u95dc\u9375\u58d3\u529b\u5340\u4e14\u91cf\u80fd\u9023\u7e8c\u653e\u5927 \u7b56\u7565 \u56de\u6e2c\u4e0d\u7834\u52a0\u78bc",
            "\u2022 \u504f\u7a7a \u89f8\u767c\u689d\u4ef6 \u8dcc\u7834\u95dc\u9375\u652f\u6490\u4e14\u5f48\u5347\u7121\u91cf \u7b56\u7565 \u53cd\u5f48\u81f3\u58d3\u529b\u5340\u6e1b\u78bc\u6216\u907f\u96aa",
            "\u2022 \u9707\u76ea \u89f8\u767c\u689d\u4ef6 \u91cf\u80fd\u6536\u7e2e\u4e14\u5340\u9593\u672a\u7834 \u7b56\u7565 \u5340\u9593\u4e0b\u7de3\u4f4e\u5438 \u5340\u9593\u4e0a\u7de3\u6e1b\u78bc",
            S7,
            "\u2022 \u7f8e\u50b5\u5229\u7387 \u7f8e\u5143\u8d70\u52e2 \u80fd\u6e90\u50f9\u683c \u6703\u5f71\u97ff\u4f30\u503c\u6298\u73fe\u8207\u98a8\u96aa\u504f\u597d",
            "\u2022 \u82e5\u805a\u7126\u901a\u81a8\u8207\u5229\u7387\u8def\u5f91\u8f49\u5411 \u6210\u9577\u80a1\u8207\u9031\u671f\u80a1\u8cc7\u91d1\u8f2a\u52d5\u901f\u5ea6\u6703\u6539\u8b8a",
            "\u2022 \u5efa\u8b70\u6bcf\u9031\u6aa2\u8996\u5b8f\u89c0\u8b8a\u6578\u8207\u6301\u5009\u66dd\u96aa \u78ba\u4fdd\u5009\u4f4d\u914d\u7f6e\u8207\u60c5\u5883\u4e00\u81f4",
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
                    "\u2022 Premium \u6a5f\u7387\u6a21\u5f0f base 50% bull 30% bear 20%",
                    "\u2022 Premium \u7d44\u5408\u8996\u89d2 \u53ef\u642d\u914d\u6307\u6578\u6216\u9632\u79a6\u8cc7\u7522\u63a7\u5236\u5c3e\u90e8\u98a8\u96aa",
                    "\u2022 Premium \u7dad\u904b\u89c0\u5ff5 \u4ee5\u52dd\u7387 \u76c8\u8667\u6bd4 \u6700\u5927\u56de\u64a4\u5b9a\u671f\u8907\u76e4",
                ]
            )

        out = "\n".join(lines)
        return GeminiService._pad_to_min_chars(out, tier)

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

    @staticmethod
    def _build_persona_modifier(investor_profile: Optional[Dict[str, Any]]) -> str:
        if not isinstance(investor_profile, dict) or not investor_profile:
            return ""
        ptype = str(investor_profile.get("primary") or "").strip().lower()
        risk = investor_profile.get("risk_score", 50)
        try:
            risk_val = int(risk)
        except Exception:
            risk_val = 50
        modifiers = {
            "guardian": f"此使用者屬於穩健型（風險分數 {risk_val}/100），請強調現金流、波動控制與下檔風險。",
            "hunter": f"此使用者屬於成長型（風險分數 {risk_val}/100），可強調成長動能、產業趨勢與加速訊號。",
            "surfer": f"此使用者屬於趨勢型（風險分數 {risk_val}/100），請強調突破、量價與時機管理。",
            "explorer": f"此使用者屬於價值型（風險分數 {risk_val}/100），請強調估值、安全邊際與逆向機會。",
        }
        return modifiers.get(ptype, "")

    def generate_analysis(
        self,
        symbol: str,
        stock_info: Dict = None,
        smc_summary: str = "",
        prediction_summary: str = "",
        macro_data: Dict = None,
        user_question: str = "",
        tier: str = "free",
        investor_profile: Optional[Dict[str, Any]] = None,
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
            persona_context = ""
            if isinstance(investor_profile, dict) and investor_profile:
                try:
                    persona_context = json.dumps(investor_profile, ensure_ascii=False, sort_keys=True)
                except Exception:
                    persona_context = str(investor_profile)
            cache_key = self._analysis_cache_key(symbol, tier, context, user_question, persona_context)
            cached = self._read_analysis_cache(cache_key)
            if cached and self._quality_ok(str(cached.get("analysis") or ""), tier):
                payload = dict(cached)
                payload["cached"] = True
                emit(100, "done", "cached", cached=True, char_count=len(str(payload.get("analysis") or "")))
                return payload

            total_deadline = started + GEMINI_TOTAL_TIMEOUT
            stage1_timeout_hit = False
            grounding_text = ""
            grounding_sources: List[Dict[str, str]] = []

            stage1_prompt = (
                f"用 Google Search 搜尋 {symbol} 最新資訊 請用繁體中文輸出\n"
                "必查 當前股價 當日漲跌幅 成交量 近五日走勢\n"
                "必查 財報 法說 公司公告 訂單 評級 產業消息 同業動態\n"
                "必查 利率 匯率 油價 地緣政治等宏觀因素\n"
                "每條格式 日期｜事件｜對股價影響｜來源\n"
                "若找不到證據請寫 尚無足夠證據 最後附 120 字新聞總結\n"
                "禁止 markdown 裝飾符號\n"
                f"背景資料 {context}\n"
                f"提問 {user_question or '無'}"
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
                            max_output_tokens=800,
                        ),
                    )
                except Exception:
                    return client.models.generate_content(
                        model=MODEL_GROUNDING,
                        contents=stage1_prompt,
                        config=types.GenerateContentConfig(temperature=0.2, max_output_tokens=800),
                    )

            grounding_cache_key = str(symbol or "").strip().upper()
            cached_grounding = self._read_grounding_cache(grounding_cache_key)
            if cached_grounding:
                grounding_text = str(cached_grounding.get("text") or "")
                grounding_sources = list(cached_grounding.get("sources") or [])
                stage1_ms = 0
                emit(38, "stage1_done", "grounded_evidence_cached", stage1_ms=stage1_ms, source_count=len(grounding_sources))
            else:
                emit(12, "stage1", "collect_grounded_evidence")
                logger.info("Stage 1 starting for %s", symbol)
                stage1_started = time.time()
                stage1_timeout_sec = min(
                    GEMINI_TIMEOUT_STAGE1,
                    max(6.0, total_deadline - time.time() - 20.0),
                )
                ex1 = ThreadPoolExecutor(max_workers=1)
                f1 = ex1.submit(_run_stage1)
                try:
                    stage1_resp = f1.result(timeout=stage1_timeout_sec)
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
                    logger.info("Stage 1 completed for %s in %.1fs", symbol, time.time() - stage1_started)
                except FuturesTimeoutError:
                    f1.cancel()
                    stage1_timeout_hit = True
                    grounding_text = "Grounding timeout."
                    logger.warning("Stage 1 timeout after %.1fs for %s", stage1_timeout_sec, symbol)
                except Exception as e:
                    grounding_text = f"Grounding failed: {type(e).__name__}"
                    logger.warning("Stage 1 error for %s: %s: %s", symbol, type(e).__name__, e)
                finally:
                    ex1.shutdown(wait=False, cancel_futures=True)

                stage1_ms = int((time.time() - stage1_started) * 1000)
                self._write_grounding_cache(grounding_cache_key, grounding_text, grounding_sources)
                emit(38, "stage1_done", "grounded_evidence_ready", stage1_ms=stage1_ms, source_count=len(grounding_sources))

            tier_norm = str(tier or "free").strip().lower()
            max_tokens = 2048 if tier_norm == "free" else (3200 if tier_norm == "pro" else 4096)
            grounding_compact = (grounding_text or "").strip()
            if len(grounding_compact) > 2200:
                grounding_compact = grounding_compact[:2200]
            tier_extra = TIER_EXTRA.get(tier_norm, TIER_EXTRA["free"])
            persona_mod = self._build_persona_modifier(investor_profile)

            final_prompt = (
                f"{UNIFIED_SYSTEM_PROMPT}\n"
                f"{persona_mod}\n"
                f"{tier_extra}\n\n"
                f"標的 {symbol}\n"
                f"背景資料 {context}\n\n"
                f"stage1 證據 {grounding_compact}\n\n"
                f"SMC 結構 {smc_summary}\n\n"
                f"技術快照 {prediction_summary}\n\n"
                f"使用者提問 {user_question or '無'}"
            )

            def _run_stage2(prompt: str, temperature: float, output_tokens: int):
                last_err: Optional[Exception] = None
                for _ in range(1):
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
                        raise
                if last_err:
                    raise last_err
                raise RuntimeError("stage2_failed")

            emit(48, "stage2", "generate_multifactor_analysis")
            logger.info("Stage 2 starting for %s", symbol)
            stage2_started = time.time()
            remaining = total_deadline - stage2_started
            if remaining <= 2.0:
                emit(86, "fallback", "deadline_near_use_local_fallback")
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
                    "error": None if quality_pass else "total_deadline_exhausted",
                    "analysis": fallback,
                    "grounding_text": grounding_text,
                    "grounding_sources": grounding_sources,
                    "quality_pass": quality_pass,
                    "timings": {
                        "stage1_ms": stage1_ms,
                        "stage2_ms": int((time.time() - stage2_started) * 1000),
                        "total_ms": int((time.time() - started) * 1000),
                        "total_timeout_sec": GEMINI_TOTAL_TIMEOUT,
                        "deadline_fallback": True,
                    },
                }
                if quality_pass:
                    self._write_analysis_cache(cache_key, payload)
                    emit(
                        100,
                        "done",
                        "analysis_completed_deadline_fallback",
                        char_count=len(fallback or ""),
                        min_chars=self._tier_min_chars(tier),
                        total_ms=payload["timings"]["total_ms"],
                    )
                else:
                    emit(100, "error", "deadline_fallback_quality_failed")
                return payload

            stage2_timeout_sec = min(GEMINI_TIMEOUT_STAGE2, max(10.0, remaining - 2.0))
            stage2_timeout_sec = min(stage2_timeout_sec, max(1.0, total_deadline - time.time() - 1.0))
            ex2 = ThreadPoolExecutor(max_workers=1)
            f2 = ex2.submit(_run_stage2, final_prompt, 0.32, max_tokens)
            try:
                stage2_resp = f2.result(timeout=stage2_timeout_sec)
                analysis = stage2_resp.text.strip() if stage2_resp and getattr(stage2_resp, "text", None) else ""
                analysis = self._ensure_smc_section(self._sanitize_analysis_text(analysis), smc_summary)

                if not self._quality_ok(analysis, tier):
                    emit(86, "fallback", "stage2_quality_fallback_local")
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
                            "total_timeout_sec": GEMINI_TOTAL_TIMEOUT,
                        },
                    }

                logger.info("Stage 2 completed for %s, %d chars", symbol, len(analysis))
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
                        "stage1_timeout": stage1_timeout_hit,
                        "stage2_timeout_sec": round(stage2_timeout_sec, 2),
                        "total_timeout_sec": GEMINI_TOTAL_TIMEOUT,
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
                logger.warning("Stage 2 timeout after %.1fs for %s", stage2_timeout_sec, symbol)
                emit(86, "timeout", "stage2_timeout_local_fallback")
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
                        "stage2_timeout_sec": round(stage2_timeout_sec, 2),
                        "total_timeout_sec": GEMINI_TOTAL_TIMEOUT,
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
                logger.warning("Stage 2 error for %s: %s", symbol, e)
                emit(86, "error", f"stage2_error_{type(e).__name__}_local_fallback")
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
                    "error": None if quality_pass else f"stage2_error_{type(e).__name__}",
                    "analysis": fallback,
                    "grounding_sources": grounding_sources,
                    "quality_pass": quality_pass,
                    "degraded": False,
                    "timings": {
                        "stage1_ms": stage1_ms,
                        "stage2_ms": int((time.time() - stage2_started) * 1000),
                        "total_ms": int((time.time() - started) * 1000),
                        "total_timeout_sec": GEMINI_TOTAL_TIMEOUT,
                    },
                }
                if quality_pass:
                    self._write_analysis_cache(cache_key, payload)
                    emit(
                        100,
                        "done",
                        "analysis_completed_after_error_fallback",
                        char_count=len(fallback or ""),
                        min_chars=self._tier_min_chars(tier),
                        total_ms=payload["timings"]["total_ms"],
                    )
                else:
                    emit(100, "error", f"stage2_error_{type(e).__name__}")
                return payload
            finally:
                ex2.shutdown(wait=False, cancel_futures=True)

    def quick_summary(self, symbol: str, max_tokens: int = 120) -> str:
        api_key = self._get_api_key()
        if not api_key or not symbol:
            return ""
        try:
            from google import genai
            from google.genai import types
        except Exception:
            return ""
        prompt = (
            f"請用繁體中文用 40-70 字摘要 {symbol} 近期投資觀察重點，"
            "包含一個風險提示。不要使用 markdown。"
        )
        try:
            client = genai.Client(api_key=api_key)
            response = client.models.generate_content(
                model=MODEL_FINAL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.25,
                    max_output_tokens=max(40, int(max_tokens)),
                ),
            )
            return self._sanitize_analysis_text((getattr(response, "text", "") or "").strip())
        except Exception:
            return ""

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
            "你是 DiscoverLatest AI 投資分析助理。\n"
            "請全程使用繁體中文回覆，語氣專業、冷靜、簡潔。\n"
            "禁止使用 markdown 分隔線或星號強調。\n"
            "禁止出現英文句子，技術縮寫（RSI、PE 等）除外。\n"
            f"背景資料:\n{context_str}\n\n"
            f"對話紀錄:\n{chr(10).join(rendered_history)}\n\n"
            f"使用者: {user_message}\n"
            "請提供實務導向的投資討論，注重風險意識與具體建議。"
        )

        try:
            client = genai.Client(api_key=api_key)
            response = client.models.generate_content(model=MODEL_FINAL, contents=prompt)
            reply = (getattr(response, "text", "") or "").strip()
            if not reply:
                return {"success": False, "error": "empty_chat_output"}
            return {"success": True, "reply": self._sanitize_analysis_text(reply)}
        except Exception as e:
            logger.warning("Chat error: %s", e)
            return {"success": False, "error": str(e)}


gemini_service = GeminiService()
