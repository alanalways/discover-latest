"""
backend/core/audit_log.py
Agent 行為留痕 & Gemini 呼叫記錄
- 所有 Gemini 呼叫都透過此模組寫入 agent_logs 表
- 失敗時降級為 Python logging，不阻斷主流程
"""
import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


def _get_supabase():
    """延遲導入 supabase_client，避免循環引用。"""
    try:
        from backend.data.storage.supabase_client import get_client
        return get_client()
    except Exception as e:
        logger.debug(f"[AuditLog] Supabase 不可用，使用本地 logging: {e}")
        return None


def log_gemini_call(
    agent_name: str,
    model_name: str,
    report_id: Optional[str] = None,
    status: str = "success",
    duration_ms: int = 0,
    use_grounding: bool = False,
    error: Optional[str] = None,
) -> None:
    """
    記錄一次 Gemini API 呼叫到 agent_logs 表。
    失敗時降級為 Python logging，不拋出例外。
    """
    metadata = {
        "use_grounding": use_grounding,
        "logged_at": datetime.now(timezone.utc).isoformat(),
    }

    log_record = {
        "agent_name": agent_name,
        "report_id": report_id,
        "action": "gemini_call",
        "gemini_model_used": model_name,
        "duration_ms": duration_ms,
        "status": status,
        "error_detail": error,
        "metadata": metadata,
    }

    # 本地 logging（永遠執行）
    if status == "success":
        logger.info(
            f"[Gemini] {agent_name} | {model_name} | "
            f"{duration_ms}ms | grounding={use_grounding}"
        )
    else:
        logger.error(
            f"[Gemini] {agent_name} | {model_name} | "
            f"FAILED: {error}"
        )

    # 寫入 Supabase（嘗試，失敗不阻斷）
    client = _get_supabase()
    if client:
        try:
            client.table("agent_logs").insert(log_record).execute()
        except Exception as e:
            logger.warning(f"[AuditLog] 寫入 Supabase 失敗（不影響主流程）: {e}")


def log_agent_action(
    agent_name: str,
    report_id: Optional[str],
    status: str,
    action: str = "run",
    duration_ms: int = 0,
    error: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> None:
    """
    記錄 Agent 執行動作到 agent_logs 表。
    """
    log_record = {
        "agent_name": agent_name,
        "report_id": report_id,
        "action": action,
        "duration_ms": duration_ms,
        "status": status,
        "error_detail": error,
        "metadata": metadata or {},
    }

    if status == "success":
        logger.info(f"[Agent] {agent_name}.{action} | {duration_ms}ms | OK")
    else:
        logger.error(f"[Agent] {agent_name}.{action} | FAILED: {error}")

    client = _get_supabase()
    if client:
        try:
            client.table("agent_logs").insert(log_record).execute()
        except Exception as e:
            logger.warning(f"[AuditLog] 寫入 Supabase 失敗（不影響主流程）: {e}")
