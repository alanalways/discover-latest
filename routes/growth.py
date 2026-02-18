"""Growth feature APIs: investor quiz, market scanner, weekly picks."""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from services.investor_quiz import calculate_profile
from services.market_scanner import scan_market
from services.weekly_picks import generate_weekly_picks

router = APIRouter()


class InvestorQuizRequest(BaseModel):
    answers: List[int] = Field(default_factory=list, min_items=1)
    occupation: str = "other"
    income: str = "50k_100k"


def _extract_user_id_optional(auth_header: str) -> Optional[str]:
    """可選 Auth：token 存在就解析 user_id，失敗靜默回 None。"""
    if not auth_header.startswith("Bearer "):
        return None
    token = auth_header.split(" ", 1)[1].strip()
    if not token:
        return None
    try:
        from services.auth_service import auth_service
        user = auth_service.verify_session(token)
        return user.get("id") if user else None
    except Exception:
        return None


@router.post("/growth/investor-quiz")
async def investor_quiz(req: InvestorQuizRequest, request: Request):
    profile = calculate_profile(
        answers=req.answers,
        occupation=req.occupation,
        income=req.income,
    )

    saved = False
    auth_header = request.headers.get("Authorization", "")
    user_id = _extract_user_id_optional(auth_header)
    if user_id:
        try:
            from adapters.supabase_adapter import supabase_adapter
            saved = supabase_adapter.save_investor_profile(
                user_id=user_id,
                profile_type=profile["primary"],
                profile_name=profile["profile_name"],
            )
        except Exception:
            saved = False

    return {"success": True, "profile": profile, "saved": saved}


@router.get("/growth/scanner")
async def growth_scanner(limit: Optional[int] = 20):
    rows = scan_market(limit=max(1, min(100, int(limit or 20))))
    return {"success": True, "count": len(rows), "items": rows}


@router.get("/growth/weekly-picks")
async def growth_weekly_picks(limit: Optional[int] = 5):
    rows = generate_weekly_picks(limit=max(1, min(10, int(limit or 5))))
    return {"success": True, "count": len(rows), "items": rows}
