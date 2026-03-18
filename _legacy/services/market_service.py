"""
Market Service — 市場資料統一入口

把原本分散在 pages/market_overview.py 的資料抓取、快取、市場時段判定
集中為 service 層，讓 route / preloader / SSE 只透過這裡取用。
pages/market_overview.py 仍然保留（內含 HTML page builder），
但資料邏輯已全部委派到此。
"""

from pages.market_overview import (
    _FALLBACK_ETFS,
    _FALLBACK_INDICES,
    _FALLBACK_TOP20_TW,
    _FALLBACK_TOP20_US,
    _fetch_market_data,
    _fetch_top20_data,
    _get_fund_flow_data,
    _get_top20_nonblocking,
    _is_tw_market_open,
    _is_tw_trading_day,
    _is_us_market_open,
    _is_us_trading_day,
    _refresh_top20_background,
    get_market_hours_snapshot,
)

__all__ = [
    "FALLBACK_ETFS",
    "FALLBACK_INDICES",
    "FALLBACK_TOP20_TW",
    "FALLBACK_TOP20_US",
    "fetch_market_data",
    "fetch_top20_data",
    "get_fund_flow_data",
    "get_top20_nonblocking",
    "is_tw_market_open",
    "is_tw_trading_day",
    "is_us_market_open",
    "is_us_trading_day",
    "refresh_top20_background",
    "get_market_hours_snapshot",
]

FALLBACK_ETFS = _FALLBACK_ETFS
FALLBACK_INDICES = _FALLBACK_INDICES
FALLBACK_TOP20_TW = _FALLBACK_TOP20_TW
FALLBACK_TOP20_US = _FALLBACK_TOP20_US

fetch_market_data = _fetch_market_data
fetch_top20_data = _fetch_top20_data
get_fund_flow_data = _get_fund_flow_data
get_top20_nonblocking = _get_top20_nonblocking
refresh_top20_background = _refresh_top20_background

is_tw_market_open = _is_tw_market_open
is_tw_trading_day = _is_tw_trading_day
is_us_market_open = _is_us_market_open
is_us_trading_day = _is_us_trading_day
