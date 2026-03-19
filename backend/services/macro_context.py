"""
backend/services/macro_context.py
宏觀市場指標服務 — 從 _legacy/services/macro_context_service.py 移植

提供 VIX, S&P500, DXY, 美債殖利率, 油價, 金價等宏觀指標，
並生成可注入 Gemini prompt 的格式化字串。
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_CACHE_TTL = 900  # 15 分鐘快取
_cache: Optional[Dict[str, Any]] = None
_cache_ts: float = 0.0
_lock = threading.Lock()

# 追蹤的宏觀指標符號
_MACRO_SYMBOLS = {
    "vix": "^VIX",
    "sp500": "^GSPC",
    "nasdaq": "^IXIC",
    "dji": "^DJI",
    "dxy": "DX-Y.NYB",
    "us10y": "^TNX",
    "us2y": "^IRX",
    "oil": "CL=F",
    "gold": "GC=F",
}


def _fetch_yf_quote(symbol: str) -> Optional[Dict[str, Any]]:
    """從 Yahoo Finance 取得單一報價。"""
    try:
        import yfinance as yf

        ticker = yf.Ticker(symbol)
        info = ticker.fast_info
        price = getattr(info, "last_price", None) or getattr(info, "previous_close", None)
        if price and price > 0:
            prev = getattr(info, "previous_close", price)
            change_pct = ((price - prev) / prev * 100) if prev > 0 else 0
            return {
                "price": round(float(price), 2),
                "change_pct": round(float(change_pct), 2),
            }
    except Exception as e:
        logger.debug("[MacroContext] 取得 %s 失敗: %s", symbol, e)
    return None


def get_macro_context(force_refresh: bool = False) -> Dict[str, Any]:
    """
    取得當前宏觀市場環境。快取 15 分鐘。

    Returns:
        {
            "indicators": {name: {"price": float, "change_pct": float}, ...},
            "regime": "high_fear" | "cautious" | "neutral" | "complacent",
            "yield_spread": float | None,
            "timestamp": float,
        }
    """
    global _cache, _cache_ts

    with _lock:
        now = time.time()
        if not force_refresh and _cache and (now - _cache_ts) < _CACHE_TTL:
            return _cache

    indicators: Dict[str, Any] = {}
    for name, sym in _MACRO_SYMBOLS.items():
        data = _fetch_yf_quote(sym)
        if data:
            indicators[name] = data

    # 市場恐慌/貪婪情境
    regime = "neutral"
    vix_price = indicators.get("vix", {}).get("price", 0)
    if vix_price > 30:
        regime = "high_fear"
    elif vix_price > 20:
        regime = "cautious"
    elif vix_price < 15:
        regime = "complacent"

    # 殖利率曲線（10Y - 2Y）
    us10y = indicators.get("us10y", {}).get("price", 0)
    us2y = indicators.get("us2y", {}).get("price", 0)
    yield_spread = round(us10y - us2y, 2) if us10y and us2y else None

    result = {
        "indicators": indicators,
        "regime": regime,
        "yield_spread": yield_spread,
        "timestamp": time.time(),
    }

    with _lock:
        _cache = result
        _cache_ts = time.time()

    return result


def format_macro_for_prompt() -> str:
    """格式化宏觀指標為 AI prompt 可注入的文字。"""
    ctx = get_macro_context()
    indicators = ctx.get("indicators", {})
    if not indicators:
        return ""

    lines = ["[Macro Context]"]

    label_map = {
        "vix": "VIX",
        "sp500": "S&P500",
        "nasdaq": "NASDAQ",
        "dji": "Dow Jones",
        "dxy": "USD Index",
        "us10y": "US 10Y Yield",
        "us2y": "US 2Y Yield",
        "oil": "Crude Oil",
        "gold": "Gold",
    }

    for key, label in label_map.items():
        data = indicators.get(key)
        if data:
            lines.append(f"{label}: {data['price']} ({data['change_pct']:+.2f}%)")

    regime = ctx.get("regime", "neutral")
    lines.append(f"Market Regime: {regime}")

    spread = ctx.get("yield_spread")
    if spread is not None:
        lines.append(f"Yield Curve (10Y-2Y): {spread:.2f}%")

    return " | ".join(lines)
