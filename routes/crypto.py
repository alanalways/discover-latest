"""加密貨幣（beta）API routes — 使用 Pionex 公開行情 API"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/crypto/tickers")
async def get_crypto_tickers():
    """
    取得加密貨幣即時行情
    回傳兩組：24h 漲幅前 10 名 + 主流幣前 10 名
    """
    try:
        from adapters.pionex_adapter import pionex_adapter

        gainers = await pionex_adapter.get_top_gainers(limit=10)
        majors = await pionex_adapter.get_top_cryptos()
        return {
            "success": True,
            "gainers": gainers,
            "majors": majors,
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


# ────────────────────── AI 深度分析 ──────────────────────

class CryptoAnalysisRequest(BaseModel):
    symbol: str
    interval: str = "1D"
    limit: int = 100


def _build_crypto_technical_snapshot(klines: list) -> str:
    """從 K 線數據建立技術指標摘要"""
    if not klines or len(klines) < 20:
        return ""

    closes = [float(k.get("close", 0)) for k in klines if float(k.get("close", 0)) > 0]
    highs = [float(k.get("high", 0)) for k in klines if float(k.get("high", 0)) > 0]
    lows = [float(k.get("low", 0)) for k in klines if float(k.get("low", 0)) > 0]
    volumes = [float(k.get("volume", 0)) for k in klines]

    if len(closes) < 14:
        return f"Price: {closes[-1]:.6g}" if closes else ""

    last = closes[-1]
    lines = [f"Price: {last:.6g}"]

    # SMA
    if len(closes) >= 20:
        sma20 = sum(closes[-20:]) / 20
        lines.append(f"SMA20: {sma20:.6g}")
    if len(closes) >= 50:
        sma50 = sum(closes[-50:]) / 50
        lines.append(f"SMA50: {sma50:.6g}")

    # RSI-14
    if len(closes) > 14:
        gains, losses = [], []
        for i in range(1, len(closes)):
            d = closes[i] - closes[i - 1]
            gains.append(max(d, 0))
            losses.append(max(-d, 0))
        avg_g = sum(gains[:14]) / 14
        avg_l = sum(losses[:14]) / 14
        for i in range(14, len(gains)):
            avg_g = (avg_g * 13 + gains[i]) / 14
            avg_l = (avg_l * 13 + losses[i]) / 14
        rsi = 100 - (100 / (1 + avg_g / avg_l)) if avg_l > 0 else 100
        lines.append(f"RSI14: {rsi:.2f}")

    # 24h Volume
    if volumes:
        lines.append(f"Volume(latest): {volumes[-1]:.2f}")
        avg_vol = sum(volumes[-20:]) / min(20, len(volumes))
        lines.append(f"AvgVolume(20): {avg_vol:.2f}")

    # High/Low range
    if highs and lows:
        lines.append(f"Range High/Low: {max(highs[-30:]):.6g}/{min(lows[-30:]):.6g}")

    return " | ".join(lines)


@router.post("/crypto/ai-analysis")
async def crypto_ai_analysis(req: CryptoAnalysisRequest, request: Request):
    """加密貨幣 AI 深度分析"""
    symbol = req.symbol.upper().replace("-", "_")
    if "_" not in symbol:
        symbol = f"{symbol}_USDT"

    # 驗證登入
    auth_header = request.headers.get("Authorization", "")
    user_id = None
    if auth_header.startswith("Bearer "):
        token = auth_header.split(" ", 1)[1]
        try:
            from services.auth_service import auth_service
            user = auth_service.verify_session(token)
            user_id = user.get("id") if user else None
        except Exception:
            pass

    if not user_id:
        raise HTTPException(status_code=401, detail="請先登入後再使用 AI 分析功能")

    # 檢查額度
    from services.rate_limiter import rate_limiter
    tier = rate_limiter.check_and_downgrade(user_id)
    allowed, reason = rate_limiter.can_make_request(user_id)
    if not allowed:
        raise HTTPException(status_code=429, detail=reason or "今日 AI 分析次數已達上限")

    try:
        from adapters.pionex_adapter import pionex_adapter
        from services.gemini_service import gemini_service
        import asyncio

        # 取得 K 線數據
        klines = await pionex_adapter.get_klines(symbol, req.interval, req.limit)
        if not klines:
            raise HTTPException(status_code=404, detail=f"無法取得 {symbol} 的 K 線數據")

        # 取得即時行情
        ticker = await pionex_adapter.get_ticker(symbol)

        # 建立技術指標
        tech_snapshot = _build_crypto_technical_snapshot(klines)

        # 組裝給 AI 的資料
        base_symbol = symbol.split("_")[0] if "_" in symbol else symbol
        crypto_info = {
            "symbol": symbol,
            "name": base_symbol,
            "asset_type": "cryptocurrency",
            "exchange": "Pionex (Multi-exchange aggregator)",
        }
        if ticker:
            crypto_info.update({
                "price": float(ticker.get("close", 0)),
                "open": float(ticker.get("open", 0)),
                "high_24h": float(ticker.get("high", 0)),
                "low_24h": float(ticker.get("low", 0)),
                "volume_24h": float(ticker.get("volume", 0)),
            })

        # 呼叫 Gemini AI 分析
        result = await asyncio.to_thread(
            gemini_service.generate_analysis,
            symbol=symbol,
            stock_info=crypto_info,
            smc_summary="Crypto asset - SMC N/A",
            prediction_summary=tech_snapshot,
            macro_data=None,
            user_question="",
            tier=tier,
            investor_profile=None,
            progress_callback=None,
        )

        analysis_text = ""
        success = False
        if isinstance(result, dict):
            analysis_text = str(result.get("analysis", "")).strip()
            success = bool(result.get("success"))

        if analysis_text and len(analysis_text) > 50:
            rate_limiter.record_request(user_id)

        return {
            "success": success or bool(analysis_text),
            "symbol": symbol,
            "analysis": analysis_text,
            "tech_snapshot": tech_snapshot,
            "kline_count": len(klines),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("[Crypto] AI analysis error")
        raise HTTPException(status_code=500, detail=str(e))

