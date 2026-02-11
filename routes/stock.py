"""
Stock API — 個股資料、歷史價格、基本面
"""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional

router = APIRouter()


@router.get("/stock/{symbol}")
async def get_stock_info(symbol: str):
    """取得個股完整資料（基本資訊 + 歷史）"""
    try:
        from services.stock_service import stock_service
        # get_stock_data 回傳 {"info": {...}, "history": [...]}
        data = stock_service.get_stock_data(symbol)
        if not data or not data.get("info"):
            raise HTTPException(status_code=404, detail=f"找不到股票: {symbol}")
        return data.get("info", {})
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stock/{symbol}/history")
async def get_stock_history(
    symbol: str,
    period: str = Query("1y", pattern="^(1mo|3mo|6mo|1y|3y|5y)$"),
):
    """取得歷史價格資料"""
    try:
        from services.stock_service import stock_service
        data = stock_service.get_stock_data(symbol, period=period)
        if not data:
            raise HTTPException(status_code=404, detail=f"無歷史資料: {symbol}")
        history = data.get("history", [])
        # 轉為 JSON-serializable
        if hasattr(history, "to_dict"):
            return {"data": history.to_dict("records")}
        return {"data": history if isinstance(history, list) else []}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stock/{symbol}/fundamentals")
async def get_stock_fundamentals(symbol: str):
    """取得基本面資料（營收、EPS 等）"""
    try:
        from services.stock_service import stock_service
        data = stock_service.get_stock_fundamentals(symbol)
        return data or {}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stock/{symbol}/chips")
async def get_stock_chips(symbol: str):
    """取得籌碼面資料（三大法人、融資融券）"""
    try:
        from services.stock_service import stock_service
        data = stock_service.get_stock_chips(symbol)
        return data or {}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stock/search/{query}")
async def search_stocks(query: str, limit: int = Query(10, le=50)):
    """搜尋股票（代號或名稱）"""
    try:
        from services.stock_service import stock_service
        results = stock_service.search_symbols(query, limit=limit)
        return {"results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
