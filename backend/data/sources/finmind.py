"""
backend/data/sources/finmind.py
FinMind 台股資料來源（Sonnet 撰寫）

參考 _legacy/adapters/finmind_adapter.py 介面，重新封裝。
用於台股三大法人籌碼、融資融券、日 K 資料。

FINMIND_TOKEN 從環境變數讀取（可無 token，但有 rate limit）。
"""

import logging
import os
from datetime import date, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

_BASE_URL  = "https://api.finmindtrade.com/api/v4/data"
_AGENT_DISPLAY = "FinMind"


def _get_token() -> str:
    return os.environ.get("FINMIND_TOKEN", "")


def _fetch(dataset: str, stock_id: str, start_date: str, end_date: str) -> list[dict]:
    """
    底層 FinMind API 呼叫。

    Returns:
        list of row dicts，失敗時回傳空列表。
    """
    try:
        import requests

        params: dict = {
            "dataset":    dataset,
            "data_id":    stock_id,
            "start_date": start_date,
            "end_date":   end_date,
        }
        token = _get_token()
        if token:
            params["token"] = token

        resp = requests.get(_BASE_URL, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        if data.get("status") != 200:
            logger.warning(
                f"[{_AGENT_DISPLAY}] {dataset} {stock_id} "
                f"回傳非 200 狀態: {data.get('msg', 'unknown')}"
            )
            return []

        return data.get("data", [])

    except Exception as e:
        logger.error(f"[{_AGENT_DISPLAY}] fetch {dataset} {stock_id} 失敗: {e}")
        return []


# ─────────────────────────────────────────────────────────
# 公開 API
# ─────────────────────────────────────────────────────────

def get_price_data(
    symbol:     str,
    days:       int = 120,
) -> dict:
    """
    取得台股日 K 資料（OHLCV）。

    Args:
        symbol: 股票代號（不含後綴，例如 "2330"）
        days:   回溯天數

    Returns:
        dict: {symbol, dates, opens, highs, lows, closes, volumes, error}
    """
    end   = date.today()
    start = end - timedelta(days=days)

    rows = _fetch(
        dataset    = "TaiwanStockPrice",
        stock_id   = symbol,
        start_date = start.isoformat(),
        end_date   = end.isoformat(),
    )

    result = {
        "symbol": symbol, "market": "TW",
        "dates": [], "opens": [], "highs": [],
        "lows": [], "closes": [], "volumes": [],
        "error": None,
    }

    if not rows:
        result["error"] = f"FinMind 無資料: {symbol}"
        return result

    for r in rows:
        result["dates"].append(r.get("date", ""))
        result["opens"].append(float(r.get("open", 0)))
        result["highs"].append(float(r.get("max", 0)))
        result["lows"].append(float(r.get("min", 0)))
        result["closes"].append(float(r.get("close", 0)))
        result["volumes"].append(int(r.get("Trading_Volume", 0)))

    return result


def get_institutional_investors(
    symbol: str,
    days:   int = 30,
) -> dict:
    """
    取得三大法人買賣超資料（外資/投信/自營商）。

    Returns:
        dict: {
            symbol,
            foreign_net: [int],   外資淨買超（張）
            trust_net: [int],     投信淨買超
            dealer_net: [int],    自營商淨買超
            dates: [str],
            error: str | None
        }
    """
    end   = date.today()
    start = end - timedelta(days=days)

    rows = _fetch(
        dataset    = "TaiwanStockInstitutionalInvestorsBuySell",
        stock_id   = symbol,
        start_date = start.isoformat(),
        end_date   = end.isoformat(),
    )

    result: dict = {
        "symbol":      symbol,
        "dates":       [],
        "foreign_net": [],
        "trust_net":   [],
        "dealer_net":  [],
        "error":       None,
    }

    if not rows:
        result["error"] = f"FinMind 無法人資料: {symbol}"
        return result

    # 按日期整理（同一天有多筆，各代表不同法人）
    from collections import defaultdict
    daily: dict = defaultdict(lambda: {"foreign": 0, "trust": 0, "dealer": 0})

    for r in rows:
        d    = r.get("date", "")
        name = r.get("name", "")
        buy  = int(r.get("buy", 0))
        sell = int(r.get("sell", 0))
        net  = buy - sell

        if "外資" in name:
            daily[d]["foreign"] += net
        elif "投信" in name:
            daily[d]["trust"] += net
        elif "自營商" in name:
            daily[d]["dealer"] += net

    for d in sorted(daily.keys()):
        result["dates"].append(d)
        result["foreign_net"].append(daily[d]["foreign"])
        result["trust_net"].append(daily[d]["trust"])
        result["dealer_net"].append(daily[d]["dealer"])

    return result


def get_margin_trading(
    symbol: str,
    days:   int = 30,
) -> dict:
    """
    取得融資融券餘額資料。

    Returns:
        dict: {
            symbol,
            dates: [str],
            margin_balance: [int],   融資餘額（張）
            short_balance: [int],    融券餘額（張）
            error: str | None
        }
    """
    end   = date.today()
    start = end - timedelta(days=days)

    rows = _fetch(
        dataset    = "TaiwanStockMarginPurchaseShortSale",
        stock_id   = symbol,
        start_date = start.isoformat(),
        end_date   = end.isoformat(),
    )

    result: dict = {
        "symbol":         symbol,
        "dates":          [],
        "margin_balance": [],
        "short_balance":  [],
        "error":          None,
    }

    if not rows:
        result["error"] = f"FinMind 無融資融券資料: {symbol}"
        return result

    for r in rows:
        result["dates"].append(r.get("date", ""))
        result["margin_balance"].append(int(r.get("MarginPurchaseTodayBalance", 0)))
        result["short_balance"].append(int(r.get("ShortSaleTodayBalance", 0)))

    return result


def get_chips_data(symbol: str, days: int = 30) -> dict:
    """
    取得完整籌碼資料（三大法人 + 融資融券）。

    整合 get_institutional_investors 與 get_margin_trading 的結果。

    Returns:
        dict: 包含 institutional 和 margin 兩組資料
    """
    institutional = get_institutional_investors(symbol, days)
    margin = get_margin_trading(symbol, days)

    return {
        "symbol": symbol,
        "institutional": institutional,
        "margin": margin,
        "foreign_net": institutional.get("foreign_net", []),
        "trust_net": institutional.get("trust_net", []),
        "dealer_net": institutional.get("dealer_net", []),
        "margin_balance": margin.get("margin_balance", []),
        "short_balance": margin.get("short_balance", []),
        "dates": institutional.get("dates", []),
        "error": institutional.get("error") or margin.get("error"),
    }


def get_current_price(symbol: str) -> Optional[float]:
    """
    取得台股最近收盤價（用最新一天的 close）。

    Returns:
        float 或 None
    """
    data = get_price_data(symbol, days=5)
    if data.get("closes"):
        return data["closes"][-1]
    return None
