"""
Prediction Tracker API Routes
\u63d0\u4f9b AI \u9810\u6e2c\u8ffd\u8e64\u7684 Admin API \u7aef\u9ede\u3002
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter()

from utils.auth import require_admin as _require_admin


# ------------------------------------------------------------------ #
# Request models
# ------------------------------------------------------------------ #

class RecordPredictionRequest(BaseModel):
    symbol: str
    direction: str
    confidence: int
    entry_price: float
    target_price: float
    stop_price: float
    horizon_days: int = 30
    tier: str = "free"


# ------------------------------------------------------------------ #
# Routes
# ------------------------------------------------------------------ #

@router.post("/admin/predictions/evaluate")
async def evaluate_predictions(request: Request):
    """
    \u89f8\u767c\u8a55\u4f30\u6240\u6709 open \u72c0\u614b\u7684\u9810\u6e2c\u3002
    """
    _require_admin(request)
    try:
        from services.ai_prediction_tracker import prediction_tracker

        result = await prediction_tracker.evaluate_open_predictions()
        return result
    except Exception as exc:
        logger.exception("[PredictionTracker] evaluate error")
        raise HTTPException(status_code=500, detail="\u4f3a\u670d\u5668\u66ab\u6642\u7121\u6cd5\u8655\u7406\u8acb\u6c42")


@router.get("/admin/predictions/stats")
async def get_accuracy_dashboard(request: Request):
    """
    \u7372\u53d6\u7e3d\u9ad4\u6e96\u78ba\u5ea6 Dashboard\u3002
    """
    _require_admin(request)
    try:
        from services.ai_prediction_tracker import prediction_tracker

        return prediction_tracker.get_accuracy_dashboard()
    except Exception as exc:
        logger.exception("[PredictionTracker] stats error")
        raise HTTPException(status_code=500, detail="\u4f3a\u670d\u5668\u66ab\u6642\u7121\u6cd5\u8655\u7406\u8acb\u6c42")


@router.get("/admin/predictions/weekly")
async def get_weekly_report(
    request: Request,
    weeks_back: int = Query(default=1, ge=1, le=52),
):
    """
    \u9031\u5831\uff1a\u52dd\u7387\u3001\u7e3d\u6578\u3001\u5e73\u5747\u5831\u916c\u3002
    """
    _require_admin(request)
    try:
        from services.ai_prediction_tracker import prediction_tracker

        return prediction_tracker.get_weekly_stats(weeks_back=weeks_back)
    except Exception as exc:
        logger.exception("[PredictionTracker] weekly error")
        raise HTTPException(status_code=500, detail="\u4f3a\u670d\u5668\u66ab\u6642\u7121\u6cd5\u8655\u7406\u8acb\u6c42")


@router.get("/admin/predictions/monthly")
async def get_monthly_review(
    request: Request,
    year: int = Query(..., ge=2020, le=2100),
    month: int = Query(..., ge=1, le=12),
):
    """
    \u6708\u5831\uff1a\u8a73\u7d30\u5206\u6790\u3002
    """
    _require_admin(request)
    try:
        from services.ai_prediction_tracker import prediction_tracker

        return prediction_tracker.get_monthly_review(year=year, month=month)
    except Exception as exc:
        logger.exception("[PredictionTracker] monthly error")
        raise HTTPException(status_code=500, detail="\u4f3a\u670d\u5668\u66ab\u6642\u7121\u6cd5\u8655\u7406\u8acb\u6c42")


@router.get("/admin/predictions/quarterly")
async def get_quarterly_audit(
    request: Request,
    year: int = Query(..., ge=2020, le=2100),
    quarter: int = Query(..., ge=1, le=4),
):
    """
    \u5b63\u5ea6\u5be9\u8a08\uff1a\u5b8c\u6574\u5206\u6790 + \u5efa\u8b70\u3002
    """
    _require_admin(request)
    try:
        from services.ai_prediction_tracker import prediction_tracker

        return prediction_tracker.get_quarterly_audit(year=year, quarter=quarter)
    except Exception as exc:
        logger.exception("[PredictionTracker] quarterly error")
        raise HTTPException(status_code=500, detail="\u4f3a\u670d\u5668\u66ab\u6642\u7121\u6cd5\u8655\u7406\u8acb\u6c42")


@router.post("/admin/predictions/record")
async def record_prediction(request: Request, body: RecordPredictionRequest):
    """
    \u624b\u52d5\u8a18\u9304\u4e00\u7b46\u9810\u6e2c\uff08\u4e5f\u53ef\u7531 AI \u5206\u6790\u6d41\u7a0b\u81ea\u52d5\u547c\u53eb\uff09\u3002
    """
    _require_admin(request)
    try:
        from services.ai_prediction_tracker import prediction_tracker

        result = prediction_tracker.record_prediction(
            symbol=body.symbol,
            direction=body.direction,
            confidence=body.confidence,
            entry_price=body.entry_price,
            target_price=body.target_price,
            stop_price=body.stop_price,
            horizon_days=body.horizon_days,
            tier=body.tier,
        )
        if not result.get("ok"):
            raise HTTPException(status_code=400, detail=result.get("error", "Unknown error"))
        return result
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("[PredictionTracker] record error")
        raise HTTPException(status_code=500, detail="\u4f3a\u670d\u5668\u66ab\u6642\u7121\u6cd5\u8655\u7406\u8acb\u6c42")
