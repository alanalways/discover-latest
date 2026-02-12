"""
Market API — 市場總覽 + Top20 排行
"""
from fastapi import APIRouter
from typing import Optional

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
        data = _fetch_top20_data()
        tw = data.get("tw", [])
        us = data.get("us", [])

        def sort_data(stocks):
            return {
                "gainers": sorted(stocks, key=lambda x: x.get("change_pct", 0), reverse=True)[:20],
                "losers": sorted(stocks, key=lambda x: x.get("change_pct", 0))[:20],
                "volume": sorted(stocks, key=lambda x: x.get("volume", 0), reverse=True)[:20],
            }

        return {
            "tw": sort_data(tw),
            "us": sort_data(us),
        }
    except Exception as e:
        return {"tw": {}, "us": {}, "error": str(e)}


@router.get("/market/hours")
async def market_hours():
    """取得台美股開休市狀態（前端也可用 JS 自行計算）"""
    from datetime import datetime
    import pytz

    tw_tz = pytz.timezone("Asia/Taipei")
    us_tz = pytz.timezone("America/New_York")
    now = datetime.now(pytz.utc)
    tw_now = now.astimezone(tw_tz)
    us_now = now.astimezone(us_tz)

    def is_open(dt, open_h, open_m, close_h, close_m):
        if dt.weekday() >= 5:  # 週末
            return False
        mins = dt.hour * 60 + dt.minute
        return open_h * 60 + open_m <= mins < close_h * 60 + close_m

    return {
        "tw": {
            "is_open": is_open(tw_now, 9, 0, 13, 30),
            "time": tw_now.strftime("%H:%M"),
            "timezone": "Asia/Taipei",
        },
        "us": {
            "is_open": is_open(us_now, 9, 30, 16, 0),
            "time": us_now.strftime("%H:%M"),
            "timezone": "America/New_York",
        },
    }
