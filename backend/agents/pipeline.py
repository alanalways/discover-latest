"""
backend/agents/pipeline.py
並行分析 Pipeline 調度器

架構：3 階段 Pipeline，目標 30-60 秒
  Stage 1: 資料收集（asyncio.gather 並行）       → 3-5s
  Stage 2: 6 Agent 全部並行（ThreadPoolExecutor） → 10-15s
  Stage 3: Arbitrator → Chief Analyst (streaming)  → 15-25s

資料來源策略：
  - FinMind 為主要來源（台股+美股價格、台股法人/融資/基本面）
  - Yahoo Finance 為備援（FinMind 失敗時 fallback）

Fast Path 回傳報告給使用者後，Background Path 異步處理：
  - DB 寫入 (reports, predictions)
  - audit_log
  - LINE 通知
"""
import time
import logging
import asyncio
from typing import AsyncGenerator, Optional
from uuid import uuid4

from backend.agents.departments.technical import TechnicalAgent
from backend.agents.departments.fundamental import FundamentalAgent
from backend.agents.departments.chips import ChipsAgent
from backend.agents.departments.event import EventAgent
from backend.agents.departments.macro import MacroAgent
from backend.agents.departments.sentiment import SentimentAgent
from backend.agents.arbitrator import ArbitratorAgent
from backend.agents.chief_analyst import ChiefAnalystAgent
from backend.gemini.cache import get_cached_grounding, set_grounding_cache

logger = logging.getLogger(__name__)

# Agent 實例（重複使用，不每次建新的）
_technical = TechnicalAgent()
_fundamental = FundamentalAgent()
_chips = ChipsAgent()
_event = EventAgent()
_macro = MacroAgent()
_sentiment = SentimentAgent()
_arbitrator = ArbitratorAgent()
_chief = ChiefAnalystAgent()


# ─────────────────────────────────────────────────────────
# 資料收集：FinMind 為主，Yahoo 為備
# ─────────────────────────────────────────────────────────

def _fetch_price_data(symbol: str, market: str) -> dict:
    """價格資料：FinMind 優先，Yahoo fallback"""
    if market in ("TW", "TWO"):
        # 台股：FinMind 主力
        from backend.data.sources.finmind import get_price_data as fm_price
        data = fm_price(symbol, days=120)
        if data.get("closes") and not data.get("error"):
            return data
        logger.warning(f"[Pipeline] FinMind 價格失敗，fallback Yahoo: {symbol}")

    # 美股或 FinMind 失敗 → Yahoo
    try:
        from backend.data.sources.yahoo import get_price_data as yf_price
        return yf_price(symbol, market)
    except Exception as e:
        logger.error(f"[Pipeline] Yahoo 價格也失敗: {symbol} {e}")
        return {"symbol": symbol, "market": market, "error": str(e),
                "dates": [], "opens": [], "highs": [], "lows": [],
                "closes": [], "volumes": []}


def _fetch_chips_data(symbol: str, market: str) -> dict:
    """籌碼資料：FinMind（台股專屬）"""
    if market not in ("TW", "TWO"):
        return {"symbol": symbol, "error": "非台股無籌碼資料",
                "foreign_net": [], "trust_net": [], "dealer_net": [],
                "margin_balance": [], "short_balance": [], "dates": []}

    from backend.data.sources.finmind import get_chips_data
    data = get_chips_data(symbol, days=30)
    return data


def _fetch_fundamentals(symbol: str, market: str) -> dict:
    """基本面：台股用 FinMind，美股用 Yahoo"""
    if market in ("TW", "TWO"):
        from backend.data.sources.finmind import get_fundamentals as fm_fund
        data = fm_fund(symbol)
        if not data.get("error") or data.get("per") or data.get("name") != symbol:
            return data
        logger.warning(f"[Pipeline] FinMind 基本面不完整，fallback Yahoo: {symbol}")

    # 美股或 fallback
    try:
        from backend.data.sources.yahoo import get_info as yf_info
        return yf_info(symbol, market)
    except Exception as e:
        logger.error(f"[Pipeline] Yahoo 基本面也失敗: {symbol} {e}")
        return {"symbol": symbol, "market": market, "error": str(e)}


# ─────────────────────────────────────────────────────────
# 主 Pipeline
# ─────────────────────────────────────────────────────────

