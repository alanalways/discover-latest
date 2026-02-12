"""
Market API — 市場總覽 + Top20 排行
"""
from fastapi import APIRouter
import asyncio
from starlette.concurrency import run_in_threadpool

router = APIRouter()


@router.get("/market/overview")
async def market_overview():
    """取得指數 + ETF 資料（台股 + 美股）"""
    try:
        from pages.market_overview import _fetch_market_data
        data = await _fetch_market_data()
        return {
            "indices": data.get("indices", []),
            "etfs": data.get("etfs", []),
        }
    except Exception as e:
        return {"indices": [], "etfs": [], "error": str(e)}


@router.get("/market/top20")
async def market_top20():
    """取得台美股 Top20 漲跌幅 + 成交量排行"""
    try:
        from pages.market_overview import _fetch_top20_data
        # _fetch_top20_data 內含大量同步 IO，丟到 threadpool 避免阻塞整個 event loop
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

        def _to_num(value, pct: bool = False) -> float:
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

        def _sanitize(stocks, market: str):
            cleaned = []
            for row in stocks or []:
                if not isinstance(row, dict):
                    continue
                symbol = str(row.get("symbol") or "").strip().upper()
                if not symbol:
                    continue
                if market == "tw":
                    if not (symbol.isdigit() and 4 <= len(symbol) <= 5):
                        continue
                cleaned.append(row)
            return cleaned

        def sort_data(stocks, market: str):
            items = _sanitize(stocks, market)
            return {
                "gainers": sorted(items, key=lambda x: _to_num(x.get("change_pct"), pct=True), reverse=True)[:20],
                "losers": sorted(items, key=lambda x: _to_num(x.get("change_pct"), pct=True))[:20],
                "volume": sorted(items, key=lambda x: _to_num(x.get("volume")), reverse=True)[:20],
            }

        return {
            "tw": sort_data(tw, "tw"),
            "us": sort_data(us, "us"),
        }
    except Exception as e:
        return {
            "tw": {"gainers": [], "losers": [], "volume": []},
            "us": {"gainers": [], "losers": [], "volume": []},
            "error": str(e),
        }


@router.get("/market/hours")
async def market_hours():
    """取得台美股開休市狀態（含 2026 休市日規則）"""
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from pages.market_overview import (
        _is_tw_market_open,
        _is_us_market_open,
        _is_tw_trading_day,
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
