"""
Admin API — 管理後台
"""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional

router = APIRouter()

_ADMIN_EMAIL = "alanalways0817@gmail.com"


class TierUpdateRequest(BaseModel):
    user_id: str
    tier: str
    expires_at: Optional[str] = None


@router.get("/admin/users")
async def list_users(request: Request):
    """列出所有使用者"""
    _require_admin(request)
    try:
        from adapters.supabase_adapter import supabase_adapter
        users = supabase_adapter.get_all_users()
        return {"users": users or []}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/admin/tier")
async def update_tier(req: TierUpdateRequest, request: Request):
    """更新用戶方案"""
    _require_admin(request)
    try:
        from services.auth_service import auth_service
        result = auth_service.admin_update_tier(
            req.user_id, req.tier, req.expires_at
        )
        return {"success": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/admin/stats")
async def get_stats(request: Request):
    """取得系統統計"""
    _require_admin(request)
    try:
        from adapters.supabase_adapter import supabase_adapter
        users = supabase_adapter.get_all_users() or []
        tier_counts = {}
        for u in users:
            t = u.get("tier", "free")
            tier_counts[t] = tier_counts.get(t, 0) + 1
        return {
            "total_users": len(users),
            "tier_distribution": tier_counts,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _require_admin(request: Request):
    """驗證 admin 權限"""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="請先登入")
    token = auth_header.split(" ", 1)[1]
    try:
        from services.auth_service import auth_service
        user = auth_service.verify_session(token)
        if not user:
            raise HTTPException(status_code=401, detail="Session 已過期")
        if user.get("email") != _ADMIN_EMAIL:
            raise HTTPException(status_code=403, detail="需要管理員權限")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="驗證失敗")
