"""
backend/data/sources/twse.py
TWSE（台灣證券交易所）公開 API — 備援資料來源

功能：
- 無需 Token，公開 API
- 取得台股日 K（OHLCV）
- 日期格式：ROC 民國年 → ISO 格式轉換

用途：FinMind + Yahoo 都失敗時的第三道防線
"""

import logging
import time
import threading
from datetime import date
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# 簡單快取（避免重複呼叫，TTL 15 分鐘）
_cache: dict = {}
_cache_lock = threading.Lock()
_CACHE_TTL = 900  # 15 分鐘


def _get_cached(key: str) -> Optional[dict]:
    with _cache_lock:
        entry = _cache.get(key)
        if entry and (time.time() - entry["ts"]) < _CACHE_TTL:
            return entry["data"]
    return None


def _set_cached(key: str, data: dict):
    with _cache_lock:
        _cache[key] = {"data": data, "ts": time.time()}


def _roc_to_iso(roc_date: str) -> Optional[str]:
    """
    民國年轉 ISO 格式。
    "113/03/01" → "2024-03-01"
    """
    try:
        parts = roc_date.strip().split("/")
        if len(parts) != 3:
            return None
        year = int(parts[0]) + 1911
        return f"{year:04d}-{int(parts[1]):02d}-{int(parts[2]):02d}"
    except Exception:
        return None


def _parse_price(s: str) -> Optional[float]:
    """解析可能含逗號的價格字串。"""
    try:
        return float(str(s).replace(",", ""))
    except Exception:
        return None


def get_price_data_twse(symbol: str, months: int = 5) -> dict:
    """
    從 TWSE 公開 API 取得台股日 K 資料。

    Args:
        symbol: 股票代號（如 "2454"）
        months: 取幾個月的資料（預設 5 個月，約 100 個交易日）

    Returns:
        dict: {symbol, market, dates, opens, highs, lows, closes, volumes, error}
    """
    cache_key = f"twse:{symbol}:{date.today().isoformat()}"
    cached = _get_cached(cache_key)
    if cached:
        logger.debug(f"[TWSE] 快取命中: {symbol}")
        return cached

    base_url = "https://www.twse.com.tw/exchangeReport/STOCK_DAY"
    today = date.today()

    all_dates: list[str] = []
    all_opens: list[float] = []
    all_highs: list[float] = []
    all_lows: list[float] = []
    all_closes: list[float] = []
    all_volumes: list[int] = []

    # 從當月往回取 months 個月
    for i in range(months):
        # 計算目標月份
        year = today.year
        month = today.month - i
        while month <= 0:
            month += 12
            year -= 1

        date_str = f"{year:04d}{month:02d}01"

        try:
            resp = requests.get(
                base_url,
                params={
                    "response": "json",
                    "date": date_str,
                    "stockNo": symbol,
                },
                timeout=10,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    ),
                    "Referer": "https://www.twse.com.tw",
                },
            )

            if resp.status_code != 200:
                logger.warning(f"[TWSE] HTTP {resp.status_code}: {symbol} {date_str}")
                continue

            payload = resp.json()
            if payload.get("stat") != "OK":
                logger.debug(f"[TWSE] stat != OK: {symbol} {date_str} → {payload.get('stat')}")
                continue

            # fields: ["日期","成交股數","成交金額","開盤價","最高價","最低價","收盤價","漲跌價差","成交筆數"]
            for row in payload.get("data", []):
                if len(row) < 7:
                    continue

                iso_date = _roc_to_iso(row[0])
                if not iso_date:
                    continue

                open_p  = _parse_price(row[3])
                high_p  = _parse_price(row[4])
                low_p   = _parse_price(row[5])
                close_p = _parse_price(row[6])
                vol     = _parse_price(row[1])

                if None in (open_p, high_p, low_p, close_p):
                    continue

                all_dates.append(iso_date)
                all_opens.append(round(open_p, 4))
                all_highs.append(round(high_p, 4))
                all_lows.append(round(low_p, 4))
                all_closes.append(round(close_p, 4))
                all_volumes.append(int(vol) if vol else 0)

        except Exception as e:
            logger.warning(f"[TWSE] {symbol} {date_str} 請求失敗: {e}")

        # 稍微 rate limit
        time.sleep(0.3)

    result = {
        "symbol": symbol,
        "market": "TW",
        "dates":   all_dates,
        "opens":   all_opens,
        "highs":   all_highs,
        "lows":    all_lows,
        "closes":  all_closes,
        "volumes": all_volumes,
        "error":   None if all_closes else f"TWSE 無資料: {symbol}",
    }

    if all_closes:
        _set_cached(cache_key, result)
        logger.info(
            f"[TWSE] {symbol} 取得 {len(all_closes)} 筆資料 "
            f"({all_dates[0] if all_dates else '?'} ~ {all_dates[-1] if all_dates else '?'})"
        )
    else:
        logger.warning(f"[TWSE] {symbol} 無資料")

    return result
