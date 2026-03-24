"""
backend/api/routes/scanner.py
掃描器 API（Sonnet 撰寫）

- GET /api/scanner          — 最新評級列表
- POST /api/scanner/run     — 手動觸發批次掃描
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query

from backend.api.routes.auth import UserInfo, require_admin
from backend.data.storage.supabase_client import get_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/scanner", tags=["scanner"])

_BULLISH_RATINGS = {"buy", "strong_buy", "bullish", "cautious_bullish"}
_ALL_RATINGS     = {"buy", "strong_buy", "hold", "sell", "strong_sell",
                    "bullish", "bearish", "neutral",
                    "cautious_bullish", "cautious_bearish"}


@router.get("")
async def get_scanner_results(
    market: Optional[str] = Query(default=None, description="TW / TWO / US"),
    rating: Optional[str] = Query(default=None, description="buy / sell / hold …"),
    limit:  int           = Query(default=20, le=100),
):
    """
    從 reports 表取最新評級清單（去重，每檔只取最新一筆）。
    """
    client = get_client()
    if not client:
        return {"error": "Database unavailable", "items": []}

    try:
        query = (
            client.table("reports")
            .select(
                "id, symbol, market, rating, confidence_score, "
                "target_price_low, target_price_high, created_at, final_report"
            )
            .eq("is_archived", False)
            .order("created_at", desc=True)
            .limit(limit * 3)   # 多取，後面去重
        )
        if market:
            query = query.eq("market", market)
        if rating:
            query = query.eq("rating", rating)

        result = query.execute()
        rows   = result.data or []

        # 每檔只保留最新一筆
        seen:  set  = set()
        items: list = []
        for r in rows:
            key = (r["symbol"], r["market"])
            if key not in seen:
                seen.add(key)
                items.append(r)
            if len(items) >= limit:
                break

        return {"items": items, "total": len(items)}

    except Exception as e:
        logger.error(f"[Scanner] 查詢失敗: {e}")
        return {"error": str(e), "items": []}


@router.get("/top-bullish")
async def get_top_bullish(
    market: Optional[str] = Query(default=None),
    limit:  int           = Query(default=10, le=50),
):
    """
    取最高信心度的偏多股票（rating 為 buy/strong_buy/bullish）。
    """
    client = get_client()
    if not client:
        return {"items": []}

    try:
        result = (
            client.table("reports")
            .select(
                "id, symbol, market, rating, confidence_score, "
                "target_price_low, target_price_high, created_at, final_report"
            )
            .eq("is_archived", False)
            .in_("rating", list(_BULLISH_RATINGS))
            .order("confidence_score", desc=True)
            .limit(limit * 2)
        )
        if market:
            result = result.eq("market", market)

        data = result.execute().data or []

        # 去重
        seen:  set  = set()
        items: list = []
        for r in data:
            key = (r["symbol"], r["market"])
            if key not in seen:
                seen.add(key)
                items.append(r)
            if len(items) >= limit:
                break

        return {"items": items}

    except Exception as e:
        logger.error(f"[Scanner] top-bullish 查詢失敗: {e}")
        return {"items": []}


@router.get("/score")
async def score_symbols(
    symbols: Optional[str] = Query(default=None, description="逗號分隔股票代號"),
    limit:   int           = Query(default=20, le=50),
):
    """
    即時 5 因子評分（momentum/volume/volatility/valuation/trend）。
    不依賴 DB，直接從 Yahoo Finance 取資料計算。
    """
    try:
        from backend.services.market_scanner import scan_market
        sym_list = [s.strip().upper() for s in symbols.split(",")] if symbols else None
        results = scan_market(limit=limit, symbols=sym_list)
        return {"items": results, "total": len(results)}
    except Exception as e:
        logger.error(f"[Scanner] score 失敗: {e}")
        return {"error": str(e), "items": []}


@router.post("/run")
async def run_scanner(
    market: str = Query(default="TW", description="TW / US"),
    admin: UserInfo = Depends(require_admin),
):
    """
    手動觸發 CEO Agent 的 hourly_watchlist_scan。
    （通常由心跳排程自動呼叫，此端點供管理員手動觸發）
    """
    try:
        from backend.agents.ceo_agent import get_ceo_agent
        ceo = get_ceo_agent()
        market = market.strip().upper()
        if market not in {"TW", "TWO", "US"}:
            return {"status": "error", "message": "market must be TW, TWO, or US"}

        result = ceo.hourly_watchlist_scan(market_filter=market)
        return {
            "status": "ok",
            "message": f"掃描已觸發（market={market}）",
            "result": result,
            "requested_by": admin.user_id,
        }
    except Exception as e:
        logger.error(f"[Scanner] run 失敗: {e}")
        return {"status": "error", "message": str(e)}
