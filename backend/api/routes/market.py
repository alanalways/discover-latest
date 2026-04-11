"""
backend/api/routes/market.py
市場資料 API — 大盤指數、宏觀指標、市場狀態

- GET /api/market/overview     — 完整市場概覽
- GET /api/market/indices      — 主要指數
- GET /api/market/top20        — Top 20 個股
- GET /api/market/macro        — 宏觀指標
- GET /api/market/hours        — 開盤時間狀態
"""

import logging
from typing import Optional

from fastapi import APIRouter, Query

from backend.config import (
    BETA_LABEL,
    BETA_MESSAGE,
    BETA_NOTES,
    BETA_OPEN_ACCESS,
    BETA_TARGET_AUDIENCE,
    STUDENT_PRICING,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/market", tags=["market"])


@router.get("/product-config")
async def product_config():
    """前台產品設定：免費 Beta 狀態、目標客群與未來方案參考。"""
    return {
        "beta_open": BETA_OPEN_ACCESS,
        "current_mode": "free_beta",
        "beta_label": BETA_LABEL,
        "beta_message": BETA_MESSAGE,
        "beta_notes": BETA_NOTES,
        "target_audience": BETA_TARGET_AUDIENCE,
        "future_pricing_note": "現階段不收費，先用免費版累積穩定使用者與回饋；正式商業化與方案規劃等免費版穩定後再評估。",
        "student_pricing": STUDENT_PRICING,
    }


@router.get("/overview")
async def market_overview():
    """完整市場概覽（指數 + Top 20 + 開盤狀態）。"""
    try:
        from backend.services.market_overview import get_full_overview
        return get_full_overview()
    except Exception as e:
        logger.error(f"[Market] overview 失敗: {e}")
        return {"error": str(e)}


@router.get("/indices")
async def market_indices():
    """主要指數與 ETF 報價。"""
    try:
        from backend.services.market_overview import get_indices
        return get_indices()
    except Exception as e:
        logger.error(f"[Market] indices 失敗: {e}")
        return {"error": str(e)}


@router.get("/top20")
async def market_top20(
    market: str = Query(default="tw", description="tw / us"),
):
    """Top 20 個股（按漲幅排序）。"""
    try:
        from backend.services.market_overview import get_top20
        items = get_top20(market)
        return {"market": market, "items": items}
    except Exception as e:
        logger.error(f"[Market] top20 失敗: {e}")
        return {"error": str(e), "items": []}


@router.get("/macro")
async def macro_indicators():
    """宏觀市場指標（VIX, 美債, 美元, 油金）。"""
    try:
        from backend.services.macro_context import get_macro_context
        return get_macro_context()
    except Exception as e:
        logger.error(f"[Market] macro 失敗: {e}")
        return {"error": str(e)}


@router.get("/hours")
async def market_hours():
    """台美股開盤狀態。"""
    try:
        from backend.services.market_overview import get_market_hours_snapshot
        return get_market_hours_snapshot()
    except Exception as e:
        logger.error(f"[Market] hours 失敗: {e}")
        return {"error": str(e)}
