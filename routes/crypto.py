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
    """加密貨幣 AI 深度分析（專屬 prompt，不走股票 pipeline）"""
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
        import asyncio

        # 取得 K 線數據
        klines = await pionex_adapter.get_klines(symbol, req.interval, req.limit)
        if not klines:
            raise HTTPException(status_code=404, detail=f"無法取得 {symbol} 的 K 線數據")

        # 取得即時行情
        ticker = await pionex_adapter.get_ticker(symbol)

        # 建立技術指標
        tech_snapshot = _build_crypto_technical_snapshot(klines)

        # 組裝幣種資訊
        base_symbol = symbol.split("_")[0] if "_" in symbol else symbol
        ticker_info = ""
        if ticker:
            price = float(ticker.get("close", 0))
            open_p = float(ticker.get("open", 0))
            high = float(ticker.get("high", 0))
            low = float(ticker.get("low", 0))
            vol = float(ticker.get("volume", 0))
            change_pct = ((price - open_p) / open_p * 100) if open_p > 0 else 0
            ticker_info = (
                f"現價: {price:.6g} USDT | 24h漲跌: {change_pct:+.2f}% | "
                f"24h高: {high:.6g} | 24h低: {low:.6g} | 成交量: {vol:.2f}"
            )

        # 加密貨幣專屬 prompt（輕量、快速、不需要股票相關指標）
        crypto_prompt = (
            f"你是加密貨幣分析師。請用繁體中文分析 {base_symbol} ({symbol})。\n\n"
            f"即時行情: {ticker_info}\n"
            f"技術指標: {tech_snapshot}\n"
            f"K線數量: {len(klines)} 根（{req.interval} 週期）\n\n"
            "請依以下架構分析（禁止使用 markdown 裝飾符號如 ** ## ``` 等）：\n\n"
            "1. 市場概況\n"
            f"   分析 {base_symbol} 當前市場表現、價格走勢、成交量變化\n\n"
            "2. 技術面分析\n"
            "   根據提供的 RSI、SMA、成交量等指標判斷趨勢方向與強度\n\n"
            "3. 支撐與壓力\n"
            "   根據近期高低點標示關鍵價位區間\n\n"
            "4. 交易策略建議\n"
            "   給出短期（1-3天）和中期（1-2週）的操作建議，包含進場區間、停損和目標價\n\n"
            "5. 風險提示\n"
            "   列出主要風險因素\n\n"
            "總長度至少 300 字。語氣專業冷靜，像經驗豐富的交易員。"
        )

        # 直接呼叫 Gemini（不走股票分析 pipeline）
        analysis_text = await asyncio.to_thread(
            _call_gemini_crypto, crypto_prompt
        )

        if analysis_text and len(analysis_text) > 50:
            rate_limiter.record_request(user_id)

        return {
            "success": bool(analysis_text and len(analysis_text) > 50),
            "symbol": symbol,
            "analysis": analysis_text or "分析暫時無法產出，請稍後再試。",
            "tech_snapshot": tech_snapshot,
            "kline_count": len(klines),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("[Crypto] AI analysis error")
        raise HTTPException(status_code=500, detail=str(e))


def _call_gemini_crypto(prompt: str) -> str:
    """直接呼叫 Gemini 生成加密貨幣分析（輕量、快速）"""
    try:
        from services.gemini_service import gemini_service
        from google import genai
        from google.genai import types

        api_key = gemini_service._get_api_key()
        if not api_key:
            return ""

        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.3,
                max_output_tokens=1500,
            ),
        )

        text = (getattr(response, "text", "") or "").strip()
        # 清理 markdown 符號
        for token in ("**", "***", "```", "__", "~~", "##", "###", "> "):
            text = text.replace(token, "")
        return text
    except Exception as e:
        logger.warning("[Crypto] Gemini 呼叫失敗: %s", e)
        return ""


