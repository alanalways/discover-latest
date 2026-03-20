"""
backend/agents/pipeline.py
並行分析 Pipeline 調度器

架構：3 階段 Pipeline，目標 30-60 秒
  Stage 1: 資料收集（asyncio.gather 並行）       → 3-5s
  Stage 2: 6 Agent 全部並行（ThreadPoolExecutor） → 10-15s
  Stage 3: Arbitrator → Chief Analyst (streaming)  → 15-25s

Fast Path 回傳報告給使用者後，Background Path 異步處理：
  - DB 寫入 (reports, predictions)
  - audit_log
  - LINE 通知
"""
import json
import time
import logging
import asyncio
from concurrent.futures import ThreadPoolExecutor, as_completed
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
from backend.data.sources.yahoo import get_price_data as fetch_price_data
from backend.data.sources.finmind import (
    get_institutional_investors as fetch_institutional_data,
    get_price_data as fetch_fundamental_data,
)

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

# 並行上限：6 個 Agent 同時跑
_AGENT_POOL_SIZE = 6


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
        price_data, institutional, fundamentals = await asyncio.gather(
            asyncio.to_thread(fetch_price_data, symbol, market),
            asyncio.to_thread(fetch_institutional_data, symbol, market),
            asyncio.to_thread(fetch_fundamental_data, symbol, market),
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
        institutional=institutional,
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
        _arbitrator.arbitrate, dept_results, report_id=report_id
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
    institutional: dict,
    fundamentals: dict,
) -> dict:
    """
    6 個 Agent 全部並行執行。

    無 grounding 的 Agent（technical, fundamental, chips）使用傳入的資料。
    有 grounding 的 Agent（event, macro, sentiment）先查快取，未命中才呼叫 Gemini。
    """

    def _run_agent(agent, agent_name: str, **kwargs) -> tuple[str, dict]:
        """在 ThreadPool 中執行單一 Agent。"""
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

    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor(max_workers=_AGENT_POOL_SIZE) as pool:
        futures = {
            loop.run_in_executor(pool, _run_agent, _technical, "technical",
                                 **{"price_data": price_data}):
                "technical",
            loop.run_in_executor(pool, _run_agent, _fundamental, "fundamental",
                                 **{"fundamentals": fundamentals}):
                "fundamental",
            loop.run_in_executor(pool, _run_agent, _chips, "chips",
                                 **{"institutional": institutional}):
                "chips",
            loop.run_in_executor(pool, _run_agent, _event, "event"):
                "event",
            loop.run_in_executor(pool, _run_agent, _macro, "macro"):
                "macro",
            loop.run_in_executor(pool, _run_agent, _sentiment, "sentiment"):
                "sentiment",
        }

        dept_results = {}
        for future in asyncio.as_completed(futures):
            agent_name, result = await future
            dept_results[agent_name] = result

    return dept_results
