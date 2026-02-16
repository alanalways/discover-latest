"""Growth feature APIs: investor quiz, market scanner, weekly picks."""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from services.investor_quiz import calculate_profile
from services.market_scanner import scan_market
from services.weekly_picks import generate_weekly_picks

router = APIRouter()


class InvestorQuizRequest(BaseModel):
    answers: List[int] = Field(default_factory=list, min_items=1)
    occupation: str = "other"
    income: str = "50k_100k"


@router.post("/growth/investor-quiz")
async def investor_quiz(req: InvestorQuizRequest):
    profile = calculate_profile(
        answers=req.answers,
        occupation=req.occupation,
        income=req.income,
    )
    return {"success": True, "profile": profile}


@router.get("/growth/scanner")
async def growth_scanner(limit: Optional[int] = 20):
    rows = scan_market(limit=max(1, min(100, int(limit or 20))))
    return {"success": True, "count": len(rows), "items": rows}


@router.get("/growth/weekly-picks")
async def growth_weekly_picks(limit: Optional[int] = 5):
    rows = generate_weekly_picks(limit=max(1, min(10, int(limit or 5))))
    return {"success": True, "count": len(rows), "items": rows}
