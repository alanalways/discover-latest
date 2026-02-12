"""Billing API routes."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from adapters.supabase_adapter import supabase_adapter

router = APIRouter()


class UpgradeRequest(BaseModel):
    plan: Literal["pro", "premium"]
    billing_cycle: Literal["monthly", "yearly"] = "monthly"


@router.get("/billing/upgrade-status")
async def get_upgrade_status(request: Request):
    """Get current user's upgrade pending status."""
    user = _require_auth(request)
    user_id = (user.get("id") or "").strip()
    if not user_id:
        raise HTTPException(status_code=401, detail="無效使用者")

    pending = supabase_adapter.get_pending_upgrade_request(user_id)
    return {
        "success": True,
        "has_pending": bool(pending),
        "pending": pending,
    }


@router.post("/billing/upgrade-request")
async def upgrade_request(req: UpgradeRequest, request: Request):
    """Create upgrade request and notify admin mailbox."""
    user = _require_auth(request)
    user_id = (user.get("id") or "").strip()
    user_email = (user.get("email") or "").strip()
    if not user_id or not user_email:
        raise HTTPException(status_code=400, detail="缺少使用者資訊，請重新登入")

    metadata = user.get("user_metadata") if isinstance(user.get("user_metadata"), dict) else {}
    user_name = (metadata.get("full_name") or user.get("name") or user_email.split("@", 1)[0]).strip()

    pending_create = supabase_adapter.create_pending_upgrade_request(
        user_id=user_id,
        user_email=user_email,
        user_name=user_name,
        plan=req.plan,
        billing_cycle=req.billing_cycle,
    )

    if not pending_create.get("success"):
        if pending_create.get("reason") == "pending_exists":
            raise HTTPException(
                status_code=409,
                detail="你已有待審核的升級申請，審核完成前不可重複送出",
            )
        raise HTTPException(status_code=500, detail=pending_create.get("message", "建立升級申請失敗"))

    request_id = str(pending_create.get("request_id") or "")

    try:
        from services.email_service import email_service

        email_result = email_service.send_upgrade_request(
            user_email=user_email,
            user_name=user_name,
            plan=req.plan,
            billing_cycle=req.billing_cycle,
            request_id=request_id,
        )
        if not email_result.get("success"):
            # Roll back pending if email notification fails.
            try:
                supabase_adapter.clear_pending_upgrade_request(user_id)
            except Exception:
                pass
            raise HTTPException(status_code=500, detail=email_result.get("message", "通知信寄送失敗"))

        return {
            "success": True,
            "message": email_result.get("message", "已送出升級申請，請等待人工審核"),
            "order_id": request_id,
            "plan": req.plan,
            "billing_cycle": req.billing_cycle,
            "has_pending": True,
            "pending": pending_create.get("pending"),
        }
    except HTTPException:
        raise
    except Exception as e:
        try:
            supabase_adapter.clear_pending_upgrade_request(user_id)
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"升級申請處理失敗: {e}")


def _require_auth(request: Request) -> dict:
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="未授權")
    token = auth_header.split(" ", 1)[1]
    try:
        from services.auth_service import auth_service

        user = auth_service.verify_session(token)
        if not user:
            raise HTTPException(status_code=401, detail="Session 已失效")
        return user
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="驗證失敗")
