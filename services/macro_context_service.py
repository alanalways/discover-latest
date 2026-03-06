"""
Macro Context Service
Fetches macro indicators (VIX, USD Index, Treasury Yields, Oil, Gold, S&P500)
to enrich AI analysis with broader market context.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Cache macro data for 15 minutes to avoid excessive API calls
_CACHE_TTL = 900
_cache: Optional[Dict[str, Any]] = None
_cache_ts: float = 0.0
_lock = threading.Lock()


def _fetch_yf_quote(symbol: str) -> Optional[Dict[str, Any]]:
    """Fetch a single quote from Yahoo Finance."""
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
        logger.debug("[MacroContext] Failed to fetch %s: %s", symbol, e)
    return None


def get_macro_context(force_refresh: bool = False) -> Dict[str, Any]:
    """
    Return current macro market context.
    Cached for 15 minutes.
    """
    global _cache, _cache_ts

    with _lock:
        now = time.time()
        if not force_refresh and _cache and (now - _cache_ts) < _CACHE_TTL:
            return _cache

    # Fetch outside lock to avoid blocking
    indicators: Dict[str, Any] = {}

    symbols = {
        "vix": "^VIX",
        "sp500": "^GSPC",
        "dxy": "DX-Y.NYB",
        "us10y": "^TNX",
        "us2y": "^IRX",
        "oil": "CL=F",
        "gold": "GC=F",
    }

    for name, sym in symbols.items():
        data = _fetch_yf_quote(sym)
        if data:
            indicators[name] = data

    # Derive market regime
    regime = "neutral"
    vix_price = indicators.get("vix", {}).get("price", 0)
    if vix_price > 30:
        regime = "high_fear"
    elif vix_price > 20:
        regime = "cautious"
    elif vix_price < 15:
        regime = "complacent"

    # Yield curve (10Y - 2Y proxy)
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
    """Format macro context as a text string for AI prompt injection."""
    ctx = get_macro_context()
    indicators = ctx.get("indicators", {})
    if not indicators:
        return ""

    lines = ["[Macro Context]"]

    label_map = {
        "vix": "VIX",
        "sp500": "S&P500",
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


# Singleton-style access
macro_context_service = type("MacroContextService", (), {
    "get_context": staticmethod(get_macro_context),
    "format_for_prompt": staticmethod(format_macro_for_prompt),
})()
