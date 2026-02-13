"""Market API routes."""

from __future__ import annotations

import asyncio
from datetime import datetime
import json
import os
from zoneinfo import ZoneInfo
import time

from fastapi import APIRouter
from starlette.concurrency import run_in_threadpool

router = APIRouter()

_TOP20_CACHE: dict = {
    "ts": 0.0,
    "data": None,
}
_TOP20_FETCH_LOCK = asyncio.Lock()
_TOP20_CACHE_FILE = os.path.join(os.getcwd(), ".cache", "top20_cache.json")
_TOP20_DISK_LOADED = False
_TOP20_TTL_OPEN_SEC = 45
_TOP20_TTL_CLOSED_SEC = 1800


def _load_top20_cache_from_disk() -> None:
    global _TOP20_DISK_LOADED
    if _TOP20_DISK_LOADED:
        return
    _TOP20_DISK_LOADED = True
    try:
        if not os.path.exists(_TOP20_CACHE_FILE):
            return
        with open(_TOP20_CACHE_FILE, "r", encoding="utf-8") as f:
            payload = json.load(f)
        if not isinstance(payload, dict):
            return
        data = payload.get("data")
        ts = float(payload.get("ts") or 0.0)
        if isinstance(data, dict) and ts > 0:
            _TOP20_CACHE["data"] = data
            _TOP20_CACHE["ts"] = ts
    except Exception:
        return


def _save_top20_cache_to_disk(data: dict, ts: float) -> None:
    try:
        os.makedirs(os.path.dirname(_TOP20_CACHE_FILE), exist_ok=True)
        with open(_TOP20_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump({"ts": ts, "data": data}, f, ensure_ascii=False)
    except Exception:
        return


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
    _load_top20_cache_from_disk()

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

    def fallback_bucket(rows):
        items = [r for r in (rows or []) if isinstance(r, dict)]
        return {
            "gainers": sorted(items, key=lambda x: to_num(x.get("change_pct"), pct=True), reverse=True)[:20],
            "losers": sorted(items, key=lambda x: to_num(x.get("change_pct"), pct=True))[:20],
            "volume": sorted(items, key=lambda x: to_num(x.get("volume")), reverse=True)[:20],
        }

    def _merge_rows(primary, fallback_rows, target: int = 20):
        merged = []
        seen = set()
        for row in (primary or []) + (fallback_rows or []):
            if not isinstance(row, dict):
                continue
            symbol = str(row.get("symbol") or "").strip().upper()
            if not symbol or symbol in seen:
                continue
            seen.add(symbol)
            merged.append(row)
            if len(merged) >= target:
                break
        return merged

    try:
        from pages.market_overview import (
            _FALLBACK_TOP20_TW,
            _FALLBACK_TOP20_US,
            _fetch_top20_data,
            _is_tw_market_open,
            _is_us_market_open,
        )

        now_utc = datetime.now(ZoneInfo("UTC"))
        tw_now = now_utc.astimezone(ZoneInfo("Asia/Taipei"))
        us_now = now_utc.astimezone(ZoneInfo("America/New_York"))
        tw_open = _is_tw_market_open(tw_now)
        us_open = _is_us_market_open(us_now)
        both_closed = (not tw_open) and (not us_open)

        ttl = _TOP20_TTL_CLOSED_SEC if both_closed else _TOP20_TTL_OPEN_SEC
        cached = _TOP20_CACHE.get("data")
        if cached and (time.time() - float(_TOP20_CACHE.get("ts") or 0.0) < ttl):
            return cached

        async with _TOP20_FETCH_LOCK:
            # Double-check inside lock
            cached = _TOP20_CACHE.get("data")
            if cached and (time.time() - float(_TOP20_CACHE.get("ts") or 0.0) < ttl):
                return cached

            try:
                data = await asyncio.wait_for(run_in_threadpool(_fetch_top20_data), timeout=8.0)
            except asyncio.TimeoutError:
                if _TOP20_CACHE.get("data"):
                    return _TOP20_CACHE["data"]
                payload = {
                    "tw": fallback_bucket(_FALLBACK_TOP20_TW),
                    "us": fallback_bucket(_FALLBACK_TOP20_US),
                    "error": "top20_timeout",
                }
                _TOP20_CACHE["data"] = payload
                _TOP20_CACHE["ts"] = time.time()
                return payload

            tw = data.get("tw", [])
            us = data.get("us", [])

            def sanitize(rows, market: str):
                cleaned = []
                for row in rows or []:
                    if not isinstance(row, dict):
                        continue
                    symbol = str(row.get("symbol") or "").strip().upper()
                    if not symbol:
                        continue
                    if market == "tw":
                        # Keep standard TW tradeable symbols only (4-digit stock/ETF).
                        if not (symbol.isdigit() and len(symbol) == 4):
                            continue
                    cleaned.append(row)
                return cleaned

            def sort_data(rows, market: str):
                items = sanitize(rows, market)
                fallback_rows = list((_FALLBACK_TOP20_TW if market == "tw" else _FALLBACK_TOP20_US) or [])[:20]
                items = _merge_rows(items, fallback_rows, target=20)
                bucket = {
                    "gainers": sorted(items, key=lambda x: to_num(x.get("change_pct"), pct=True), reverse=True)[:20],
                    "losers": sorted(items, key=lambda x: to_num(x.get("change_pct"), pct=True))[:20],
                    "volume": sorted(items, key=lambda x: to_num(x.get("volume")), reverse=True)[:20],
                }
                if len(bucket["gainers"]) < 20:
                    bucket["gainers"] = _merge_rows(
                        bucket["gainers"], sorted(fallback_rows, key=lambda x: to_num(x.get("change_pct"), pct=True), reverse=True), target=20
                    )
                if len(bucket["losers"]) < 20:
                    bucket["losers"] = _merge_rows(
                        bucket["losers"], sorted(fallback_rows, key=lambda x: to_num(x.get("change_pct"), pct=True)), target=20
                    )
                if len(bucket["volume"]) < 20:
                    bucket["volume"] = _merge_rows(
                        bucket["volume"], sorted(fallback_rows, key=lambda x: to_num(x.get("volume")), reverse=True), target=20
                    )
                return bucket

            payload = {"tw": sort_data(tw, "tw"), "us": sort_data(us, "us")}
            _TOP20_CACHE["data"] = payload
            _TOP20_CACHE["ts"] = time.time()
            _save_top20_cache_to_disk(payload, _TOP20_CACHE["ts"])
            return payload
    except Exception as e:
        try:
            from pages.market_overview import _FALLBACK_TOP20_TW, _FALLBACK_TOP20_US
            return {
                "tw": fallback_bucket(_FALLBACK_TOP20_TW),
                "us": fallback_bucket(_FALLBACK_TOP20_US),
                "error": str(e),
            }
        except Exception:
            pass
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
