"""
backend/api/routes/beta.py
免費 Beta 營運 API — 回饋蒐集、簡易營運概覽

- GET  /api/beta/overview   — 公開 Beta 概覽
- POST /api/beta/feedback   — 送出 Beta 回饋（可匿名 / 可帶登入資訊）
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from backend.config import BETA_LABEL, BETA_MESSAGE, BETA_NOTES, BETA_TARGET_AUDIENCE

router = APIRouter(prefix="/beta", tags=["beta"])


class BetaFeedbackCreate(BaseModel):
    category: str = Field(default="general", description="ux | bug | idea | content | speed | general")
    message: str = Field(min_length=8, max_length=1200)
    page: str | None = Field(default=None, max_length=120)
    contact_email: str | None = Field(default=None, max_length=255)
    rating: int | None = Field(default=None, ge=1, le=5)
    would_recommend: bool | None = None


async def get_optional_current_user(
    authorization: str | None = Header(default=None),
) -> Any | None:
    """Lazy import auth dependency to avoid test/runtime import crashes when auth stack is unavailable."""
    if not authorization:
        return None

    try:
        from backend.api.routes.auth import get_current_user as auth_get_current_user
    except Exception:
        return None

    return await auth_get_current_user(authorization=authorization)


@router.get("/overview")
async def beta_overview():
    """公開免費 Beta 概覽與回饋摘要。"""
    from backend.data.storage.supabase_client import (
        get_ai_usage_today,
        get_beta_feedback_summary,
        get_client,
    )

    client = get_client()
    reports_total = 0
    ratings_total = 0
    if client:
        try:
            reports_total = client.table("reports").select("id", count="exact").eq("is_archived", False).execute().count or 0
        except Exception:
            reports_total = 0
        try:
            ratings_total = client.table("report_ratings").select("id", count="exact").execute().count or 0
        except Exception:
            ratings_total = 0

    feedback = get_beta_feedback_summary()
    return {
        "label": BETA_LABEL,
        "message": BETA_MESSAGE,
        "notes": BETA_NOTES,
        "target_audience": BETA_TARGET_AUDIENCE,
        "stats": {
            "reports_total": reports_total,
            "ratings_total": ratings_total,
            "feedback_total": feedback.get("total_feedback", 0),
        },
        "feedback": feedback,
    }


@router.post("/feedback")
async def create_feedback(
    body: BetaFeedbackCreate,
    current_user: Any | None = Depends(get_optional_current_user),
):
    """提交一筆 Beta 回饋。"""
    category = str(body.category or "general").strip().lower()
    if category not in {"ux", "bug", "idea", "content", "speed", "general"}:
        raise HTTPException(status_code=400, detail="category must be one of ux, bug, idea, content, speed, general")

    from backend.data.storage.supabase_client import create_beta_feedback

    row = create_beta_feedback({
        "category": category,
        "message": body.message,
        "page": body.page,
        "contact_email": body.contact_email,
        "rating": body.rating,
        "would_recommend": body.would_recommend,
        "user_id": current_user.user_id if current_user else None,
        "user_email": current_user.email if current_user else None,
        "user_name": current_user.name if current_user else None,
    })

    if not row:
        raise HTTPException(status_code=500, detail="目前無法送出回饋，請稍後再試")

    return {
        "status": "ok",
        "message": "收到你的回饋了，這會直接進入 Beta 改版清單。",
        "feedback_id": row.get("id"),
        "storage_backend": row.get("storage_backend", "database"),
        "persistent": row.get("persistent", True),
        "warning": row.get("warning"),
    }
