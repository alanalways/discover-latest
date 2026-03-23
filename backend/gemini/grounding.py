"""
backend/gemini/grounding.py
Batch Grounding Agent — 每次分析只消耗 1 次 Gemini text RPD

架構說明：
  舊版：event/macro/sentiment 三個 Agent 各自呼叫 Gemini grounding（3 次 RPD）
  新版：BatchGroundingAgent 一次 Gemini 呼叫取回三份資料（1 次 RPD）
        → event_data / macro_data / sentiment_data 傳給 NVIDIA agents 分析

快取：同股票同天 4 小時 TTL（使用 backend/gemini/cache.py）
配額：消耗 1 text RPD + 1 grounding RPD，每天最多 20 次（受 RPD=20 限制）
"""
import json
import logging
from typing import Optional

from backend.gemini.client import call_gemini
from backend.gemini.cache import get_cached_grounding, set_grounding_cache

logger = logging.getLogger(__name__)

# Batch Grounding 的 Prompt 模板
_BATCH_GROUNDING_PROMPT = """你是一位精準的金融資料蒐集員。
請針對股票代號 {symbol}（{market} 市場）搜尋以下三類最新資訊，
以 JSON 格式輸出，不要輸出任何 JSON 以外的文字。


必須輸出以下結構：
{{
  "event_data": {{
    "recent_earnings": "最近一季財報摘要（EPS、營收、年增率）",
    "investor_conference": "最近法說會重點（若無則填 null）",
    "major_announcements": ["重大訊息1", "重大訊息2"],
    "analyst_ratings": "近期分析師評級變動（若無則填 null）",
    "policy_impact": "相關政策衝擊（若無則填 null）"
  }},
  "macro_data": {{
    "us_market": "美股三大指數近期表現與傳導效應",
    "vix": "VIX 恐慌指數水準與趨勢",
    "fed_rate": "Fed 利率預期與最新動態",
    "usd_twd": "美元兌台幣匯率（若為台股）或美元指數（若為美股）",
    "sector_rotation": "所屬板塊近期輪動方向"
  }},
  "sentiment_data": {{
    "social_sentiment": "社群媒體（PTT/Dcard/Twitter）整體情緒：正面/中性/負面",
    "google_trends": "Google Trends 搜尋趨勢（上升/平穩/下降）",
    "retail_confidence": "散戶信心指標描述",
    "fear_greed_index": "恐慌貪婪指數水準（0-100，100最貪婪）"
  }},
  "data_freshness": "資料截止日期（YYYY-MM-DD 格式）"
}}

重要：
- 只輸出純 JSON，不要 markdown 符號（不要 ```json）
- 若某項資訊搜尋不到，填 null 而非省略欄位
- 財報數字請標明貨幣單位
"""

# ── 多股票批次 Grounding Prompt ───────────────────────────────────────────────
_MULTI_STOCK_GROUNDING_PROMPT = """你是一位精準的金融資料蒐集員。
請針對以下 {n} 支股票，分別搜尋最新的事件、宏觀環境、市場情緒三類資訊。
以 JSON 格式輸出，不要輸出任何 JSON 以外的文字。

股票清單：
{stock_list}

必須輸出以下結構（以「代號:市場」為 key）：
{{
  "results": {{
    "SYMBOL1:MARKET1": {{
      "event_data": {{
        "recent_earnings": "最近一季財報摘要（EPS、營收、年增率）",
        "investor_conference": "最近法說會重點（若無則填 null）",
        "major_announcements": ["重大訊息1", "重大訊息2"],
        "analyst_ratings": "近期分析師評級變動（若無則填 null）",
        "policy_impact": "相關政策衝擊（若無則填 null）"
      }},
      "macro_data": {{
        "us_market": "美股三大指數近期表現與傳導效應",
        "vix": "VIX 恐慌指數水準與趨勢",
        "fed_rate": "Fed 利率預期與最新動態",
        "usd_twd": "美元兌台幣匯率（若為台股）或美元指數（若為美股）",
        "sector_rotation": "所屬板塊近期輪動方向"
      }},
      "sentiment_data": {{
        "social_sentiment": "社群媒體整體情緒：正面/中性/負面",
        "google_trends": "Google Trends 搜尋趨勢（上升/平穩/下降）",
        "retail_confidence": "散戶信心指標描述",
        "fear_greed_index": "恐慌貪婪指數水準（0-100，100最貪婪）"
      }},
      "data_freshness": "YYYY-MM-DD"
    }},
    "SYMBOL2:MARKET2": {{ ... }}
  }}
}}

重要：
- 只輸出純 JSON，不要 markdown 符號（不要 ```json）
- 宏觀資料（us_market/vix/fed_rate）可跨股票共用相同基礎描述，但 sector_rotation/usd_twd 依股票調整
- 若某項資訊搜尋不到，填 null 而非省略欄位
- 財報數字請標明貨幣單位
"""


