"""Billing API routes."""

from __future__ import annotations

import time
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from adapters.supabase_adapter import supabase_adapter

router = APIRouter()


class UpgradeRequest(BaseModel):
    plan: Literal["pro", "premium"]
    billing_cycle: Literal["monthly", "yearly"] = "monthly"


def _require_auth(request: Request) -> dict:
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="未登入")

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


@router.get("/billing/upgrade-status")
async def get_upgrade_status(request: Request):
    """Get current user's upgrade pending status."""
    user = _require_auth(request)
    user_id = (user.get("id") or "").strip()
    if not user_id:
        raise HTTPException(status_code=401, detail="找不到使用者 ID")

    pending = supabase_adapter.get_pending_upgrade_request(user_id)
    return {"success": True, "has_pending": bool(pending), "pending": pending}


@router.post("/billing/upgrade-request")
async def upgrade_request(req: UpgradeRequest, request: Request):
    """
    Create an upgrade request.

    Flow:
    1. Always create pending request first.
    2. Notification failure must not rollback pending request.
    """
    user = _require_auth(request)
    user_id = (user.get("id") or "").strip()
    user_email = (user.get("email") or "").strip()
    if not user_id or not user_email:
        raise HTTPException(status_code=400, detail="使用者資料不完整")

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
                detail={
                    "message": "已有待審核升級申請，請等待審核完成後再送出。",
                    "code": "pending_exists",
                },
            )

        # Schema drift fallback: keep request flow alive.
        recovered = supabase_adapter.get_pending_upgrade_request(user_id)
        if not recovered:
            fallback_id = f"UPG-{int(time.time())}"
            recovered = {
                "id": fallback_id,
                "user_id": user_id,
                "plan": req.plan,
                "billing_cycle": req.billing_cycle,
                "email": user_email,
                "name": user_name,
                "status": "pending",
            }
            try:
                supabase_adapter._pending_upgrade_mem[user_id] = recovered  # noqa: SLF001
            except Exception:
                pass

        pending_create = {
            "success": True,
            "request_id": str(recovered.get("id") or ""),
            "pending": recovered,
            "message": "pending_fallback_created",
        }

    request_id = str(pending_create.get("request_id") or "")

    notify_success = False
    notify_provider = None
    notify_message = ""
    notify_code = None

    try:
        from services.email_service import email_service

        email_result = email_service.send_upgrade_request(
            user_email=user_email,
            user_name=user_name,
            plan=req.plan,
            billing_cycle=req.billing_cycle,
            request_id=request_id,
        )
        notify_success = bool(email_result.get("success"))
        notify_provider = email_result.get("provider")
        notify_message = str(email_result.get("message") or "")
        notify_code = email_result.get("code")
    except Exception as e:
        notify_success = False
        notify_provider = "exception"
        notify_message = f"通知寄送例外: {e}"
        notify_code = "notification_exception"

    if notify_success:
        message = notify_message or "升級申請已建立，管理員將在 1-5 個工作天內完成人工審核。"
    else:
        extra = f"（通知失敗: {notify_message}）" if notify_message else ""
        message = f"升級申請已建立，但通知寄送失敗。請聯繫管理員確認。{extra}"

    return {
        "success": True,
        "message": message,
        "order_id": request_id,
        "plan": req.plan,
        "billing_cycle": req.billing_cycle,
        "has_pending": True,
        "pending": pending_create.get("pending"),
        "notify_success": notify_success,
        "notify_provider": notify_provider,
        "notify_code": notify_code,
    }
