"""Billing API routes."""

from __future__ import annotations

import time
from typing import Literal, Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from adapters.supabase_adapter import supabase_adapter

router = APIRouter()


class UpgradeRequest(BaseModel):
    plan: Literal["pro", "premium"]
    billing_cycle: Literal["monthly", "yearly"] = "monthly"


def _require_auth(request: Request) -> dict[str, Any]:
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="請先登入")

    token = auth_header.split(" ", 1)[1]
    try:
        from services.auth_service import auth_service

        user = auth_service.verify_session(token)
        if not user:
            raise HTTPException(status_code=401, detail="Session 驗證失敗")
        return user
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="登入狀態失效")


def _build_memory_pending(
    user_id: str,
    user_email: str,
    user_name: str,
    plan: str,
    billing_cycle: str,
) -> dict[str, Any]:
    return {
        "id": f"UPG-{int(time.time())}",
        "user_id": user_id,
        "email": user_email,
        "name": user_name,
        "plan": plan,
        "billing_cycle": billing_cycle,
        "status": "pending",
    }


@router.get("/billing/upgrade-status")
async def get_upgrade_status(request: Request):
    user = _require_auth(request)
    user_id = str(user.get("id") or "").strip()
    if not user_id:
        raise HTTPException(status_code=401, detail="找不到使用者 ID")

    pending = supabase_adapter.get_pending_upgrade_request(user_id)
    return {"success": True, "has_pending": bool(pending), "pending": pending}


@router.post("/billing/upgrade-request")
async def upgrade_request(req: UpgradeRequest, request: Request):
    """
    建立升級申請（先建 pending，再嘗試通知）。

    設計原則：
    1. pending 建立成功就要回成功（通知可降級）。
    2. schema 漂移或通知失敗都不該讓使用者收到 500。
    """
    user = _require_auth(request)
    user_id = str(user.get("id") or "").strip()
    user_email = str(user.get("email") or "").strip()
    if not user_id or not user_email:
        raise HTTPException(status_code=400, detail="缺少使用者資訊")

    metadata = user.get("user_metadata") if isinstance(user.get("user_metadata"), dict) else {}
    user_name = str(metadata.get("full_name") or user.get("name") or user_email.split("@", 1)[0]).strip()

    pending_create: dict[str, Any] | None = None
    try:
        created = supabase_adapter.create_pending_upgrade_request(
            user_id=user_id,
            user_email=user_email,
            user_name=user_name,
            plan=req.plan,
            billing_cycle=req.billing_cycle,
        )
        pending_create = created if isinstance(created, dict) else None
    except Exception as e:
        print(f"[Billing] create_pending_upgrade_request exception: {type(e).__name__}: {e}")
        pending_create = None

    if pending_create and not pending_create.get("success"):
        if pending_create.get("reason") == "pending_exists":
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "你已有待審核升級申請，請先等待管理員處理。",
                    "code": "pending_exists",
                },
            )
        pending_create = None

    # Schema 漂移/異常時，直接回退到 memory pending，避免 500
    if not pending_create:
        recovered = supabase_adapter.get_pending_upgrade_request(user_id)
        if not recovered:
            recovered = _build_memory_pending(
                user_id=user_id,
                user_email=user_email,
                user_name=user_name,
                plan=req.plan,
                billing_cycle=req.billing_cycle,
            )
            try:
                supabase_adapter._pending_upgrade_mem[user_id] = recovered  # noqa: SLF001
            except Exception:
                pass
        pending_create = {
            "success": True,
            "request_id": str(recovered.get("id") or f"UPG-{int(time.time())}"),
            "pending": recovered,
            "message": "pending_fallback_created",
        }

    request_id = str(pending_create.get("request_id") or "")
    pending = pending_create.get("pending") if isinstance(pending_create.get("pending"), dict) else None

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
        if isinstance(email_result, dict):
            notify_success = bool(email_result.get("success"))
            notify_provider = email_result.get("provider")
            notify_message = str(email_result.get("message") or "")
            notify_code = email_result.get("code")
    except Exception as e:
        notify_success = False
        notify_provider = "exception"
        notify_message = f"通知服務異常: {e}"
        notify_code = "notification_exception"

    if notify_success:
        message = "升級申請已建立，系統已通知管理員，預計 1-5 個工作天內完成審核。"
    else:
        extra = f"（通知失敗：{notify_message}）" if notify_message else ""
        message = f"升級申請已建立，但通知發送失敗，請稍後到管理後台確認{extra}"

    return {
        "success": True,
        "message": message,
        "order_id": request_id,
        "plan": req.plan,
        "billing_cycle": req.billing_cycle,
        "has_pending": True,
        "pending": pending,
        "notify_success": notify_success,
        "notify_provider": notify_provider,
        "notify_code": notify_code,
    }
