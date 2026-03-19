"""
backend/api/routes/admin.py
管理員 API — 使用者管理、方案審核、系統狀態

- GET    /api/admin/users          — 列出所有使用者
- GET    /api/admin/users/{id}     — 查詢單一使用者
- PATCH  /api/admin/users/{id}/tier— 更新使用者方案
- GET    /api/admin/upgrades       — 待審升級列表
- POST   /api/admin/upgrades/{id}  — 審核升級（approve/reject）
- GET    /api/admin/system         — 系統狀態
- GET    /api/admin/cache          — 快取統計
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.api.routes.auth import require_admin, UserInfo

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


# ─── Models ───────────────────────────────────────────────

class TierUpdate(BaseModel):
    tier: str
    expires_at: Optional[str] = None


class UpgradeReview(BaseModel):
    action: str  # approve | reject


# ─── Routes ──────────────────────────────────────────────

@router.get("/users")
async def list_users(admin: UserInfo = Depends(require_admin)):
    """列出所有使用者（Admin 專用）。"""
    from backend.data.storage.supabase_client import rest_request
    result = rest_request(
        "GET", "users",
        params={
            "select": "id,email,name,tier,created_at",
            "order": "created_at.desc",
            "limit": "200",
        },
        use_service_key=True,
    )
    return {"users": result or []}


@router.get("/users/{user_id}")
async def get_user(user_id: str, admin: UserInfo = Depends(require_admin)):
    """查詢單一使用者詳細資訊。"""
    from backend.data.storage.supabase_client import (
        get_user_by_id, auth_admin_get_user_by_id,
        get_user_subscription, get_ai_usage_today,
    )

    user = get_user_by_id(user_id) or auth_admin_get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    sub = get_user_subscription(user_id)
    usage = get_ai_usage_today(user_id)

    return {
        "id": user.get("id"),
        "email": user.get("email", ""),
        "name": user.get("name", ""),
        "tier": sub.get("tier", "free"),
        "expires_at": sub.get("expires_at"),
        "daily_ai_usage": usage,
        "created_at": user.get("created_at"),
    }


@router.patch("/users/{user_id}/tier")
async def update_tier(
    user_id: str,
    body: TierUpdate,
    admin: UserInfo = Depends(require_admin),
):
    """更新使用者方案等級。"""
    from backend.data.storage.supabase_client import update_user_tier
    ok = update_user_tier(user_id, body.tier, body.expires_at)
    if not ok:
        raise HTTPException(status_code=500, detail="更新失敗")
    return {"status": "ok", "tier": body.tier}


@router.get("/upgrades")
async def list_upgrades(admin: UserInfo = Depends(require_admin)):
    """列出待審升級申請。"""
    from backend.data.storage.supabase_client import rest_request
    result = rest_request(
        "GET", "pending_upgrades",
        params={
            "status": "eq.pending",
            "select": "*",
            "order": "created_at.desc",
        },
        use_service_key=True,
    )
    return {"upgrades": result or []}


@router.post("/upgrades/{upgrade_id}")
async def review_upgrade(
    upgrade_id: str,
    body: UpgradeReview,
    admin: UserInfo = Depends(require_admin),
):
    """審核升級申請。"""
    from backend.data.storage.supabase_client import rest_request, update_user_tier
    from backend.core.email_service import email_service

    # 取得申請資料
    result = rest_request(
        "GET", "pending_upgrades",
        params={"id": f"eq.{upgrade_id}", "select": "*"},
        use_service_key=True,
    )
    if not result or not isinstance(result, list) or not result:
        raise HTTPException(status_code=404, detail="Upgrade request not found")

    req = result[0]
    user_id = req.get("user_id")
    plan = req.get("plan")
    user_email = req.get("user_email", "")
    user_name = req.get("user_name", "")

    if body.action == "approve":
        update_user_tier(user_id, plan)
        rest_request(
            "PATCH", "pending_upgrades",
            params={"id": f"eq.{upgrade_id}"},
            json={"status": "approved"},
            use_service_key=True,
        )
        email_service.notify_user_upgrade_approved(user_email, user_name, plan)
        return {"status": "approved"}

    elif body.action == "reject":
        rest_request(
            "PATCH", "pending_upgrades",
            params={"id": f"eq.{upgrade_id}"},
            json={"status": "rejected"},
            use_service_key=True,
        )
        email_service.notify_user_upgrade_rejected(user_email, user_name, plan)
        return {"status": "rejected"}

    else:
        raise HTTPException(status_code=400, detail="action must be approve or reject")


@router.get("/system")
async def system_status(admin: UserInfo = Depends(require_admin)):
    """系統狀態總覽。"""
    from backend.core.budget_guard import get_budget_guard
    from backend.gemini.client import get_rate_limiter_status, get_key_usage_stats
    from backend.data.storage.supabase_client import get_client

    budget = get_budget_guard().get_status()
    rate_limiter = get_rate_limiter_status()
    key_usage = get_key_usage_stats()
    db_ok = get_client() is not None

    return {
        "database": "connected" if db_ok else "unavailable",
        "budget": budget,
        "gemini_rate_limits": rate_limiter,
        "gemini_key_usage": key_usage,
    }


@router.get("/cache")
async def cache_stats(admin: UserInfo = Depends(require_admin)):
    """快取統計。"""
    from backend.core.cache_manager import cache_registry
    return {"caches": cache_registry.get_all_stats()}
