"""加密貨幣（beta）API routes — 使用 Pionex 公開行情 API"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter()

CRYPTO_SYSTEM_PROMPT = """你是 DiscoverLatest 專屬加密貨幣 AI 深度分析引擎
今日日期 {today}
身份 10 年加密貨幣交易經驗 風格冷靜 執行導向 數據驅動
語言 全文繁體中文 禁止英文句子 技術縮寫 RSI MACD BTC ETH 等除外
格式 純文字列點 禁止任何 markdown 符號 --- ** *** ## ### ``` __ ~~ >

幻覺防護規則
• 若無充分數據支撐 寫「資料不足 無法判斷」 禁止編造數據或事件
• 所有價位 數值 日期必須來自提供的即時行情或技術指標 不可憑空捏造
• 每條建議必須附帶理由（WHY）

重要 在正文分析之前 先輸出一段 JSON 摘要 用 <<<JSON_START>>> 和 <<<JSON_END>>> 包裹
格式如下
<<<JSON_START>>>
{"verdict":"偏多或偏空或中性","confidence":0到100整數,"scores":{"technical":0到100,"on_chain":0到100,"sentiment":0到100,"macro":0到100},"entry":{"short":"xxx-xxx","mid":"xxx-xxx","long":"xxx-xxx"},"stop_loss":{"short":"xxx","mid":"xxx","long":"xxx"},"target":{"short":"xxx","mid":"xxx","long":"xxx"},"risk_reward":{"short":"x.x:1","mid":"x.x:1","long":"x.x:1"},"key_levels":{"support":["xxx","xxx"],"resistance":["xxx","xxx"]},"one_liner":"一句話總結最重要的操作建議"}
<<<JSON_END>>>
JSON 中所有價位必須是具體數字 不可使用文字描述
然後接著輸出正文分析

固定輸出結構 不可更改標題文字與順序

我是 DiscoverLatest 專屬 AI 🚀
1.市場快報 📰
• 當前價格 24h漲跌幅 成交量變化 市值排名
• 3-5 個最新驅動因子 每個註明偏多或偏空 並說明 WHY

2.技術面分析 📈
• RSI14 數值與超買超賣判讀
• MACD 數值 金叉死叉 柱狀體方向
• 布林通道(20,2) 上軌 中軌 下軌與價格位置
• SMA20 SMA50 排列與支撐壓力
• 量價背離分析
• 多空結構結論 附具體理由

3.進出場計劃 🎯
• 短期 1-3天 進場區 停損 目標價 R:R
  WHY 為何選這個進場價位 停損邏輯 目標依據
• 中期 1-2週 進場區 停損 目標價 R:R
  WHY 為何選這個進場價位 停損邏輯 目標依據
• 長期 1-3月 進場區 停損 目標價 R:R
  WHY 為何選這個進場價位 停損邏輯 目標依據

4.風險提示 ⚠️
• 監管風險 各國政策變動
• 安全風險 交易所駭客 智能合約漏洞
• 槓桿清算風險 資金費率 爆倉價位
• 穩定幣風險 脫錨事件
• 失效條件與停損執行原則

5.結論 ✅
• 當前最佳操作 做多 做空 或觀望 並說明理由
• 2-3 句可執行總結 明確方向與優先動作

6.情境交易地圖 偏多 偏空 震盪 🗺️
• 偏多 觸發條件 關鍵價位 應對策略 理由
• 偏空 觸發條件 關鍵價位 應對策略 理由
• 震盪 觸發條件 關鍵價位 應對策略 理由

7.鏈上與宏觀分析 🌍
• 交易所淨流入流出趨勢（若有數據）
• BTC 主導率對山寨幣的影響
• 恐慌貪婪指數參考
• 聯準會利率 美元指數對加密市場的傳導機制 及 WHY
"""


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
    allowed, reason = rate_limiter.acquire_request(user_id)
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

        # 加密貨幣專屬 prompt — 使用完整 7 章節 CRYPTO_SYSTEM_PROMPT
        from datetime import datetime as _dt_crypto
        today_str = _dt_crypto.now().strftime("%Y-%m-%d")
        crypto_prompt = (
            f"{CRYPTO_SYSTEM_PROMPT.replace('{today}', today_str)}\n\n"
            f"標的 {base_symbol} ({symbol})\n"
            f"即時行情: {ticker_info}\n"
            f"技術指標: {tech_snapshot}\n"
            f"K線數量: {len(klines)} 根（{req.interval} 週期）\n"
        )

        # 直接呼叫 Gemini（不走股票分析 pipeline）
        analysis_text = await asyncio.to_thread(
            _call_gemini_crypto, crypto_prompt
        )

        # 提取 JSON 摘要
        summary_data = None
        if analysis_text:
            try:
                from services.gemini_service import GeminiService
                summary_data, analysis_text = GeminiService._extract_summary_json(analysis_text)
            except Exception:
                pass

        return {
            "success": bool(analysis_text and len(analysis_text) > 50),
            "symbol": symbol,
            "analysis": analysis_text or "分析暫時無法產出，請稍後再試。",
            "summary": summary_data or {},
            "tech_snapshot": tech_snapshot,
            "kline_count": len(klines),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("[Crypto] AI analysis error")
        raise HTTPException(status_code=500, detail=str(e))


def _call_gemini_crypto(prompt: str) -> str:
    """直接呼叫 Gemini 生成加密貨幣分析（輕量、快速、含重試）"""
    import time as _time
    import re as _re

    try:
        from services.gemini_service import gemini_service, _load_key_pool, _mask_key
        from config.models import MODEL_FINAL
        from google import genai
        from google.genai import types
    except Exception:
        return ""

    pool_size = len(_load_key_pool())
    max_retries = max(pool_size, 3)  # 至少嘗試所有 key

    for attempt in range(max_retries):
        api_key = gemini_service._get_api_key()
        if not api_key:
            return ""

        masked = _mask_key(api_key)
        try:
            client = genai.Client(api_key=api_key)
            response = client.models.generate_content(
                model=MODEL_FINAL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.3,
                    max_output_tokens=3200,
                ),
            )

            text = (getattr(response, "text", "") or "").strip()
            for token in ("**", "***", "```", "__", "~~", "##", "###", "> "):
                text = text.replace(token, "")
            if text:
                logger.info("[Crypto] Gemini 成功 (key=%s, attempt=%d)", masked, attempt + 1)
            return text
        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                # 嘗試從錯誤訊息解析建議等待時間
                wait_match = _re.search(r"retry in ([\d.]+)s", err_str)
                wait = float(wait_match.group(1)) if wait_match else min(2 ** attempt, 4)
                wait = min(wait, 5)  # 最多等 5 秒
                logger.info(
                    "[Crypto] key=%s 429 quota exhausted (%d/%d)，等 %.1fs",
                    masked, attempt + 1, max_retries, wait,
                )
                _time.sleep(wait)
                continue
            logger.warning("[Crypto] Gemini 呼叫失敗 (key=%s): %s", masked, e)
            return ""

    logger.warning("[Crypto] 所有 %d 把 key 都 quota exhausted，無法生成分析", pool_size)
    return ""


