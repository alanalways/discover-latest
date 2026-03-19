"""
backend/data/sources/yahoo.py
Yahoo Finance 資料來源（Sonnet 撰寫）

注意：鎖定 yfinance>=0.2.0,<0.2.59，新版有 bug（CLAUDE.md 禁止事項第 9 條）

提供：
- get_price_data(symbol, market, period) → dict
- get_current_price(symbol, market) → float | None
- get_info(symbol, market) → dict
"""

import logging
from datetime import date, timedelta
from typing import Optional

logger = logging.getLogger(__name__)


def _build_ticker(symbol: str, market: str) -> str:
    """依市場加上 Yahoo Finance 後綴。"""
    if market == "TW":
        return f"{symbol}.TW"
    elif market == "TWO":
        return f"{symbol}.TWO"
    elif market == "US":
        return symbol
    return symbol


def get_price_data(
    symbol:  str,
    market:  str,
    period:  str = "6mo",   # yfinance period string
    interval: str = "1d",
) -> dict:
    """
    取得歷史 OHLCV 資料。

    Args:
        symbol:   股票代號
        market:   TW / TWO / US
        period:   yfinance 期間字串（1mo, 3mo, 6mo, 1y, 2y, 5y）
        interval: 資料頻率（1d, 1wk, 1mo）

    Returns:
        dict: {
            symbol, market, period,
            dates: [str], opens: [float], highs: [float],
            lows: [float], closes: [float], volumes: [int],
            error: str | None
        }
    """
    ticker_sym = _build_ticker(symbol, market)
    result_base = {
        "symbol": symbol, "market": market, "period": period,
        "dates": [], "opens": [], "highs": [],
        "lows": [], "closes": [], "volumes": [],
        "error": None,
    }

    try:
        import yfinance as yf

        ticker = yf.Ticker(ticker_sym)
        hist   = ticker.history(period=period, interval=interval, auto_adjust=True)

        if hist.empty:
            result_base["error"] = f"No data for {ticker_sym}"
            return result_base

        result_base.update(
            {
                "dates":   [str(d.date()) if hasattr(d, "date") else str(d) for d in hist.index],
                "opens":   [round(float(v), 4) for v in hist["Open"]],
                "highs":   [round(float(v), 4) for v in hist["High"]],
                "lows":    [round(float(v), 4) for v in hist["Low"]],
                "closes":  [round(float(v), 4) for v in hist["Close"]],
                "volumes": [int(v) for v in hist["Volume"]],
            }
        )
        return result_base

    except Exception as e:
        logger.error(f"[Yahoo] get_price_data {ticker_sym} 失敗: {e}")
        result_base["error"] = str(e)
        return result_base


def get_current_price(symbol: str, market: str) -> Optional[float]:
    """
    取得即時（或最近收盤）價格。

    Returns:
        float 價格，或 None（失敗時）
    """
    ticker_sym = _build_ticker(symbol, market)
    try:
        import yfinance as yf

        ticker = yf.Ticker(ticker_sym)
        info   = ticker.fast_info

        # fast_info 提供 last_price（比 info dict 快很多）
        price = getattr(info, "last_price", None)
        if price is not None:
            return round(float(price), 4)

        # fallback：取最近 2 日歷史
        hist = ticker.history(period="2d", auto_adjust=True)
        if not hist.empty:
            return round(float(hist["Close"].iloc[-1]), 4)

        return None

    except Exception as e:
        logger.error(f"[Yahoo] get_current_price {ticker_sym} 失敗: {e}")
        return None


def get_info(symbol: str, market: str) -> dict:
    """
    取得股票基本資訊（公司名稱、市值、PE、PB 等）。

    Returns:
        dict（可能部分欄位為 None）
    """
    ticker_sym = _build_ticker(symbol, market)
    defaults = {
        "symbol": symbol, "market": market, "name": symbol,
        "sector": None, "industry": None,
        "market_cap": None, "pe_ratio": None, "pb_ratio": None,
        "dividend_yield": None, "currency": None,
        "error": None,
    }

    try:
        import yfinance as yf

        info = yf.Ticker(ticker_sym).info

        defaults.update(
            {
                "name":           info.get("longName") or info.get("shortName", symbol),
                "sector":         info.get("sector"),
                "industry":       info.get("industry"),
                "market_cap":     info.get("marketCap"),
                "pe_ratio":       info.get("trailingPE"),
                "pb_ratio":       info.get("priceToBook"),
                "dividend_yield": info.get("dividendYield"),
                "currency":       info.get("currency"),
            }
        )
        return defaults

    except Exception as e:
        logger.error(f"[Yahoo] get_info {ticker_sym} 失敗: {e}")
        defaults["error"] = str(e)
        return defaults


def get_close_on_date(symbol: str, market: str, date_str: str) -> Optional[float]:
    """
    取得指定日期的收盤價（供 backtester 使用）。

    Args:
        date_str: "YYYY-MM-DD"

    Returns:
        float 收盤價，或 None
    """
    ticker_sym = _build_ticker(symbol, market)
    try:
        import yfinance as yf

        target    = date.fromisoformat(date_str)
        end_date  = (target + timedelta(days=5)).isoformat()
        start_date = target.isoformat()

        hist = yf.Ticker(ticker_sym).history(
            start=start_date, end=end_date, auto_adjust=True
        )
        if hist.empty:
            return None

        hist.index = [i.date() if hasattr(i, "date") else i for i in hist.index]
        for delta in range(5):
            d = target + timedelta(days=delta)
            if d in hist.index:
                return round(float(hist.loc[d, "Close"]), 4)

        return None

    except Exception as e:
        logger.debug(f"[Yahoo] get_close_on_date {ticker_sym} {date_str} 失敗: {e}")
        return None
