"""Admin API routes."""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter()

# 管理員 email
_DEFAULT_ADMIN_EMAIL = os.environ.get("DEFAULT_ADMIN_EMAIL", "cmshj30326@gmail.com")


class TierUpdateRequest(BaseModel):
    user_id: str
    tier: str
    expires_at: Optional[str] = None


class PendingModerateRequest(BaseModel):
    user_id: str
    tier: Optional[str] = None
    expires_at: Optional[str] = None


class PromptChangeRequest(BaseModel):
    change_type: str = "prompt"
    old_version: str = ""
    new_version: str = ""
    reason: str = ""
    expected_improvement: str = ""
    evidence: str = ""


from utils.auth import require_admin as _require_admin_shared


@router.get("/admin/users")
async def list_users(request: Request):
    """List users for admin dashboard."""
    _require_admin(request)
    try:
        from adapters.supabase_adapter import supabase_adapter
        import os

        users = supabase_adapter.get_all_users()

        # 回傳診斷資訊，讓前端知道各步驟有沒有問題
        diagnostic = {
            "user_count": len(users) if users else 0,
            "supabase_url_set": bool(os.environ.get("SUPABASE_URL")),
            "service_key_set": bool(os.environ.get("SUPABASE_SERVICE_ROLE_KEY")),
            "anon_key_set": bool(os.environ.get("SUPABASE_ANON_KEY")),
        }

        if not users:
            logger.warning("[Admin] /admin/users 回傳空列表，diagnostic=%s", diagnostic)

        return {"users": users or [], "diagnostic": diagnostic}
    except Exception as e:
        logger.error("[Admin] /admin/users 例外: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="\u4f3a\u670d\u5668\u66ab\u6642\u7121\u6cd5\u8655\u7406\u8acb\u6c42")


@router.post("/admin/tier")
async def update_tier(req: TierUpdateRequest, request: Request):
    """Manual tier update."""
    _require_admin(request)
    try:
        from services.auth_service import auth_service
        from adapters.supabase_adapter import supabase_adapter

        ok = auth_service.admin_update_tier(req.user_id, req.tier, req.expires_at)
        if ok:
            # If user is manually updated, clear pending request if present.
            try:
                supabase_adapter.clear_pending_upgrade_request(req.user_id)
            except Exception:
                pass
        return {"success": bool(ok)}
    except Exception:
        raise HTTPException(status_code=500, detail="\u4f3a\u670d\u5668\u66ab\u6642\u7121\u6cd5\u8655\u7406\u8acb\u6c42")


@router.get("/admin/stats")
async def get_stats(request: Request):
    """Basic platform stats."""
    _require_admin(request)
    try:
        from adapters.supabase_adapter import supabase_adapter

        users = supabase_adapter.get_all_users() or []
        pending = supabase_adapter.list_pending_upgrade_requests() or []

        tier_counts: dict[str, int] = {}
        for u in users:
            t = str(u.get("tier") or "free").lower()
            tier_counts[t] = tier_counts.get(t, 0) + 1

        return {
            "total_users": len(users),
            "tier_distribution": tier_counts,
            "pending_upgrade_count": len(pending),
        }
    except Exception:
        raise HTTPException(status_code=500, detail="\u4f3a\u670d\u5668\u66ab\u6642\u7121\u6cd5\u8655\u7406\u8acb\u6c42")


@router.get("/admin/upgrade-pending")
async def list_upgrade_pending(request: Request):
    """List pending upgrade requests."""
    _require_admin(request)
    try:
        from adapters.supabase_adapter import supabase_adapter

        rows = supabase_adapter.list_pending_upgrade_requests() or []
        return {"pending": rows}
    except Exception:
        raise HTTPException(status_code=500, detail="\u4f3a\u670d\u5668\u66ab\u6642\u7121\u6cd5\u8655\u7406\u8acb\u6c42")


@router.post("/admin/upgrade-pending/approve")
async def approve_upgrade_pending(req: PendingModerateRequest, request: Request):
    """Approve pending upgrade and apply tier immediately."""
    actor = _require_admin(request)
    user_id = (req.user_id or "").strip()
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id is required")

    try:
        from adapters.supabase_adapter import supabase_adapter
        from services.auth_service import auth_service

        logger.info(
            "[AdminModeration] approve requested by=%s target=%s tier=%s",
            actor.get('email') or actor.get('id'), user_id, req.tier or ''
        )

        pending = supabase_adapter.get_pending_upgrade_request(user_id)
        if not pending:
            return {
                "success": True,
                "user_id": user_id,
                "message": "待審申請已不存在，可能已被其他管理員處理",
            }

        tier = (req.tier or pending.get("plan") or "").strip().lower()
        if tier not in {"free", "pro", "premium"}:
            raise HTTPException(status_code=400, detail="tier 必須為 free/pro/premium")

        ok = auth_service.admin_update_tier(user_id, tier, req.expires_at)
        if not ok:
            raise HTTPException(status_code=500, detail="升級方案寫入失敗")

        cleared = supabase_adapter.clear_pending_upgrade_request(user_id)
        if not cleared:
            # Keep action idempotent; only fail if pending is still visible in listing source.
            pending_rows = supabase_adapter.list_pending_upgrade_requests() or []
            still_visible = any(str((row or {}).get("user_id") or "").strip() == user_id for row in pending_rows)
            if still_visible:
                raise HTTPException(status_code=500, detail="清除待審核申請失敗")

        # 通知用戶升級已核准
        try:
            from services.email_service import email_service
            email_service.notify_user_upgrade_approved(
                pending.get("email", ""), pending.get("name", ""), tier
            )
        except Exception:
            logger.warning("[Admin] email notify_user_upgrade_approved failed", exc_info=True)

        return {
            "success": True,
            "user_id": user_id,
            "tier": tier,
            "message": "升級申請已核准並套用方案",
        }
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="\u4f3a\u670d\u5668\u66ab\u6642\u7121\u6cd5\u8655\u7406\u8acb\u6c42")