class BatchGroundingAgent:
    """
    批次 Grounding Agent。

    一次 Gemini 呼叫取回 event / macro / sentiment 三份資料，
    再交給 NVIDIA agents 進行分析。
    節省：3 次 Gemini RPD → 1 次 Gemini RPD。
    """

    def fetch_all(
        self,
        symbol: str,
        market: str,
        report_id: Optional[str] = None,
    ) -> dict:
        """
        執行 Batch Grounding，取回三份資料。

        先查快取（同股票同天 4 小時 TTL），命中直接回傳。
        未命中則呼叫 Gemini（使用 Google Search grounding）。

        Args:
            symbol:    股票代號（例：2330）
            market:    市場（TW / TWO / US）
            report_id: 關聯報告 ID（用於 audit_log）

        Returns:
            {
                "event_data":     {...},
                "macro_data":     {...},
                "sentiment_data": {...},
                "data_freshness": "YYYY-MM-DD",
                "_from_cache":    bool,
                "_error":         str | None,
            }
        """
        cache_key = f"{symbol.upper()}_{market.upper()}"

        # ── 查快取 ───────────────────────────────────────
        cached = get_cached_grounding(symbol, "batch_all")
        if cached:
            logger.info(f"[BatchGrounding] {symbol} 快取命中，跳過 Gemini 呼叫")
            return {**cached, "_from_cache": True, "_error": None}

        # ── 呼叫 Gemini（1 次 RPD）──────────────────────
        prompt = _BATCH_GROUNDING_PROMPT.format(
            symbol=symbol.upper(),
            market=market.upper(),
        )

        logger.info(f"[BatchGrounding] {symbol} 呼叫 Gemini grounding...")
        result = call_gemini(
            agent_name="batch_grounding",
            prompt=prompt,
            use_grounding=True,
            report_id=report_id,
        )

        if result["status"] != "success" or not result.get("output"):
            error_msg = result.get("error") or result["status"]
            logger.error(f"[BatchGrounding] {symbol} Gemini 呼叫失敗: {error_msg}")
            return _empty_grounding_data(error=error_msg)

        # ── 解析 JSON 輸出 ───────────────────────────────
        raw_output = result["output"].strip()
        # 移除可能的 markdown code block
        if raw_output.startswith("```"):
            lines = raw_output.split("\n")
            raw_output = "\n".join(
                l for l in lines
                if not l.startswith("```")
            ).strip()

        try:
            parsed = json.loads(raw_output)
        except json.JSONDecodeError as e:
            logger.error(
                f"[BatchGrounding] {symbol} JSON 解析失敗: {e}\n"
                f"原始輸出: {raw_output[:500]}..."
            )
            return _empty_grounding_data(
                raw_output=raw_output,
                error=f"JSON parse failed: {e}",
            )

        grounding_data = {
            "event_data":     parsed.get("event_data", {}),
            "macro_data":     parsed.get("macro_data", {}),
            "sentiment_data": parsed.get("sentiment_data", {}),
            "data_freshness": parsed.get("data_freshness", ""),
        }

        # ── 寫入快取（4 小時 TTL）───────────────────────
        set_grounding_cache(symbol, "batch_all", grounding_data)

        logger.info(
            f"[BatchGrounding] {symbol} grounding 完成，"
            f"耗時 {result.get('duration_ms', 0)}ms"
        )

        return {**grounding_data, "_from_cache": False, "_error": None}

    def fetch_batch(
        self,
        symbols_markets: list[tuple[str, str]],
        report_id: Optional[str] = None,
    ) -> dict[str, dict]:
        """
        批次 Grounding：一次 Gemini 呼叫，同時取回多支股票的資料。

        主要用途：背景佇列在處理多個分析工作前，預先暖快取。
        各股票資料寫入快取後，_run_analysis 呼叫 fetch_all() 時直接命中快取。

        Args:
            symbols_markets: [(symbol, market), ...] 最多 8 支（太多會超出 Gemini context）
            report_id:        關聯報告 ID（可選）

        Returns:
            dict keyed by "SYMBOL:MARKET" → grounding data
            （同時將各筆資料寫入快取，供後續 fetch_all 命中）
        """
        if not symbols_markets:
            return {}

        # 每批最多 8 支（避免 prompt 過長）
        batch = symbols_markets[:8]

        # 檢查快取：已有快取的跳過，只 Gemini 查詢沒快取的
        missing: list[tuple[str, str]] = []
        cached_results: dict[str, dict] = {}
        for sym, mkt in batch:
            cached = get_cached_grounding(sym, "batch_all")
            key = f"{sym.upper()}:{mkt.upper()}"
            if cached:
                cached_results[key] = cached
                logger.debug(f"[BatchGrounding] {sym} 快取命中（批次），跳過")
            else:
                missing.append((sym, mkt))

        if not missing:
            logger.info(f"[BatchGrounding] 批次所有 {len(batch)} 支快取命中，無需 Gemini")
            return cached_results

        # 建立股票清單說明
        stock_lines = "\n".join(
            f"- {sym.upper()}（{mkt.upper()} 市場）"
            for sym, mkt in missing
        )
        prompt = _MULTI_STOCK_GROUNDING_PROMPT.format(
            n=len(missing),
            stock_list=stock_lines,
        )

        logger.info(
            f"[BatchGrounding] 批次 Gemini 呼叫：{len(missing)} 支 "
            f"({[s for s, _ in missing]})..."
        )
        result = call_gemini(
            agent_name="batch_grounding",
            prompt=prompt,
            use_grounding=True,
            report_id=report_id,
        )

        if result["status"] != "success" or not result.get("output"):
            error_msg = result.get("error") or result["status"]
            logger.error(f"[BatchGrounding] 批次 Gemini 失敗: {error_msg}")
            # 返回已快取的部分 + 空值
            for sym, mkt in missing:
                key = f"{sym.upper()}:{mkt.upper()}"
                cached_results[key] = _empty_grounding_data(error=error_msg)
            return cached_results

        # 解析 JSON
        raw_output = result["output"].strip()
        if raw_output.startswith("```"):
            lines = raw_output.split("\n")
            raw_output = "\n".join(
                l for l in lines if not l.startswith("```")
            ).strip()

        try:
            parsed = json.loads(raw_output)
        except json.JSONDecodeError as e:
            logger.error(f"[BatchGrounding] 批次 JSON 解析失敗: {e}\n{raw_output[:300]}...")
            for sym, mkt in missing:
                key = f"{sym.upper()}:{mkt.upper()}"
                cached_results[key] = _empty_grounding_data(error=f"JSON parse: {e}")
            return cached_results

        results_map = parsed.get("results", {})
        logger.info(
            f"[BatchGrounding] 批次完成，耗時 {result.get('duration_ms', 0)}ms，"
            f"取回 {len(results_map)} 支資料"
        )

        # 寫入快取，回傳結果
        for sym, mkt in missing:
            key = f"{sym.upper()}:{mkt.upper()}"
            # 嘗試不同的 key 格式（有些 LLM 只輸出代號不帶市場）
            stock_data = (
                results_map.get(key)
                or results_map.get(f"{sym.upper()}:{mkt.upper()}")
                or results_map.get(sym.upper())
                or {}
            )
            grounding_data = {
                "event_data":     stock_data.get("event_data", {}),
                "macro_data":     stock_data.get("macro_data", {}),
                "sentiment_data": stock_data.get("sentiment_data", {}),
                "data_freshness": stock_data.get("data_freshness", ""),
            }
            # 寫入快取（供後續 fetch_all 命中）
            set_grounding_cache(sym, "batch_all", grounding_data)
            cached_results[key] = grounding_data

        return cached_results


