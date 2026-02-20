"""加密貨幣（beta）API routes — 使用 Pionex 公開行情 API"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/crypto/tickers")
async def get_crypto_tickers():
    """
    取得主流加密貨幣即時行情
    包含 BTC, ETH, SOL, BNB, XRP, DOGE, ADA, AVAX, DOT, MATIC
    """
    try:
        from adapters.pionex_adapter import pionex_adapter

        tickers = await pionex_adapter.get_top_cryptos()
        return {
            "success": True,
            "tickers": tickers,
            "count": len(tickers),
            "source": "pionex",
        }
    except Exception as e:
        logger.exception("[Crypto] get_crypto_tickers error")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/crypto/ticker/{symbol}")
async def get_crypto_ticker(symbol: str):
    """取得單一加密貨幣即時行情"""
    symbol = symbol.upper().replace("-", "_")
    if "_" not in symbol:
        symbol = f"{symbol}_USDT"

    try:
        from adapters.pionex_adapter import pionex_adapter

        ticker = await pionex_adapter.get_ticker(symbol)
        if not ticker:
            raise HTTPException(status_code=404, detail=f"找不到 {symbol} 行情")

        close = float(ticker.get("close", 0))
        open_price = float(ticker.get("open", 0))
        change = close - open_price
        change_pct = (change / open_price * 100) if open_price > 0 else 0

        return {
            "success": True,
            "symbol": symbol,
            "price": close,
            "open": open_price,
            "high": float(ticker.get("high", 0)),
            "low": float(ticker.get("low", 0)),
            "change": round(change, 4),
            "change_pct": round(change_pct, 2),
            "volume": float(ticker.get("volume", 0)),
            "amount": float(ticker.get("amount", 0)),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("[Crypto] get_crypto_ticker error")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/crypto/klines")
async def get_crypto_klines(
    symbol: str = Query(..., description="交易對，如 BTC_USDT"),
    interval: str = Query("1D", description="K 線間隔: 1M,5M,15M,30M,60M,4H,8H,12H,1D"),
    limit: int = Query(100, ge=1, le=500, description="筆數，最大 500"),
):
    """取得加密貨幣 K 線數據"""
    symbol = symbol.upper().replace("-", "_")
    if "_" not in symbol:
        symbol = f"{symbol}_USDT"

    valid_intervals = {"1M", "5M", "15M", "30M", "60M", "4H", "8H", "12H", "1D"}
    if interval not in valid_intervals:
        raise HTTPException(
            status_code=400,
            detail=f"interval 必須為 {', '.join(sorted(valid_intervals))} 之一",
        )

    try:
        from adapters.pionex_adapter import pionex_adapter

        klines = await pionex_adapter.get_klines(symbol, interval, limit)
        return {
            "success": True,
            "symbol": symbol,
            "interval": interval,
            "klines": klines,
            "count": len(klines),
        }
    except Exception as e:
        logger.exception("[Crypto] get_crypto_klines error")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/crypto/symbols")
async def get_crypto_symbols():
    """取得所有可交易的加密貨幣交易對"""
    try:
        from adapters.pionex_adapter import pionex_adapter

        symbols = await pionex_adapter.get_symbols()
        # 只回傳 SPOT 類型
        spot_symbols = [s for s in symbols if s.get("type") == "SPOT"]
        return {
            "success": True,
            "symbols": spot_symbols,
            "count": len(spot_symbols),
        }
    except Exception as e:
        logger.exception("[Crypto] get_crypto_symbols error")
        raise HTTPException(status_code=500, detail=str(e))
