"""
Watchlist API — 自選清單 + Portfolio CRUD
"""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional, List

router = APIRouter()


class WatchlistAddRequest(BaseModel):
    symbol: str


class AlertAddRequest(BaseModel):
    symbol: str
    target_price: float
    direction: str = "above"  # above | below | gte | lte


# ── 自選清單 ──
@router.get("/watchlist")
async def get_watchlist(request: Request):
    """取得自選清單"""
    user_id = _require_auth(request)
    try:
        from adapters.supabase_adapter import supabase_adapter
        watchlist = supabase_adapter.get_user_watchlist(user_id)
        return {"watchlist": watchlist or []}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/watchlist/add")
async def add_to_watchlist(req: WatchlistAddRequest, request: Request):
    """新增股票到自選清單"""
    user_id = _require_auth(request)
    try:
        from adapters.supabase_adapter import supabase_adapter
        symbol = (req.symbol or "").strip().upper()
        if not symbol:
            raise HTTPException(status_code=400, detail="symbol 不可為空")
        result = supabase_adapter.add_to_watchlist(user_id, symbol)
        if not result:
            raise HTTPException(status_code=500, detail="自選清單寫入失敗（請確認 watchlist/watchlists 或 portfolios 設定）")
        return {"success": result}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/watchlist/{symbol}")
async def remove_from_watchlist(symbol: str, request: Request):
    """從自選清單移除"""
    user_id = _require_auth(request)
    try:
        from adapters.supabase_adapter import supabase_adapter
        target = (symbol or "").strip().upper()
        if not target:
            raise HTTPException(status_code=400, detail="symbol 不可為空")
        result = supabase_adapter.remove_from_watchlist(user_id, target)
        if not result:
            raise HTTPException(status_code=404, detail=f"找不到 {target} 或移除失敗")
        return {"success": result}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── 價格警報 ──
@router.get("/alerts")
async def get_alerts(request: Request):
    """取得價格警報"""
    user_id = _require_auth(request)
    try:
        from adapters.supabase_adapter import supabase_adapter
        alerts = supabase_adapter.get_user_alerts(user_id)
        return {"alerts": alerts or []}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/alerts/add")
async def add_alert(req: AlertAddRequest, request: Request):
    """新增價格警報"""
    user_id = _require_auth(request)
    try:
        from services.feature_gate import can_access
        from services.feature_gate import get_limit
        from services.rate_limiter import rate_limiter

        tier = rate_limiter.check_and_downgrade(user_id)
        if not can_access(tier, "price_alert"):
            raise HTTPException(status_code=403, detail="此功能需要升級方案")

        from adapters.supabase_adapter import supabase_adapter
        alerts = supabase_adapter.get_user_alerts(user_id) or []
        max_alerts = get_limit(tier, "price_alert_max")
        if max_alerts > 0 and len(alerts) >= max_alerts:
            raise HTTPException(status_code=403, detail=f"已達警報上限（{max_alerts}）")

        direction = (req.direction or "above").lower()
        if direction in ("gte", "above"):
            normalized_direction = "above"
        elif direction in ("lte", "below"):
            normalized_direction = "below"
        else:
            raise HTTPException(status_code=400, detail="direction 僅支援 above/below/gte/lte")

        result = supabase_adapter.add_alert(
            user_id, req.symbol, req.target_price, normalized_direction
        )
        return {"success": result}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/alerts/{alert_id}")
async def delete_alert(alert_id: str, request: Request):
    """刪除警報"""
    user_id = _require_auth(request)
    try:
        from adapters.supabase_adapter import supabase_adapter
        result = supabase_adapter.delete_alert(alert_id, user_id)
        return {"success": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Portfolio ──
@router.get("/portfolio")
async def get_portfolio(request: Request):
    """取得投資組合"""
    user_id = _require_auth(request)
    try:
        from adapters.supabase_adapter import supabase_adapter
        portfolio = supabase_adapter.get_user_portfolio(user_id)
        return {"portfolio": portfolio or []}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _require_auth(request: Request) -> str:
    """驗證並回傳 user_id，未登入則 401"""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="請先登入")
    token = auth_header.split(" ", 1)[1]
    try:
        from services.auth_service import auth_service
        user = auth_service.verify_session(token)
        if not user:
            raise HTTPException(status_code=401, detail="Session 已過期")
        return user.get("id", "")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="驗證失敗")
