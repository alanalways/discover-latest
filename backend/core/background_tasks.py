"""
backend/core/background_tasks.py

分析完成後的背景任務：
- 寫入 reports
- 寫入 predictions
- 留痕 pipeline 結果
"""

import asyncio
import logging
from typing import Optional

from backend.core.audit_log import log_agent_action
from backend.data.storage.supabase_client import get_client

logger = logging.getLogger(__name__)


async def save_report_to_db(report_data: dict) -> Optional[str]:
    """將完整報告寫入 reports。"""
    try:
        client = get_client()
        if not client:
            logger.error("[Background] Supabase client unavailable")
            return None

        structured = report_data.get("structured_data") or {}
        arbitration = report_data.get("arbitration") or {}

        row = {
            "id": report_data["report_id"],
            "symbol": report_data["symbol"],
            "market": report_data["market"],
            "report_type": "full_analysis",
            "tier": "standard",
            "technical_output": report_data["dept_results"].get("technical"),
            "fundamental_output": report_data["dept_results"].get("fundamental"),
            "chips_output": report_data["dept_results"].get("chips"),
            "event_output": report_data["dept_results"].get("event"),
            "macro_output": report_data["dept_results"].get("macro"),
            "sentiment_output": report_data["dept_results"].get("sentiment"),
            "arbitration_log": arbitration,
            "final_report": report_data["full_report"],
            "rating": structured.get("rating") or arbitration.get("final_stance"),
            "target_price_low": structured.get("target_price_low"),
            "target_price_high": structured.get("target_price_high"),
            "confidence_score": arbitration.get("stance_confidence"),
            "triggered_by": "user",
            "user_id": report_data.get("user_id"),
        }

        await asyncio.to_thread(lambda: client.table("reports").insert(row).execute())
        logger.info("[Background] report saved: %s", report_data["report_id"])
        return report_data["report_id"]
    except Exception as exc:
        logger.error("[Background] failed to save report: %s", exc)
        return None


async def create_predictions(report_data: dict) -> int:
    """將 Chief Analyst 已整理好的 prediction 契約直接寫入 DB。"""
    try:
        predictions = report_data.get("pending_predictions") or []
        if not predictions:
            logger.info(
                "[Background] no pending predictions for %s",
                report_data.get("symbol"),
            )
            return 0

        client = get_client()
        if not client:
            logger.error("[Background] Supabase client unavailable for predictions")
            return 0

        await asyncio.to_thread(
            lambda: client.table("predictions").insert(predictions).execute()
        )
        logger.info(
            "[Background] inserted %s predictions for %s",
            len(predictions),
            report_data.get("symbol"),
        )
        return len(predictions)
    except Exception as exc:
        logger.error("[Background] failed to create predictions: %s", exc)
        return 0


async def log_pipeline_result(report_data: dict, meta: dict) -> None:
    """將 pipeline 執行摘要寫入 agent_logs。"""
    try:
        log_agent_action(
            agent_name="pipeline",
            report_id=report_data.get("report_id"),
            status="success",
            metadata={
                "symbol": report_data.get("symbol"),
                "total_ms": meta.get("total_ms"),
                "agents_success": meta.get("agents_success"),
                "final_stance": meta.get("final_stance"),
                "target_price_low": meta.get("target_price_low"),
                "target_price_high": meta.get("target_price_high"),
            },
        )
    except Exception as exc:
        logger.error("[Background] failed to log pipeline result: %s", exc)


async def run_all_background_tasks(report_data: dict, meta: dict) -> None:
    """
    先寫 reports，再平行處理其餘背景工作。

    predictions.report_id 有 FK，因此必須先確保 reports 落地成功。
    """
    report_id = await save_report_to_db(report_data)
    if not report_id:
        logger.error("[Background] report save failed, skip predictions")

    tasks = [log_pipeline_result(report_data, meta)]
    if report_id:
        tasks.append(create_predictions(report_data))

    results = await asyncio.gather(*tasks, return_exceptions=True)
    for index, result in enumerate(results):
        if isinstance(result, Exception):
            logger.error("[Background] task %s failed: %s", index, result)
