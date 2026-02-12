"""
Stock Routes — 股票核心資料、歷史、搜尋與籌碼
"""
from fastapi import APIRouter, HTTPException, Query
from typing import List, Dict, Optional
from services.stock_service import stock_service
import asyncio

router = APIRouter()

@router.get("/stock/{symbol}")
async def get_stock_overview(
    symbol: str,
    period: str = Query("1y", description="1mo, 3mo, 6mo, 1y, 2y, 3y, 5y, max")
):
    """取得股票概要 (Info + Latest History + Valuation + Market Cap)"""
    try:
        data = await stock_service.get_stock_data(symbol, period=period)
        if not data:
            raise HTTPException(status_code=404, detail=f"找不到股票: {symbol}")
        return data
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/stock/{symbol}/history")
async def get_stock_history(
    symbol: str, 
    period: str = Query("1y", description="1mo, 3mo, 6mo, 1y, 3y, 5y, max")
):
    """取得歷史 K 線 (Lightweight Charts 格式)"""
    try:
        history = await stock_service.get_stock_history(symbol, period=period)
        return history
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/stock/search/{query}")
async def search_stocks(query: str, limit: int = 10):
    """搜尋股票 (支援台股與美股)"""
    try:
        results = await stock_service.search_symbols(query, limit=limit)
        return results
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/stock/{symbol}/fundamentals")
async def get_stock_fundamentals(symbol: str):
    """取得基本面資料 (財務報表)"""
    try:
        data = await stock_service.get_stock_fundamentals(symbol)
        return data
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/stock/{symbol}/chips")
async def get_stock_chips(symbol: str):
    """取得籌碼面資料 (法人買賣)"""
    try:
        data = await stock_service.get_stock_chips(symbol)
        return data
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
