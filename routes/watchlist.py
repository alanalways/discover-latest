"""Watchlist API: watchlist, alerts, portfolio, and portfolio health."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

router = APIRouter()


class WatchlistAddRequest(BaseModel):
    symbol: str


class AlertAddRequest(BaseModel):
    symbol: str
    target_price: float
    direction: str = "above"  # above | below | gte | lte


@router.get("/watchlist")
async def get_watchlist(request: Request):
    """Get current user's watchlist."""
    user_id = _require_auth(request)
    from adapters.supabase_adapter import supabase_adapter

    try:
        watchlist = supabase_adapter.get_user_watchlist(user_id)
        return {"watchlist": watchlist or []}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"讀取自選清單失敗: {e}")


@router.post("/watchlist/add")
async def add_to_watchlist(req: WatchlistAddRequest, request: Request):
    """Add a symbol to watchlist."""
    user_id = _require_auth(request)
    from adapters.supabase_adapter import supabase_adapter

    symbol = (req.symbol or "").strip().upper()
    if not symbol:
        raise HTTPException(status_code=400, detail="symbol 不可為空")

    try:
        result = supabase_adapter.add_to_watchlist(user_id, symbol)
        if not result:
            raise HTTPException(
                status_code=500,
                detail="自選清單寫入失敗（請確認 watchlist/watchlists 或 portfolios 設定）",
            )
        return {"success": True, "symbol": symbol}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"加入自選失敗: {e}")


@router.delete("/watchlist/{symbol}")
async def remove_from_watchlist(symbol: str, request: Request):
    """Remove a symbol from watchlist."""
    user_id = _require_auth(request)
    from adapters.supabase_adapter import supabase_adapter

    target = (symbol or "").strip().upper()
    if not target:
        raise HTTPException(status_code=400, detail="symbol 不可為空")

    try:
        result = supabase_adapter.remove_from_watchlist(user_id, target)
        if not result:
            raise HTTPException(status_code=404, detail=f"找不到 {target} 或刪除失敗")
        return {"success": True, "symbol": target}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"刪除自選失敗: {e}")


@router.get("/alerts")
async def get_alerts(request: Request):
    """Get current user's alerts."""
    user_id = _require_auth(request)
    from adapters.supabase_adapter import supabase_adapter

    try:
        alerts = supabase_adapter.get_user_alerts(user_id)
        return {"alerts": alerts or []}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"讀取警報失敗: {e}")


@router.post("/alerts/add")
async def add_alert(req: AlertAddRequest, request: Request):
    """Add a price alert."""
    user_id = _require_auth(request)
    from adapters.supabase_adapter import supabase_adapter
    from services.feature_gate import can_access, get_limit
    from services.rate_limiter import rate_limiter

    tier = rate_limiter.check_and_downgrade(user_id)
    if not can_access(tier, "price_alert"):
        raise HTTPException(status_code=403, detail="你的方案尚未開放價格警報")

    symbol = (req.symbol or "").strip().upper()
    if not symbol:
        raise HTTPException(status_code=400, detail="symbol 不可為空")
    if req.target_price <= 0:
        raise HTTPException(status_code=400, detail="target_price 必須大於 0")

    try:
        alerts = supabase_adapter.get_user_alerts(user_id) or []
        max_alerts = int(get_limit(tier, "price_alert_max") or 0)
        if max_alerts > 0 and len(alerts) >= max_alerts:
            raise HTTPException(status_code=403, detail=f"價格警報上限為 {max_alerts}")

        direction = (req.direction or "above").lower()
        if direction in ("gte", "above"):
            normalized_direction = "above"
        elif direction in ("lte", "below"):
            normalized_direction = "below"
        else:
            raise HTTPException(status_code=400, detail="direction 僅支援 above/below/gte/lte")

        result = supabase_adapter.add_alert(
            user_id=user_id,
            symbol=symbol,
            target_price=req.target_price,
            direction=normalized_direction,
        )
        return {"success": bool(result)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"新增警報失敗: {e}")


@router.delete("/alerts/{alert_id}")
async def delete_alert(alert_id: str, request: Request):
    """Delete an alert."""
    user_id = _require_auth(request)
    from adapters.supabase_adapter import supabase_adapter

    try:
        result = supabase_adapter.delete_alert(alert_id, user_id)
        return {"success": bool(result)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"刪除警報失敗: {e}")


@router.get("/portfolio")
async def get_portfolio(request: Request):
    """Get user portfolio."""
    user_id = _require_auth(request)
    from adapters.supabase_adapter import supabase_adapter

    try:
        portfolio = supabase_adapter.get_user_portfolio(user_id)
        return {"portfolio": portfolio or []}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"讀取投資組合失敗: {e}")


