"""
backend/core/background_tasks.py
背景任務管理

報告產出後，使用者不需等待的任務：
- 寫入 reports 表
- 寫入 predictions 表
- 寫入 agent_logs 審計日誌
- LINE 通知（如果有重大訊號）
- 更新使用者用量計數
"""
import logging
import asyncio
from typing import Optional
from datetime import date, timedelta

from backend.data.storage.supabase_client import get_client
from backend.core.audit_log import log_agent_action

logger = logging.getLogger(__name__)


async def save_report_to_db(report_data: dict) -> Optional[str]:
    """
    將完整報告寫入 reports 表。

    Returns:
        report_id 或 None（失敗時）
    """
    try:
        client = get_client()
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
            "arbitration_log": report_data.get("arbitration"),
            "final_report": report_data["full_report"],
            "rating": report_data.get("arbitration", {}).get("final_stance"),
            "confidence_score": report_data.get("arbitration", {}).get(
                "stance_confidence"
            ),
            "triggered_by": "user",
            "user_id": report_data.get("user_id"),
        }

        result = await asyncio.to_thread(
            lambda: client.table("reports").insert(row).execute()
        )
        logger.info(f"[Background] 報告已儲存: {report_data['report_id']}")
        return report_data["report_id"]

    except Exception as e:
        logger.error(f"[Background] 報告儲存失敗: {e}")
        return None


async def create_predictions(report_data: dict) -> int:
    """
    從報告中提取預測，寫入 predictions 表。

    Returns:
        寫入的 prediction 數量
    """
    try:
        arbitration = report_data.get("arbitration", {})
        stance = arbitration.get("final_stance", "neutral")
        confidence = arbitration.get("stance_confidence", 0.5)

        # 方向映射
        direction_map = {
            "bullish": "up",
            "cautious_bullish": "up",
            "bearish": "down",
            "cautious_bearish": "down",
            "neutral": "neutral",
        }
        direction = direction_map.get(stance, "neutral")

        if direction == "neutral":
            logger.info("[Background] 中性立場，不建立預測")
            return 0

        # 短期（5 天）和中期（30 天）各建一筆
        predictions = []
        today = date.today()

        for timeframe, days in [("short", 5), ("medium", 30)]:
            predictions.append({
                "report_id": report_data["report_id"],
                "symbol": report_data["symbol"],
                "market": report_data["market"],
                "predicted_direction": direction,
                "timeframe": timeframe,
                "prediction_date": today.isoformat(),
                "verify_date": (today + timedelta(days=days)).isoformat(),
            })

        client = get_client()
        result = await asyncio.to_thread(
            lambda: client.table("predictions").insert(predictions).execute()
        )
        logger.info(
            f"[Background] 建立 {len(predictions)} 筆預測: "
            f"{report_data['symbol']} {direction}"
        )
        return len(predictions)

    except Exception as e:
        logger.error(f"[Background] 預測建立失敗: {e}")
        return 0


async def log_pipeline_result(report_data: dict, meta: dict) -> None:
    """記錄 pipeline 執行結果到 agent_logs。"""
    try:
        log_agent_action(
            agent_name="pipeline",
            report_id=report_data.get("report_id"),
            status="success",
            metadata={
                "symbol": report_data["symbol"],
                "total_ms": meta.get("total_ms"),
                "agents_success": meta.get("agents_success"),
                "final_stance": meta.get("final_stance"),
            },
        )
    except Exception as e:
        logger.error(f"[Background] 日誌記錄失敗: {e}")


async def run_all_background_tasks(report_data: dict, meta: dict) -> None:
    """
    啟動所有背景任務（fire-and-forget）。

    在 analysis route 中，報告 streaming 完成後呼叫此函式。
    """
    tasks = [
        save_report_to_db(report_data),
        create_predictions(report_data),
        log_pipeline_result(report_data, meta),
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.error(f"[Background] 任務 {i} 失敗: {result}")
