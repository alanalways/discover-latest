"""
backend/services/market_overview.py
市場概覽服務 — 從 _legacy/pages/market_overview.py 移植核心邏輯

提供大盤指數、ETF、Top 20 排行、台美股市場時間狀態。
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

# ── 追蹤標的 ──────────────────────────────────────

_INDEX_TICKERS = {
    "tw": {
        "^TWII": "加權指數",
        "^SOX": "費城半導體",
    },
    "us": {
        "^GSPC": "S&P 500",
        "^IXIC": "NASDAQ",
        "^DJI": "Dow Jones",
    },
}

_ETF_TICKERS = {
    "tw": ["0050", "0056", "00878", "00919"],
    "us": ["VOO", "QQQ", "SPY"],
}

_TW_TOP_SYMBOLS = [
    "2330", "2317", "2454", "2308", "2881", "2882", "2891", "2303",
    "3711", "2412", "1301", "2886", "3008", "2002", "1303",
    "2880", "3037", "6505", "5880", "2884",
]

_US_TOP_SYMBOLS = [
    "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA",
    "BRK-B", "LLY", "AVGO", "JPM", "V", "UNH", "XOM",
    "MA", "PG", "COST", "HD", "JNJ", "NFLX",
]

# ── 快取 ──────────────────────────────────────────

_indices_cache: Dict[str, Any] = {"ts": 0.0, "data": {}}
_top20_cache: Dict[str, Any] = {"ts": 0.0, "tw": [], "us": []}
_INDICES_TTL = 300   # 5 分鐘
_TOP20_TTL = 180     # 3 分鐘
_lock = threading.Lock()


# ── 市場時間 ──────────────────────────────────────

def _is_tw_market_open() -> bool:
    """台股是否開盤中（09:00-13:30 台北時間，週一到週五）。"""
    tz = ZoneInfo("Asia/Taipei")
    now = datetime.now(tz)
    if now.weekday() >= 5:
        return False
    t = now.time()
    from datetime import time as dt_time
    return dt_time(9, 0) <= t <= dt_time(13, 30)


def _is_us_market_open() -> bool:
    """美股是否開盤中（09:30-16:00 紐約時間，週一到週五）。"""
    tz = ZoneInfo("America/New_York")
    now = datetime.now(tz)
    if now.weekday() >= 5:
        return False
    t = now.time()
    from datetime import time as dt_time
    return dt_time(9, 30) <= t <= dt_time(16, 0)


def get_market_hours_snapshot() -> Dict[str, Any]:
    """取得台美股當前開盤狀態。"""
    tz_tw = ZoneInfo("Asia/Taipei")
    tz_us = ZoneInfo("America/New_York")
    now_tw = datetime.now(tz_tw)
    now_us = datetime.now(tz_us)

    return {
        "tw": {
            "is_open": _is_tw_market_open(),
            "local_time": now_tw.strftime("%H:%M"),
            "session": "09:00-13:30 TST",
        },
        "us": {
            "is_open": _is_us_market_open(),
            "local_time": now_us.strftime("%H:%M"),
            "session": "09:30-16:00 EST",
        },
    }


# ── 指數資料 ──────────────────────────────────────

def _fetch_yf_quote(symbol: str) -> Optional[Dict[str, Any]]:
    """透過 yfinance 取得即時報價。"""
    try:
        import yfinance as yf

        ticker = yf.Ticker(symbol)
        info = ticker.fast_info
        price = getattr(info, "last_price", None) or getattr(info, "previous_close", None)
        if not price or price <= 0:
            return None

        prev = getattr(info, "previous_close", price)
        change_pct = ((price - prev) / prev * 100) if prev > 0 else 0

        return {
            "symbol": symbol,
            "price": round(float(price), 2),
            "change_pct": round(float(change_pct), 2),
            "prev_close": round(float(prev), 2) if prev else None,
        }
    except Exception as e:
        logger.debug("[MarketOverview] fetch %s 失敗: %s", symbol, e)
        return None


def get_indices() -> Dict[str, Any]:
    """取得主要指數報價（含快取）。"""
    now = time.time()
    with _lock:
        if _indices_cache["data"] and (now - _indices_cache["ts"]) < _INDICES_TTL:
            return _indices_cache["data"]

    result: Dict[str, List] = {"tw": [], "us": []}

    for market, tickers in _INDEX_TICKERS.items():
        for sym, name in tickers.items():
            quote = _fetch_yf_quote(sym)
            if quote:
                quote["name"] = name
                result[market].append(quote)

    # ETF
    for market, etf_list in _ETF_TICKERS.items():
        for sym in etf_list:
            ticker_sym = f"{sym}.TW" if market == "tw" else sym
            quote = _fetch_yf_quote(ticker_sym)
            if quote:
                quote["name"] = sym
                quote["type"] = "etf"
                result[market].append(quote)

    with _lock:
        _indices_cache["ts"] = time.time()
        _indices_cache["data"] = result

    return result


def get_top20(market: str = "tw") -> List[Dict[str, Any]]:
    """取得 Top 20 個股報價（按漲幅排序）。"""
    now = time.time()
    cache_key = market.lower()
    with _lock:
        cached = _top20_cache.get(cache_key, [])
        if cached and (now - _top20_cache["ts"]) < _TOP20_TTL:
            return cached

    symbols = _TW_TOP_SYMBOLS if cache_key == "tw" else _US_TOP_SYMBOLS
    rows: List[Dict[str, Any]] = []

    for sym in symbols:
        ticker_sym = f"{sym}.TW" if cache_key == "tw" else sym
        quote = _fetch_yf_quote(ticker_sym)
        if quote:
            quote["symbol"] = sym
            rows.append(quote)

    rows.sort(key=lambda x: x.get("change_pct", 0), reverse=True)

    with _lock:
        _top20_cache["ts"] = time.time()
        _top20_cache[cache_key] = rows

    return rows


def get_full_overview() -> Dict[str, Any]:
    """取得完整市場概覽（指數 + Top 20 + 市場狀態）。"""
    return {
        "market_hours": get_market_hours_snapshot(),
        "indices": get_indices(),
        "top20_tw": get_top20("tw"),
        "top20_us": get_top20("us"),
    }
