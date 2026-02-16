"""Billing API routes."""

from __future__ import annotations

import time
import logging
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from adapters.supabase_data import supabase_data_adapter

logger = logging.getLogger(__name__)

router = APIRouter()


class UpgradeRequest(BaseModel):
    plan: Literal["pro", "premium"]
    billing_cycle: Literal["monthly", "yearly"] = "monthly"


def _parse_bearer_token(auth_header: str) -> str:
    if not auth_header or not auth_header.startswith("Bearer "):
        return ""
    return auth_header.split(" ", 1)[1].strip()


def _require_auth(request: Request) -> dict[str, Any]:
    auth_header = request.headers.get("Authorization", "")
    token = _parse_bearer_token(auth_header)
    if not token:
        raise HTTPException(status_code=401, detail="請先登入")
    try:
        from services.auth_service import auth_service

        user = auth_service.verify_session(token)
        if not user:
            raise HTTPException(status_code=401, detail="Session 已失效")
        return user
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="登入驗證失敗")


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
        raise HTTPException(status_code=401, detail="缺少使用者 ID")

    pending = supabase_data_adapter.get_pending_upgrade_request(user_id)
    return {"success": True, "has_pending": bool(pending), "pending": pending}


@router.post("/billing/upgrade-request")
async def upgrade_request(req: UpgradeRequest, request: Request):
    """Create a pending upgrade request only.

    Flow is intentionally simplified:
    1) create pending request
    2) lock duplicate submissions
    3) admin handles notification/reply manually in backoffice
    """
    user = _require_auth(request)
    user_id = str(user.get("id") or "").strip()
    user_email = str(user.get("email") or "").strip()
    if not user_id or not user_email:
        raise HTTPException(status_code=400, detail="缺少使用者資料")

    metadata = user.get("user_metadata") if isinstance(user.get("user_metadata"), dict) else {}
    user_name = str(metadata.get("full_name") or user.get("name") or user_email.split("@", 1)[0]).strip()

    try:
        created = supabase_data_adapter.create_pending_upgrade_request(
            user_id=user_id,
            user_email=user_email,
            user_name=user_name,
            plan=req.plan,
            billing_cycle=req.billing_cycle,
        )
    except Exception as e:
        logger.exception(
            "create_pending_upgrade_request failed: %s: %s",
            type(e).__name__,
            e,
        )
        created = None

    if isinstance(created, dict) and not created.get("success") and created.get("reason") == "pending_exists":
        raise HTTPException(
            status_code=409,
            detail={
                "message": "你已經有待審核中的升級申請，請等待管理員處理。",
                "code": "pending_exists",
            },
        )

    pending = None
    request_id = ""
    if isinstance(created, dict) and created.get("success"):
        pending = created.get("pending") if isinstance(created.get("pending"), dict) else None
        request_id = str(created.get("request_id") or "")

    # Last-resort fallback: keep request alive in memory to avoid user-facing failure.
    if not pending:
        pending = supabase_data_adapter.get_pending_upgrade_request(user_id)

    if not pending:
        pending = _build_memory_pending(
            user_id=user_id,
            user_email=user_email,
            user_name=user_name,
            plan=req.plan,
            billing_cycle=req.billing_cycle,
        )
        try:
            supabase_data_adapter.pending_upgrade_mem[user_id] = pending
        except Exception:
            pass

    if not request_id:
        request_id = str(pending.get("id") or f"UPG-{int(time.time())}")

    return {
        "success": True,
        "message": "升級申請已建立並等待管理員審核，審核完成前不可重複送出。",
        "order_id": request_id,
        "plan": req.plan,
        "billing_cycle": req.billing_cycle,
        "has_pending": True,
        "pending": pending,
    }
