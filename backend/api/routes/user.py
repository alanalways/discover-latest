"""
backend/api/routes/user.py
使用者 API — 個人資料、方案、升級、AI 用量

- GET  /api/user/limits      — 取得 AI 使用限額資訊
- GET  /api/user/portfolio    — 取得持股
- PUT  /api/user/portfolio    — 更新持股
- GET  /api/user/alerts       — 取得價格提醒
- POST /api/user/alerts       — 新增提醒
- DELETE /api/user/alerts/{id}— 刪除提醒
- POST /api/user/upgrade      — 申請升級
- GET  /api/user/upgrade      — 查詢升級狀態
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.api.routes.auth import require_user, UserInfo

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/user", tags=["user"])


# ─── Models ───────────────────────────────────────────────

class PortfolioItem(BaseModel):
    symbol: str
    shares: int = 0
    avg_cost: float = 0.0


class PortfolioUpdate(BaseModel):
    holdings: list[PortfolioItem]


class AlertCreate(BaseModel):
    symbol: str
    target_price: float
    direction: str = "above"  # above | below


class UpgradeRequest(BaseModel):
    plan: str           # pro | premium
    billing_cycle: str = "monthly"  # monthly | yearly


# ─── Routes ──────────────────────────────────────────────

@router.get("/limits")
async def get_limits(user: UserInfo = Depends(require_user)):
    """取得使用者 AI 使用限額。"""
    from backend.core.user_rate_limiter import get_user_rate_limiter
    limiter = get_user_rate_limiter()
    return limiter.get_user_limits_info(user.user_id)


@router.get("/portfolio")
async def get_portfolio(user: UserInfo = Depends(require_user)):
    """取得使用者持股。"""
    from backend.data.storage.supabase_client import load_user_portfolio
    holdings = load_user_portfolio(user.user_id)
    return {"holdings": holdings}


@router.put("/portfolio")
async def update_portfolio(
    body: PortfolioUpdate,
    user: UserInfo = Depends(require_user),
):
    """更新使用者持股（覆蓋）。"""
    from backend.data.storage.supabase_client import save_user_portfolio
    items = [h.model_dump() for h in body.holdings]
    ok = save_user_portfolio(user.user_id, items)
    if not ok:
        raise HTTPException(status_code=500, detail="儲存失敗")
    return {"status": "ok", "count": len(items)}


@router.get("/alerts")
async def get_alerts(user: UserInfo = Depends(require_user)):
    """取得使用者的價格提醒。"""
    from backend.data.storage.supabase_client import get_user_alerts
    alerts = get_user_alerts(user.user_id)
    return {"alerts": alerts}


@router.post("/alerts")
async def create_alert(
    body: AlertCreate,
    user: UserInfo = Depends(require_user),
):
    """新增價格提醒。"""
    from backend.data.storage.supabase_client import create_user_alert
    condition = "gte" if body.direction == "above" else "lte"
    ok = create_user_alert(user.user_id, body.symbol, body.target_price, condition)
    if not ok:
        raise HTTPException(status_code=500, detail="新增失敗")
    return {"status": "ok"}


@router.delete("/alerts/{alert_id}")
async def delete_alert(
    alert_id: str,
    user: UserInfo = Depends(require_user),
):
    """刪除價格提醒。"""
    from backend.data.storage.supabase_client import delete_user_alert
    ok = delete_user_alert(alert_id, user.user_id)
    if not ok:
        raise HTTPException(status_code=500, detail="刪除失敗")
    return {"status": "ok"}


@router.post("/upgrade")
async def request_upgrade(
    body: UpgradeRequest,
    user: UserInfo = Depends(require_user),
):
    """申請方案升級。"""
    from backend.data.storage.supabase_client import create_pending_upgrade, get_pending_upgrade
    from backend.core.email_service import email_service

    # 檢查是否已有待審申請
    existing = get_pending_upgrade(user.user_id)
    if existing:
        return {
            "status": "already_pending",
            "message": "您已有一筆待審的升級申請",
        }

    create_pending_upgrade(
        user_id=user.user_id,
        user_email=user.email or "",
        user_name=user.name or user.email or "",
        plan=body.plan,
        billing_cycle=body.billing_cycle,
    )

    # 發送通知
    email_service.notify_admin_new_upgrade(
        user_name=user.name or user.email or "",
        user_email=user.email or "",
        plan=body.plan,
        billing_cycle=body.billing_cycle,
    )
    email_service.notify_user_upgrade_submitted(
        user_email=user.email or "",
        user_name=user.name or user.email or "",
        plan=body.plan,
        billing_cycle=body.billing_cycle,
    )

    return {"status": "submitted", "message": "升級申請已送出，管理員將盡快審核"}


@router.get("/upgrade")
async def check_upgrade(user: UserInfo = Depends(require_user)):
    """查詢升級申請狀態。"""
    from backend.data.storage.supabase_client import get_pending_upgrade
    pending = get_pending_upgrade(user.user_id)
    if pending:
        return {"status": "pending", "request": pending}
    return {"status": "none"}