def _empty_grounding_data(
    error: Optional[str] = None,
    raw_output: Optional[str] = None,
) -> dict:
    """回傳空白 grounding 資料結構（Gemini 失敗時使用）。"""
    return {
        "event_data": {
            "recent_earnings":      None,
            "investor_conference":  None,
            "major_announcements":  [],
            "analyst_ratings":      None,
            "policy_impact":        None,
        },
        "macro_data": {
            "us_market":        None,
            "vix":              None,
            "fed_rate":         None,
            "usd_twd":          None,
            "sector_rotation":  None,
        },
        "sentiment_data": {
            "social_sentiment":  None,
            "google_trends":     None,
            "retail_confidence": None,
            "fear_greed_index":  None,
        },
        "data_freshness": None,
        "_from_cache":    False,
        "_error":         error,
        "_raw_output":    raw_output,
    }


# ── 保留輔助函式（供前端顯示 grounding 來源）─────────────

def extract_grounding_sources(response_metadata) -> list[dict]:
    """
    從 Gemini response metadata 中提取 grounding 來源連結。
    供 audit_log 或前端顯示使用。
    """
    sources = []
    try:
        if not response_metadata:
            return sources
        grounding_metadata = getattr(response_metadata, "grounding_metadata", None)
        if not grounding_metadata:
            return sources
        for chunk in getattr(grounding_metadata, "grounding_chunks", []):
            web = getattr(chunk, "web", None)
            if web:
                sources.append({
                    "title": getattr(web, "title", ""),
                    "uri": getattr(web, "uri", ""),
                })
    except Exception as e:
        logger.debug(f"[Grounding] 無法提取來源: {e}")
    return sources


def format_grounding_disclaimer(sources: list[dict]) -> str:
    """將 grounding 來源格式化為報告末尾的免責聲明文字。"""
    if not sources:
        return ""
    lines = ["\n\n---\n**資料來源（Google Search Grounding）**"]
    for i, src in enumerate(sources[:5], 1):
        title = src.get("title", "未知來源")
        uri = src.get("uri", "")
        if uri:
            lines.append(f"{i}. [{title}]({uri})")
        else:
            lines.append(f"{i}. {title}")
    return "\n".join(lines)
