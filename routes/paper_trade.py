"""Paper trading API routes."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

router = APIRouter()
logger = logging.getLogger(__name__)

_TW_TZ = ZoneInfo("Asia/Taipei")

# In-memory paper trades (per user).
_paper_trades: Dict[str, List[Dict[str, Any]]] = {}


class PaperTradeRequest(BaseModel):
    symbol: str
    action: str = "buy"
    shares: float = 1
    price: Optional[float] = None


def _extract_user_id(auth_header: str) -> Optional[str]:
    if not auth_header or not auth_header.startswith("Bearer "):
        return None
    token = auth_header[7:]
    try:
        from helpers import verify_supabase_token
        user = verify_supabase_token(token)
        return user.get("sub") if user else None
    except Exception:
        return None


def _safe_float(val: Any, default: float = 0.0) -> float:
    try:
        v = float(val)
        return v if v == v else default
    except (TypeError, ValueError):
        return default


@router.post("/paper-trade/execute")
async def execute_paper_trade(req: PaperTradeRequest, request: Request):
    """Execute a paper trade."""
    auth_header = request.headers.get("Authorization", "")
    user_id = _extract_user_id(auth_header)
    if not user_id:
        raise HTTPException(status_code=401, detail="請先登入")

    symbol = req.symbol.strip().upper()
    if not symbol:
        raise HTTPException(status_code=400, detail="請輸入股票代號")

    # Get current price if not specified
    price = req.price
    if price is None or price <= 0:
        try:
            from services.stock_service import stock_service
            data = await run_in_threadpool(stock_service.get_stock_data, symbol, None, "1y")
            if data:
                history = data.get("history") or []
                if history:
                    price = _safe_float(history[-1].get("close"))
        except Exception:
            pass
    if not price or price <= 0:
        raise HTTPException(status_code=400, detail=f"無法取得 {symbol} 的即時價格")

    now = datetime.now(_TW_TZ)
    trade = {
        "id": str(uuid.uuid4())[:8],
        "symbol": symbol,
        "action": req.action,
        "shares": req.shares,
        "price": round(price, 2),
        "timestamp": now.isoformat(),
        "value": round(price * req.shares, 2),
    }

    if user_id not in _paper_trades:
        _paper_trades[user_id] = []
    _paper_trades[user_id].append(trade)

    return {"success": True, "trade": trade}


@router.get("/paper-trade/positions")
async def get_paper_positions(request: Request):
    """Get user's paper trading positions."""
    auth_header = request.headers.get("Authorization", "")
    user_id = _extract_user_id(auth_header)
    if not user_id:
        raise HTTPException(status_code=401, detail="請先登入")

    trades = _paper_trades.get(user_id, [])

    # Aggregate positions
    positions: Dict[str, Dict[str, Any]] = {}
    for t in trades:
        sym = t["symbol"]
        if sym not in positions:
            positions[sym] = {"symbol": sym, "shares": 0, "avg_cost": 0, "total_invested": 0}

        if t["action"] == "buy":
            old_shares = positions[sym]["shares"]
            old_total = positions[sym]["total_invested"]
            new_shares = old_shares + t["shares"]
            new_total = old_total + t["value"]
            positions[sym]["shares"] = new_shares
            positions[sym]["total_invested"] = new_total
            positions[sym]["avg_cost"] = round(new_total / new_shares, 2) if new_shares > 0 else 0
        elif t["action"] == "sell":
            positions[sym]["shares"] = max(0, positions[sym]["shares"] - t["shares"])

    # Get current prices
    active_positions = []
    for sym, pos in positions.items():
        if pos["shares"] <= 0:
            continue

        current_price = pos["avg_cost"]
        try:
            from services.stock_service import stock_service
            data = await run_in_threadpool(stock_service.get_stock_data, sym, None, "1y")
            if data:
                history = data.get("history") or []
                if history:
                    current_price = _safe_float(history[-1].get("close"), pos["avg_cost"])
        except Exception:
            pass

        market_value = round(current_price * pos["shares"], 2)
        cost_value = round(pos["avg_cost"] * pos["shares"], 2)
        pnl = round(market_value - cost_value, 2)
        pnl_pct = round((pnl / cost_value) * 100, 2) if cost_value > 0 else 0

        active_positions.append({
            **pos,
            "current_price": current_price,
            "market_value": market_value,
            "cost_value": cost_value,
            "pnl": pnl,
            "pnl_pct": pnl_pct,
        })

    total_value = sum(p["market_value"] for p in active_positions)
    total_cost = sum(p["cost_value"] for p in active_positions)
    total_pnl = round(total_value - total_cost, 2)
    total_pnl_pct = round((total_pnl / total_cost) * 100, 2) if total_cost > 0 else 0

    return {
        "positions": active_positions,
        "trades": trades[-20:],
        "summary": {
            "total_value": total_value,
            "total_cost": total_cost,
            "total_pnl": total_pnl,
            "total_pnl_pct": total_pnl_pct,
            "position_count": len(active_positions),
        },
    }