@router.get("/portfolio/health")
async def get_portfolio_health(
    request: Request,
    benchmark: str = Query("0050", description="Benchmark symbol"),
):
    """
    Portfolio health check.

    Returns:
    - per-holding market value, pnl, weight
    - total summary and simple diversification score
    - benchmark 1Y return
    """
    user_id = _require_auth(request)
    from adapters.supabase_adapter import supabase_adapter
    from services.stock_service import stock_service

    holdings = supabase_adapter.get_user_portfolio(user_id) or []
    if not holdings:
        return {
            "portfolio": [],
            "summary": {
                "total_market_value": 0.0,
                "total_cost": 0.0,
                "total_pnl": 0.0,
                "total_pnl_pct": 0.0,
                "diversification_score": 0,
                "max_weight_pct": 0.0,
                "risk_level": "low",
            },
            "suggestions": ["目前沒有持股，先建立 3-5 檔不同產業配置可提升分散度。"],
            "benchmark": {"symbol": benchmark.upper(), "return_1y_pct": 0.0},
        }

    async def enrich(holding: dict[str, Any]) -> dict[str, Any]:
        symbol = str(holding.get("symbol") or "").strip().upper()
        shares = float(holding.get("shares") or 0.0)
        avg_cost = float(holding.get("avg_cost") or 0.0)
        current_price = float(holding.get("current_price") or 0.0)

        try:
            stock = await stock_service.get_stock_data(symbol=symbol, period="1y")
            info = stock.get("info", {}) if isinstance(stock, dict) else {}
            history = stock.get("history", []) if isinstance(stock, dict) else []
            last_close = float(history[-1].get("close", 0) or 0) if history else 0.0
            if last_close > 0:
                current_price = last_close
            else:
                info_price = info.get("price")
                if info_price is not None:
                    current_price = float(info_price or 0.0)
        except Exception:
            pass

        market_value = shares * current_price
        cost_value = shares * avg_cost
        pnl = market_value - cost_value
        pnl_pct = (pnl / cost_value * 100) if cost_value > 0 else 0.0
        return {
            "symbol": symbol,
            "shares": shares,
            "avg_cost": avg_cost,
            "current_price": current_price,
            "market_value": market_value,
            "cost_value": cost_value,
            "pnl": pnl,
            "pnl_pct": pnl_pct,
        }

    enriched = await asyncio.gather(*[enrich(h) for h in holdings])
    total_market_value = sum(max(0.0, float(h.get("market_value") or 0.0)) for h in enriched)
    total_cost = sum(max(0.0, float(h.get("cost_value") or 0.0)) for h in enriched)
    total_pnl = total_market_value - total_cost
    total_pnl_pct = (total_pnl / total_cost * 100) if total_cost > 0 else 0.0

    for row in enriched:
        mv = float(row.get("market_value") or 0.0)
        row["weight_pct"] = (mv / total_market_value * 100) if total_market_value > 0 else 0.0

    sorted_by_weight = sorted(enriched, key=lambda x: float(x.get("weight_pct") or 0.0), reverse=True)
    max_weight_pct = float(sorted_by_weight[0].get("weight_pct") or 0.0) if sorted_by_weight else 0.0
    diversification_score = int(max(0, min(100, round(100 - max_weight_pct))))

    if max_weight_pct >= 55:
        risk_level = "high"
    elif max_weight_pct >= 35:
        risk_level = "medium"
    else:
        risk_level = "low"

    suggestions: list[str] = []
    if max_weight_pct >= 55:
        suggestions.append("單一持股集中度偏高，建議增加 3-5 檔不同產業分散風險。")
    elif max_weight_pct >= 35:
        suggestions.append("持股集中度中等，可再增加非同產業標的降低波動。")
    else:
        suggestions.append("持股分散度良好，建議維持紀律再平衡。")

    if total_pnl_pct < -12:
        suggestions.append("目前整體報酬偏弱，建議重新檢視停損與倉位管理。")
    elif total_pnl_pct > 18:
        suggestions.append("目前整體報酬偏強，留意獲利了結與風險回撤。")

    benchmark_symbol = (benchmark or "0050").strip().upper()
    benchmark_return = 0.0
    try:
        bm = await stock_service.get_stock_data(symbol=benchmark_symbol, period="1y")
        history = bm.get("history", []) if isinstance(bm, dict) else []
        if len(history) >= 2:
            first = float(history[0].get("close", 0) or 0.0)
            last = float(history[-1].get("close", 0) or 0.0)
            if first > 0:
                benchmark_return = (last / first - 1) * 100
    except Exception:
        benchmark_return = 0.0

    return {
        "portfolio": sorted_by_weight,
        "summary": {
            "total_market_value": round(total_market_value, 2),
            "total_cost": round(total_cost, 2),
            "total_pnl": round(total_pnl, 2),
            "total_pnl_pct": round(total_pnl_pct, 2),
            "diversification_score": diversification_score,
            "max_weight_pct": round(max_weight_pct, 2),
            "risk_level": risk_level,
        },
        "suggestions": suggestions,
        "benchmark": {
            "symbol": benchmark_symbol,
            "return_1y_pct": round(benchmark_return, 2),
        },
    }


def _require_auth(request: Request) -> str:
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="請先登入")

    token = auth_header.split(" ", 1)[1]
    try:
        from services.auth_service import auth_service

        user = auth_service.verify_session(token)
        if not user:
            raise HTTPException(status_code=401, detail="Session 驗證失敗")
        user_id = str(user.get("id") or "")
        if not user_id:
            raise HTTPException(status_code=401, detail="缺少 user_id")
        return user_id
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="登入狀態失效")