@router.post("/admin/upgrade-pending/reject")
async def reject_upgrade_pending(req: PendingModerateRequest, request: Request):
    """Reject pending upgrade request."""
    actor = _require_admin(request)
    user_id = (req.user_id or "").strip()
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id is required")

    try:
        from adapters.supabase_adapter import supabase_adapter

        logger.info(
            "[AdminModeration] reject requested by=%s target=%s",
            actor.get('email') or actor.get('id'), user_id
        )

        pending = supabase_adapter.get_pending_upgrade_request(user_id)
        if not pending:
            return {
                "success": True,
                "user_id": user_id,
                "message": "待審申請已不存在，可能已被其他管理員處理",
            }

        ok = supabase_adapter.clear_pending_upgrade_request(user_id)
        if not ok:
            pending_rows = supabase_adapter.list_pending_upgrade_requests() or []
            still_visible = any(str((row or {}).get("user_id") or "").strip() == user_id for row in pending_rows)
            if still_visible:
                raise HTTPException(status_code=500, detail="清除待審核申請失敗")

        # 通知用戶升級已拒絕
        try:
            from services.email_service import email_service
            email_service.notify_user_upgrade_rejected(
                pending.get("email", ""), pending.get("name", ""), pending.get("plan", "")
            )
        except Exception:
            logger.warning("[Admin] email notify_user_upgrade_rejected failed", exc_info=True)

        return {
            "success": True,
            "user_id": user_id,
            "message": "已拒絕升級申請",
        }
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="\u4f3a\u670d\u5668\u66ab\u6642\u7121\u6cd5\u8655\u7406\u8acb\u6c42")


@router.get("/admin/system")
async def get_system_status(request: Request):
    """System status: API key usage, Supabase latency, server uptime."""
    _require_admin(request)
    try:
        from services.gemini_service import get_key_usage_stats

        # API key usage
        api_keys = get_key_usage_stats()

        # Supabase latency — 輕量 ping（SELECT id LIMIT 1），不再用 get_all_users()
        supabase_latency_ms: Optional[float] = None
        try:
            from adapters.supabase_adapter import supabase_adapter

            t0 = time.time()
            supabase_adapter._request(
                "GET", "users",
                params={"select": "id", "limit": "1"},
                use_service_key=True, silent=True,
            )
            supabase_latency_ms = round((time.time() - t0) * 1000, 1)
        except Exception:
            supabase_latency_ms = None

        # Server uptime
        startup_time = getattr(request.app.state, 'startup_time', None)
        uptime_sec = round(time.time() - startup_time) if startup_time else None

        # 本地 SQLite 統計
        local_stats = {}
        try:
            from adapters.local_store import local_store
            local_stats = local_store.get_stats()
        except Exception:
            pass

        return {
            "api_keys": api_keys,
            "supabase_latency_ms": supabase_latency_ms,
            "server_uptime_sec": uptime_sec,
            "local_store_stats": local_stats,
        }
    except Exception:
        raise HTTPException(status_code=500, detail="\u4f3a\u670d\u5668\u66ab\u6642\u7121\u6cd5\u8655\u7406\u8acb\u6c42")


@router.get("/admin/circuit-breaker")
async def get_circuit_breaker_status(request: Request):
    """Get Gemini API circuit breaker status."""
    _require_admin(request)
    try:
        from services.gemini_circuit_breaker import gemini_breaker
        return gemini_breaker.get_status()
    except ImportError:
        return {"state": "unavailable", "error": "circuit breaker module not loaded"}
    except Exception:
        raise HTTPException(status_code=500, detail="\u4f3a\u670d\u5668\u66ab\u6642\u7121\u6cd5\u8655\u7406\u8acb\u6c42")


