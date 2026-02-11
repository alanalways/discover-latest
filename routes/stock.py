"""
Stock API — 個股資料 + 搜尋 + 基本面 + 籌碼面
"""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional

router = APIRouter()


@router.get("/stock/search/{query}")
async def search_stocks(query: str, limit: int = Query(20, le=50)):
    """搜尋股票代號或名稱"""
    try:
        from services.stock_service import stock_service
        results = await stock_service.search_symbols(query, limit)
        return {"results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stock/{symbol}")
async def get_stock(symbol: str, period: str = Query("1y", pattern="^(1mo|3mo|6mo|1y|2y|5y)$")):
    """取得完整股票資料（基本資訊 + 最新價格 + PER/PBR）"""
    try:
        from services.stock_service import stock_service

        # 取得完整資料（async）
        data = await stock_service.get_stock_data(symbol, period=period)

        if not data:
            raise HTTPException(status_code=404, detail=f"找不到股票: {symbol}")

        info = data.get("info") or {}
        history = data.get("history") or []

        # 從歷史資料取最新價格
        latest = {}
        if history and len(history) > 0:
            last = history[-1]
            prev = history[-2] if len(history) > 1 else last
            close = float(last.get("close", 0))
            prev_close = float(prev.get("close", close))
            change = close - prev_close
            change_pct = (change / prev_close * 100) if prev_close > 0 else 0

            latest = {
                "price": close,
                "change": round(change, 2),
                "change_pct": round(change_pct, 2),
                "open": float(last.get("open", 0)),
                "high": float(last.get("high", 0)),
                "low": float(last.get("low", 0)),
                "volume": int(last.get("volume", 0)),
            }

        # 嘗試取得 PER/PBR（台股限定，不阻塞主流程）
        valuation = {}
        market = data.get("market", "")
        if market in ["TWSE", "TPEX"]:
            try:
                from adapters.finmind_adapter import finmind_adapter
                from datetime import datetime, timedelta

                start = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
                per_data = await finmind_adapter.get_tw_per_pbr(symbol, start)
                if per_data and len(per_data) > 0:
                    last_per = per_data[-1]
                    valuation = {
                        "pe_ratio": _safe_float(last_per.get("PER")),
                        "pb_ratio": _safe_float(last_per.get("PBR")),
                        "dividend_yield": _safe_float(last_per.get("dividend_yield")),
                    }
            except Exception as e:
                print(f"[Stock] PER/PBR 取得失敗 ({symbol}): {e}")

        return {
            "symbol": symbol,
            "market": market,
            "name": info.get("name"),
            "industry": info.get("industry"),
            **latest,
            **valuation,
            "updated_at": data.get("updated_at"),
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stock/{symbol}/history")
async def get_stock_history(
    symbol: str,
    period: str = Query("1y", pattern="^(1mo|3mo|6mo|1y|2y|5y)$"),
):
    """取得個股歷史 K 線資料"""
    try:
        from services.stock_service import stock_service

        data = await stock_service.get_stock_data(symbol, period=period)
        history = data.get("history") or [] if data else []

        return {
            "symbol": symbol,
            "period": period,
            "data": history,
            "count": len(history),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stock/{symbol}/fundamentals")
async def get_stock_fundamentals(symbol: str):
    """取得個股基本面資料（PER/PBR/月營收/損益表/股利）- 台股限定"""
    try:
        from services.stock_service import stock_service
        result = await stock_service.get_stock_fundamentals(symbol)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stock/{symbol}/chips")
async def get_stock_chips(symbol: str):
    """取得個股籌碼面資料（三大法人 + 融資融券）- 台股限定"""
    try:
        from services.stock_service import stock_service
        result = await stock_service.get_stock_chips(symbol)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _safe_float(val) -> Optional[float]:
    """安全轉換為 float"""
    if val is None:
        return None
    try:
        f = float(val)
        return round(f, 4) if f != 0 else None
    except (ValueError, TypeError):
        return None
