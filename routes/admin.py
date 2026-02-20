"""Admin API routes."""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter()

# 管理員 email 從環境變數讀取，不硬編碼於原始碼
_DEFAULT_ADMIN_EMAIL = os.environ.get("DEFAULT_ADMIN_EMAIL", "")


class TierUpdateRequest(BaseModel):
    user_id: str
    tier: str
    expires_at: Optional[str] = None


class PendingModerateRequest(BaseModel):
    user_id: str
    tier: Optional[str] = None
    expires_at: Optional[str] = None


def _collect_admin_emails() -> set[str]:
    raw_values = [
        os.environ.get("ADMIN_EMAILS", ""),
        os.environ.get("NEXT_PUBLIC_ADMIN_EMAILS", ""),
        _DEFAULT_ADMIN_EMAIL,
    ]
    emails: set[str] = set()
    for raw in raw_values:
        for item in str(raw or "").split(","):
            email = item.strip().lower()
            if email:
                emails.add(email)
    return emails


def _is_admin_user(user: dict[str, Any], admin_emails: set[str]) -> bool:
    user_email = str(user.get("email") or "").strip().lower()
    if user_email and user_email in admin_emails:
        return True

    metadata = user.get("user_metadata") if isinstance(user.get("user_metadata"), dict) else {}
    app_metadata = user.get("app_metadata") if isinstance(user.get("app_metadata"), dict) else {}

    if bool(metadata.get("is_admin")) or bool(app_metadata.get("is_admin")):
        return True

    role = str(metadata.get("role") or app_metadata.get("role") or "").strip().lower()
    if role in {"admin", "owner"}:
        return True

    roles = metadata.get("roles") if isinstance(metadata.get("roles"), list) else app_metadata.get("roles")
    if isinstance(roles, list):
        for item in roles:
            if str(item or "").strip().lower() in {"admin", "owner"}:
                return True

    return False


@router.get("/admin/users")
async def list_users(request: Request):
    """List users for admin dashboard."""
    _require_admin(request)
    try:
        from adapters.supabase_adapter import supabase_adapter

        users = supabase_adapter.get_all_users()
        return {"users": users or []}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/admin/upgrade-pending")
async def list_upgrade_pending(request: Request):
    """List pending upgrade requests."""
    _require_admin(request)
    try:
        from adapters.supabase_adapter import supabase_adapter

        rows = supabase_adapter.list_pending_upgrade_requests() or []
        return {"pending": rows}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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

        return {
            "success": True,
            "user_id": user_id,
            "tier": tier,
            "message": "升級申請已核准並套用方案",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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

        return {
            "success": True,
            "user_id": user_id,
            "message": "已拒絕升級申請",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/admin/system")
async def get_system_status(request: Request):
    """System status: API key usage, Supabase latency, server uptime."""
    _require_admin(request)
    try:
        from services.gemini_service import get_key_usage_stats
        import main as _main

        # API key usage
        api_keys = get_key_usage_stats()

        # Supabase latency（不暴露 service_key，封裝到 adapter 方法）
        supabase_latency_ms: Optional[float] = None
        try:
            from adapters.supabase_adapter import supabase_adapter

            t0 = time.time()
            # 使用 adapter 內部方法測試連線，不直接操作 key
            supabase_adapter.get_all_users()  # 簡單查詢測延遲
            supabase_latency_ms = round((time.time() - t0) * 1000, 1)
        except Exception:
            supabase_latency_ms = None

        # Server uptime（使用 app.state 而非全域變數）
        from fastapi import Request as _Req
        startup_time = getattr(request.app.state, 'startup_time', None)
        uptime_sec = round(time.time() - startup_time) if startup_time else None

        return {
            "api_keys": api_keys,
            "supabase_latency_ms": supabase_latency_ms,
            "server_uptime_sec": uptime_sec,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _require_admin(request: Request) -> dict[str, Any]:
    """Verify admin access by session + allowlist emails."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="請先登入")

    token = auth_header.split(" ", 1)[1]
    try:
        from services.auth_service import auth_service

        user = auth_service.verify_session(token)
        if not user:
            raise HTTPException(status_code=401, detail="Session 已失效")

        admin_emails = _collect_admin_emails()
        if not _is_admin_user(user, admin_emails):
            raise HTTPException(status_code=403, detail="你不是管理員")
        return user
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="驗證失敗")
