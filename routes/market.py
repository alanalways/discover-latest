"""Market API routes."""

from __future__ import annotations

import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter
from starlette.concurrency import run_in_threadpool

router = APIRouter()


@router.get("/market/overview")
async def market_overview():
    """Return market indices and ETFs with safe fallback."""
    try:
        from pages.market_overview import _FALLBACK_ETFS, _FALLBACK_INDICES, _fetch_market_data

        data = await _fetch_market_data()
        indices = data.get("indices") or list(_FALLBACK_INDICES)
        etfs = data.get("etfs") or list(_FALLBACK_ETFS)
        return {"indices": indices, "etfs": etfs}
    except Exception as e:
        try:
            from pages.market_overview import _FALLBACK_ETFS, _FALLBACK_INDICES

            return {
                "indices": list(_FALLBACK_INDICES),
                "etfs": list(_FALLBACK_ETFS),
                "error": str(e),
            }
        except Exception:
            return {"indices": [], "etfs": [], "error": str(e)}


@router.get("/market/top20")
async def market_top20():
    """Return top20 by gainers/losers/volume for TW and US."""
    try:
        from pages.market_overview import _FALLBACK_TOP20_TW, _FALLBACK_TOP20_US, _fetch_top20_data

        try:
            data = await asyncio.wait_for(run_in_threadpool(_fetch_top20_data), timeout=8.0)
        except asyncio.TimeoutError:
            return {
                "tw": {"gainers": [], "losers": [], "volume": []},
                "us": {"gainers": [], "losers": [], "volume": []},
                "error": "top20_timeout",
            }

        tw = data.get("tw", [])
        us = data.get("us", [])

        def to_num(value, pct: bool = False) -> float:
            if value is None:
                return 0.0
            if isinstance(value, (int, float)):
                return float(value)
            try:
                text = str(value).strip().replace(",", "")
                if pct:
                    text = text.replace("%", "")
                return float(text) if text else 0.0
            except Exception:
                return 0.0

        def sanitize(rows, market: str):
            cleaned = []
            for row in rows or []:
                if not isinstance(row, dict):
                    continue
                symbol = str(row.get("symbol") or "").strip().upper()
                if not symbol:
                    continue
                if market == "tw":
                    # Keep only standard TW stock code (4 digits).
                    if not (symbol.isdigit() and len(symbol) == 4):
                        continue
                cleaned.append(row)
            return cleaned

        def sort_data(rows, market: str):
            items = sanitize(rows, market)
            if not items and market == "tw":
                items = list((_FALLBACK_TOP20_TW or [])[:20])
            if not items and market == "us":
                items = list((_FALLBACK_TOP20_US or [])[:20])
            return {
                "gainers": sorted(items, key=lambda x: to_num(x.get("change_pct"), pct=True), reverse=True)[:20],
                "losers": sorted(items, key=lambda x: to_num(x.get("change_pct"), pct=True))[:20],
                "volume": sorted(items, key=lambda x: to_num(x.get("volume")), reverse=True)[:20],
            }

        return {"tw": sort_data(tw, "tw"), "us": sort_data(us, "us")}
    except Exception as e:
        return {
            "tw": {"gainers": [], "losers": [], "volume": []},
            "us": {"gainers": [], "losers": [], "volume": []},
            "error": str(e),
        }


@router.get("/market/hours")
async def market_hours():
    """Return market hours status using 2026 holiday calendars."""
    from pages.market_overview import (
        _is_tw_market_open,
        _is_tw_trading_day,
        _is_us_market_open,
        _is_us_trading_day,
    )

    now = datetime.now(ZoneInfo("UTC"))
    tw_now = now.astimezone(ZoneInfo("Asia/Taipei"))
    us_now = now.astimezone(ZoneInfo("America/New_York"))

    return {
        "tw": {
            "is_open": _is_tw_market_open(tw_now),
            "is_trading_day": _is_tw_trading_day(tw_now),
            "time": tw_now.strftime("%H:%M"),
            "timezone": "Asia/Taipei",
        },
        "us": {
            "is_open": _is_us_market_open(us_now),
            "is_trading_day": _is_us_trading_day(us_now),
            "time": us_now.strftime("%H:%M"),
            "timezone": "America/New_York",
        },
    }

