"""
Billing API — 升級請求與付款資訊寄送
"""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Literal

router = APIRouter()


class UpgradeRequest(BaseModel):
    plan: Literal["pro", "premium"]
    billing_cycle: Literal["monthly", "yearly"] = "monthly"


@router.post("/billing/upgrade-request")
async def upgrade_request(req: UpgradeRequest, request: Request):
    """送出升級請求，寄付款資訊到用戶信箱並通知管理員"""
    user = _require_auth(request)
    user_email = (user.get("email") or "").strip()
    if not user_email:
        raise HTTPException(status_code=400, detail="帳號缺少 Email，無法寄送升級資訊")

    metadata = user.get("user_metadata", {}) if isinstance(user.get("user_metadata"), dict) else {}
    user_name = (
        metadata.get("full_name")
        or user.get("name")
        or user_email.split("@", 1)[0]
    )

    try:
        from services.email_service import email_service
        result = email_service.send_upgrade_request(
            user_email=user_email,
            user_name=user_name,
            plan=req.plan,
            billing_cycle=req.billing_cycle,
        )
        if not result.get("success"):
            raise HTTPException(status_code=500, detail=result.get("message", "升級請求發送失敗"))
        return {
            "success": True,
            "message": result.get("message", "升級申請已送出，請查收 Email"),
            "order_id": result.get("order_id"),
            "plan": req.plan,
            "billing_cycle": req.billing_cycle,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"升級流程失敗: {e}")


def _require_auth(request: Request) -> dict:
    """驗證登入狀態，回傳 user"""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="請先登入")
    token = auth_header.split(" ", 1)[1]
    try:
        from services.auth_service import auth_service
        user = auth_service.verify_session(token)
        if not user:
            raise HTTPException(status_code=401, detail="Session 已過期")
        return user
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="驗證失敗")