@router.post("/admin/circuit-breaker/reset")
async def reset_circuit_breaker(request: Request):
    """Force close the circuit breaker (restore normal API access)."""
    _require_admin(request)
    try:
        from services.gemini_circuit_breaker import gemini_breaker
        gemini_breaker.force_close()
        return {"success": True, "state": gemini_breaker.state.value, "message": "Circuit breaker 已重置為 CLOSED"}
    except ImportError:
        raise HTTPException(status_code=500, detail="circuit breaker module not loaded")
    except Exception:
        raise HTTPException(status_code=500, detail="\u4f3a\u670d\u5668\u66ab\u6642\u7121\u6cd5\u8655\u7406\u8acb\u6c42")


def _require_admin(request: Request) -> dict[str, Any]:
    """Verify admin access (delegated to utils.auth)."""
    return _require_admin_shared(request)


@router.get("/admin/cache-stats")
async def get_cache_stats(request: Request):
    """Return stats for all registered caches."""
    _require_admin(request)
    try:
        from services.cache_manager import cache_registry
        return {"caches": cache_registry.get_all_stats()}
    except Exception:
        raise HTTPException(status_code=500, detail="\u4f3a\u670d\u5668\u66ab\u6642\u7121\u6cd5\u8655\u7406\u8acb\u6c42")


@router.get("/admin/calibration")
async def get_calibration_report(request: Request):
    """Return confidence calibration report."""
    _require_admin(request)
    try:
        from services.confidence_calibrator import confidence_calibrator
        return confidence_calibrator.get_report()
    except Exception:
        raise HTTPException(status_code=500, detail="\u4f3a\u670d\u5668\u66ab\u6642\u7121\u6cd5\u8655\u7406\u8acb\u6c42")


@router.get("/admin/macro")
async def get_macro_context(request: Request):
    """Return current macro market context."""
    _require_admin(request)
    try:
        from services.macro_context_service import macro_context_service
        return macro_context_service.get_context(force_refresh=True)
    except Exception:
        raise HTTPException(status_code=500, detail="\u4f3a\u670d\u5668\u66ab\u6642\u7121\u6cd5\u8655\u7406\u8acb\u6c42")


@router.get("/admin/predictions/dashboard")
async def get_predictions_dashboard(request: Request):
    """AI prediction accuracy dashboard with version-level breakdown."""
    _require_admin(request)
    try:
        from services.ai_prediction_tracker import prediction_tracker
        return prediction_tracker.get_accuracy_dashboard()
    except Exception:
        raise HTTPException(status_code=500, detail="\u4f3a\u670d\u5668\u66ab\u6642\u7121\u6cd5\u8655\u7406\u8acb\u6c42")


@router.get("/admin/predictions/monthly")
async def get_predictions_monthly(
    request: Request,
    year: int = Query(..., ge=2020, le=2100),
    month: int = Query(..., ge=1, le=12),
):
    """Monthly prediction review with prompt/rule/model version breakdown."""
    _require_admin(request)
    try:
        from services.ai_prediction_tracker import prediction_tracker
        return prediction_tracker.get_monthly_review(year=year, month=month)
    except Exception:
        raise HTTPException(status_code=500, detail="\u4f3a\u670d\u5668\u66ab\u6642\u7121\u6cd5\u8655\u7406\u8acb\u6c42")


@router.get("/admin/predictions/quarterly")
async def get_predictions_quarterly(
    request: Request,
    year: int = Query(..., ge=2020, le=2100),
    quarter: int = Query(..., ge=1, le=4),
):
    """Quarterly audit with tuning recommendations."""
    _require_admin(request)
    try:
        from services.ai_prediction_tracker import prediction_tracker
        return prediction_tracker.get_quarterly_audit(year=year, quarter=quarter)
    except Exception:
        raise HTTPException(status_code=500, detail="\u4f3a\u670d\u5668\u66ab\u6642\u7121\u6cd5\u8655\u7406\u8acb\u6c42")


@router.get("/admin/prompt-changes")
async def list_prompt_changes(request: Request):
    """List prompt/rule change history."""
    _require_admin(request)
    try:
        from adapters.local_store import local_store
        rows = local_store.list_prompt_changes(limit=200)
        return {"changes": rows}
    except Exception:
        raise HTTPException(status_code=500, detail="\u4f3a\u670d\u5668\u66ab\u6642\u7121\u6cd5\u8655\u7406\u8acb\u6c42")


@router.post("/admin/prompt-changes")
async def add_prompt_change(req: PromptChangeRequest, request: Request):
    """Record a prompt/rule/system change with reason and evidence."""
    _require_admin(request)
    try:
        import uuid
        from adapters.local_store import local_store
        record = {
            "id": str(uuid.uuid4()),
            "change_type": req.change_type,
            "old_version": req.old_version,
            "new_version": req.new_version,
            "reason": req.reason,
            "expected_improvement": req.expected_improvement,
            "evidence": req.evidence,
            "changed_by": "admin",
        }
        ok = local_store.add_prompt_change(record)
        return {"success": ok, "record": record}
    except Exception:
        raise HTTPException(status_code=500, detail="\u4f3a\u670d\u5668\u66ab\u6642\u7121\u6cd5\u8655\u7406\u8acb\u6c42")