async def fast_analysis(
    symbol: str,
    market: str = "TW",
    user_id: Optional[str] = None,
) -> AsyncGenerator[dict, None]:
    """
    Fast Path：使用者等待的主 Pipeline。

    透過 SSE 逐段推送：
      {"type": "status", "stage": "data", "message": "正在收集資料..."}
      {"type": "status", "stage": "agents", "message": "6 位分析師並行分析中..."}
      {"type": "status", "stage": "arbitration", "message": "仲裁官整合中..."}
      {"type": "chunk", "content": "報告文字片段..."}
      {"type": "done", "report_id": "xxx", "meta": {...}}
    """
    pipeline_start = time.time()
    report_id = str(uuid4())

    # ── Stage 1: 資料收集（並行）──────────────────────────
    yield {"type": "status", "stage": "data", "message": "正在收集市場資料..."}

    stage1_start = time.time()
    try:
        price_data, chips_data, fundamentals = await asyncio.gather(
            asyncio.to_thread(_fetch_price_data, symbol, market),
            asyncio.to_thread(_fetch_chips_data, symbol, market),
            asyncio.to_thread(_fetch_fundamentals, symbol, market),
        )
    except Exception as e:
        logger.error(f"[Pipeline] 資料收集失敗: {e}")
        yield {"type": "error", "message": f"資料收集失敗: {e}"}
        return

    stage1_ms = int((time.time() - stage1_start) * 1000)
    logger.info(f"[Pipeline] Stage 1 資料收集完成: {stage1_ms}ms")

    # ── Stage 2: 6 Agent 全部並行 ─────────────────────────
    yield {
        "type": "status",
        "stage": "agents",
        "message": "6 位分析師並行分析中...",
    }

    stage2_start = time.time()
    dept_results = await _run_agents_parallel(
        symbol=symbol,
        market=market,
        report_id=report_id,
        price_data=price_data,
        chips_data=chips_data,
        fundamentals=fundamentals,
    )
    stage2_ms = int((time.time() - stage2_start) * 1000)

    success_count = sum(
        1 for r in dept_results.values()
        if r.get("status") == "success" or "raw" in r or "trend" in r
    )
    logger.info(
        f"[Pipeline] Stage 2 完成: {success_count}/6 成功, {stage2_ms}ms"
    )

    # ── Stage 3a: Arbitrator ──────────────────────────────
    yield {
        "type": "status",
        "stage": "arbitration",
        "message": "仲裁官整合分析結果中...",
    }

    stage3_start = time.time()
    arbitration = await asyncio.to_thread(
        _arbitrator.arbitrate,
        technical=dept_results.get("technical", {}),
        fundamental=dept_results.get("fundamental", {}),
        chips=dept_results.get("chips", {}),
        event=dept_results.get("event", {}),
        macro=dept_results.get("macro", {}),
        sentiment=dept_results.get("sentiment", {}),
        report_id=report_id,
    )
    stage3a_ms = int((time.time() - stage3_start) * 1000)
    logger.info(f"[Pipeline] Stage 3a 仲裁完成: {stage3a_ms}ms")

    # ── Stage 3b: Chief Analyst（streaming）───────────────
    yield {
        "type": "status",
        "stage": "report",
        "message": "首席分析師正在撰寫報告...",
    }

    stage3b_start = time.time()
    report_chunks = []

    for chunk in _chief.stream_report(
        dept_results=dept_results,
        arbitration=arbitration,
        symbol=symbol,
        market=market,
        report_id=report_id,
    ):
        report_chunks.append(chunk)
        yield {"type": "chunk", "content": chunk}

    stage3b_ms = int((time.time() - stage3b_start) * 1000)
    total_ms = int((time.time() - pipeline_start) * 1000)
    full_report = "".join(report_chunks)

    logger.info(
        f"[Pipeline] 完成! 總計 {total_ms}ms "
        f"(資料={stage1_ms}ms, 6Agent={stage2_ms}ms, "
        f"仲裁={stage3a_ms}ms, 報告={stage3b_ms}ms)"
    )

    # ── 完成信號 + 元資料 ────────────────────────────────
    yield {
        "type": "done",
        "report_id": report_id,
        "final_report": full_report,
        "rating": arbitration.get("final_stance"),
        "confidence": arbitration.get("stance_confidence"),
        "meta": {
            "symbol": symbol,
            "market": market,
            "total_ms": total_ms,
            "stage1_data_ms": stage1_ms,
            "stage2_agents_ms": stage2_ms,
            "stage3a_arbitration_ms": stage3a_ms,
            "stage3b_report_ms": stage3b_ms,
            "agents_success": success_count,
            "final_stance": arbitration.get("final_stance"),
            "stance_confidence": arbitration.get("stance_confidence"),
        },
        "report_data": {
            "report_id": report_id,
            "symbol": symbol,
            "market": market,
            "full_report": full_report,
            "dept_results": dept_results,
            "arbitration": arbitration,
            "user_id": user_id,
        },
    }


async def _run_agents_parallel(
    symbol: str,
    market: str,
    report_id: str,
    price_data: dict,
    chips_data: dict,
    fundamentals: dict,
) -> dict:
    """
    6 個 Agent 全部並行執行。

    無 grounding 的 Agent（technical, fundamental, chips）使用傳入的資料。
    有 grounding 的 Agent（event, macro, sentiment）先查快取，未命中才呼叫 Gemini。
    """

    def _run_agent(agent, agent_name: str, **kwargs) -> tuple[str, dict]:
        """在背景執行緒中執行單一 Agent。"""
        try:
            # Grounding Agent 先查快取
            if hasattr(agent, 'use_grounding') and agent.use_grounding:
                cached = get_cached_grounding(symbol, agent_name)
                if cached is not None:
                    logger.info(f"[Pipeline] {agent_name} 使用快取結果")
                    return (agent_name, cached)

            result = agent.analyze(
                symbol=symbol,
                market=market,
                report_id=report_id,
                **kwargs,
            )

            # Grounding Agent 結果寫入快取
            if hasattr(agent, 'use_grounding') and agent.use_grounding:
                if result.get("status") != "failed":
                    set_grounding_cache(symbol, agent_name, result)

            return (agent_name, result)
        except Exception as e:
            logger.error(f"[Pipeline] {agent_name} 執行失敗: {e}")
            return (agent_name, {"status": "failed", "error": str(e)})

    # 取得產業資訊（供 MacroAgent 使用）
    industry = fundamentals.get("industry") or fundamentals.get("sector") or "科技"

    results = await asyncio.gather(
        asyncio.to_thread(_run_agent, _technical, "technical",
                          price_data=price_data),
        asyncio.to_thread(_run_agent, _fundamental, "fundamental",
                          financial_data=fundamentals),
        asyncio.to_thread(_run_agent, _chips, "chips",
                          chips_data=chips_data),
        asyncio.to_thread(_run_agent, _event, "event"),
        asyncio.to_thread(_run_agent, _macro, "macro",
                          industry=industry),
        asyncio.to_thread(_run_agent, _sentiment, "sentiment"),
    )

    return {name: result for name, result in results}
