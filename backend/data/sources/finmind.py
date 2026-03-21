"""
backend/data/sources/finmind.py
FinMind 資料來源 — 主要資料提供者（台股 + 美股）

功能：
  - 雙 Token 輪替（各 600 req/hr，合計 1200 req/hr）
  - 資料集快取（不同 TTL）
  - 完整台股資料：價格、法人、融資融券、PER/PBR、月營收、財報、股利
  - 美股價格資料
  - 自動 fallback（token 耗盡時切換）

參考 _legacy/adapters/finmind_adapter.py 重建。
"""

import logging
import time
import threading
from datetime import date, datetime, timedelta
from typing import Optional, Any
from collections import defaultdict

import requests

from backend.config import FINMIND_TOKENS_LIST, FINMIND_CACHE_TTL

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.finmindtrade.com/api/v4/data"


# ─────────────────────────────────────────────────────────
# Rate Limiter（per token）
# ─────────────────────────────────────────────────────────

class _TokenRateLimiter:
    """單一 token 的速率限制器（滑動窗口）"""

    def __init__(self, max_per_hour: int = 550):
        self.max_per_hour = max_per_hour
        self._timestamps: list[float] = []
        self._lock = threading.Lock()

    def can_request(self) -> bool:
        with self._lock:
            now = time.time()
            self._timestamps = [t for t in self._timestamps if now - t < 3600]
            return len(self._timestamps) < self.max_per_hour

    def record(self):
        with self._lock:
            self._timestamps.append(time.time())

    @property
    def remaining(self) -> int:
        with self._lock:
            now = time.time()
            self._timestamps = [t for t in self._timestamps if now - t < 3600]
            return max(0, self.max_per_hour - len(self._timestamps))


# ─────────────────────────────────────────────────────────
# 快取系統
# ─────────────────────────────────────────────────────────

_cache: dict[str, dict[str, Any]] = {}
_CACHE_MAXSIZE = 512


def _cache_key(dataset: str, data_id: str = "", extra: str = "") -> str:
    return f"{dataset}:{data_id}:{extra}"


def _get_cached(key: str) -> Optional[Any]:
    if key not in _cache:
        return None
    entry = _cache[key]
    dataset = key.split(":")[0]
    ttl = FINMIND_CACHE_TTL.get(dataset, FINMIND_CACHE_TTL.get("_default", 600))
    if time.time() - entry["ts"] < ttl:
        return entry["data"]
    return None


def _set_cache(key: str, data: Any):
    if len(_cache) >= _CACHE_MAXSIZE:
        now = time.time()
        expired = [
            k for k, v in _cache.items()
            if now - v["ts"] > FINMIND_CACHE_TTL.get(
                k.split(":")[0], FINMIND_CACHE_TTL.get("_default", 600)
            )
        ]
        for k in expired:
            _cache.pop(k, None)
        if len(_cache) >= _CACHE_MAXSIZE:
            sorted_keys = sorted(_cache, key=lambda k: _cache[k]["ts"])
            for k in sorted_keys[:len(sorted_keys) // 4]:
                _cache.pop(k, None)
    _cache[key] = {"data": data, "ts": time.time()}


# ─────────────────────────────────────────────────────────
# Token 管理器
# ─────────────────────────────────────────────────────────

class _TokenManager:
    """多 Token 輪替管理"""

    def __init__(self):
        self._tokens: list[str] = list(FINMIND_TOKENS_LIST)
        self._limiters: list[_TokenRateLimiter] = [
            _TokenRateLimiter(max_per_hour=550) for _ in self._tokens
        ]
        self._active_idx: int = 0
        self._cooldown_until: list[float] = [0.0] * len(self._tokens)
        self._lock = threading.Lock()

        if self._tokens:
            logger.info(
                f"[FinMind] Token 管理器初始化: {len(self._tokens)} 把 token, "
                f"合計 ~{len(self._tokens) * 550} req/hr"
            )

    def pick_token(self) -> tuple[str, int]:
        """
        挑選可用 token。
        Returns: (token_str, token_idx)，無可用時 ("", -1)
        """
        with self._lock:
            if not self._tokens:
                return ("", -1)

            now = time.time()
            # 先嘗試當前 active，再依序嘗試其他
            order = [self._active_idx] + [
                i for i in range(len(self._tokens)) if i != self._active_idx
            ]

            old_idx = self._active_idx
            for i in order:
                if now < self._cooldown_until[i]:
                    continue
                if not self._limiters[i].can_request():
                    continue
                self._active_idx = i
                if i != old_idx:
                    remaining = [str(self._limiters[j].remaining) for j in range(len(self._tokens))]
                    logger.info(f"[FinMind] Token 切換 #{old_idx}→#{i}（剩餘 {'/'.join(remaining)}）")
                return (self._tokens[i], i)

            remaining = [str(self._limiters[j].remaining) for j in range(len(self._tokens))]
            logger.warning(f"[FinMind] 所有 Token 額度耗盡（剩餘 {'/'.join(remaining)}）")
            return ("", -1)

    def record_usage(self, idx: int):
        if 0 <= idx < len(self._limiters):
            self._limiters[idx].record()

    def mark_cooldown(self, idx: int, seconds: int, reason: str):
        if 0 <= idx < len(self._limiters):
            self._cooldown_until[idx] = max(
                self._cooldown_until[idx], time.time() + seconds
            )
            logger.info(f"[FinMind] Token #{idx} 暫停 {seconds}s（{reason}）")

    @property
    def total_remaining(self) -> int:
        return sum(l.remaining for l in self._limiters)

    @property
    def token_count(self) -> int:
        return len(self._tokens)


# 全域單例
_token_mgr = _TokenManager()


def get_token_status() -> dict:
    """供外部查詢 token 狀態"""
    return {
        "token_count": _token_mgr.token_count,
        "total_remaining": _token_mgr.total_remaining,
    }


# ─────────────────────────────────────────────────────────
# 底層 API 呼叫
# ─────────────────────────────────────────────────────────

def _fetch(params: dict, use_cache: bool = True) -> Optional[list[dict]]:
    """
    底層 FinMind API 呼叫。
    自動嘗試所有 token，含快取 + rate limit。
    """
    dataset = params.get("dataset", "")
    data_id = params.get("data_id", "")
    start = params.get("start_date", "")
    ckey = _cache_key(dataset, data_id, start)

    # 快取命中
    if use_cache:
        cached = _get_cached(ckey)
        if cached is not None:
            logger.debug(f"[FinMind] 快取命中: {dataset} {data_id}")
            return cached

    # 嘗試所有 token
    attempted: set[int] = set()
    for _ in range(_token_mgr.token_count or 1):  # 至少嘗試一次（anonymous）
        token, idx = _token_mgr.pick_token() if _token_mgr.token_count > 0 else ("", -1)

        if idx >= 0 and idx in attempted:
            break  # 所有 token 都試過了
        if idx >= 0:
            attempted.add(idx)

        req_params = dict(params)
        if token:
            req_params["token"] = token

        try:
            resp = requests.get(_BASE_URL, params=req_params, timeout=15)

            if idx >= 0:
                _token_mgr.record_usage(idx)

            if resp.status_code == 429:
                if idx >= 0:
                    _token_mgr.mark_cooldown(idx, 120, "HTTP 429")
                continue

            if resp.status_code == 402:
                logger.warning(f"[FinMind] {dataset} 需付費方案，跳過")
                return None

            resp.raise_for_status()
            result = resp.json()

            if result.get("status") != 200:
                msg = result.get("msg", "unknown")
                logger.warning(f"[FinMind] {dataset} {data_id} 非 200: {msg}")
                return None

            data = result.get("data", [])
            if data:
                _set_cache(ckey, data)
            return data if data else []

        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response is not None else None
            logger.warning(f"[FinMind] HTTP {status}: {dataset} {data_id}")
            if status == 429 and idx >= 0:
                _token_mgr.mark_cooldown(idx, 120, f"HTTP {status}")
                continue
            return None
        except Exception as e:
            logger.error(f"[FinMind] {dataset} {data_id} 失敗: {e}")
            return None

    logger.warning(f"[FinMind] 所有 token 嘗試完畢: {dataset} {data_id}")
    return None


# ─────────────────────────────────────────────────────────
# 日期工具
# ─────────────────────────────────────────────────────────

def _date_range(days: int) -> tuple[str, str]:
    end = date.today()
    start = end - timedelta(days=days)
    return start.isoformat(), end.isoformat()


# ═════════════════════════════════════════════════════════
# 公開 API — 台股
# ═════════════════════════════════════════════════════════

def get_price_data(symbol: str, days: int = 120) -> dict:
    """
    台股日 K（OHLCV）。

    Returns:
        dict: {symbol, market, dates, opens, highs, lows, closes, volumes, error}
    """
    start_date, end_date = _date_range(days)
    rows = _fetch({
        "dataset": "TaiwanStockPrice",
        "data_id": symbol,
        "start_date": start_date,
        "end_date": end_date,
    })

    result: dict = {
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


def get_institutional_investors(symbol: str, days: int = 30) -> dict:
    """
    三大法人買賣超（外資/投信/自營商）。

    Returns:
        dict: {symbol, dates, foreign_net, trust_net, dealer_net, error}
    """
    start_date, end_date = _date_range(days)
    rows = _fetch({
        "dataset": "TaiwanStockInstitutionalInvestorsBuySell",
        "data_id": symbol,
        "start_date": start_date,
        "end_date": end_date,
    })

    result: dict = {
        "symbol": symbol,
        "dates": [], "foreign_net": [], "trust_net": [], "dealer_net": [],
        "error": None,
    }

    if not rows:
        result["error"] = f"FinMind 無法人資料: {symbol}"
        return result

    daily: dict = defaultdict(lambda: {"foreign": 0, "trust": 0, "dealer": 0})
    for r in rows:
        d = r.get("date", "")
        name = r.get("name", "")
        buy = int(r.get("buy", 0))
        sell = int(r.get("sell", 0))
        net = buy - sell
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


def get_margin_trading(symbol: str, days: int = 30) -> dict:
    """
    融資融券餘額。

    Returns:
        dict: {symbol, dates, margin_balance, short_balance, error}
    """
    start_date, end_date = _date_range(days)
    rows = _fetch({
        "dataset": "TaiwanStockMarginPurchaseShortSale",
        "data_id": symbol,
        "start_date": start_date,
        "end_date": end_date,
    })

    result: dict = {
        "symbol": symbol,
        "dates": [], "margin_balance": [], "short_balance": [],
        "error": None,
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
    完整籌碼資料（三大法人 + 融資融券）。
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


def get_per_pbr(symbol: str, days: int = 365) -> dict:
    """
    PER / PBR / 殖利率。

    Returns:
        dict: {symbol, dates, per, pbr, dividend_yield, error}
    """
    start_date, end_date = _date_range(days)

    # TaiwanStockPER 有時不接受 end_date，用兩段式重試
    attempts = [
        {"dataset": "TaiwanStockPER", "data_id": symbol,
         "start_date": start_date, "end_date": end_date},
        {"dataset": "TaiwanStockPER", "data_id": symbol,
         "start_date": start_date},
        {"dataset": "TaiwanStockPER", "data_id": symbol},
    ]

    rows = None
    for params in attempts:
        rows = _fetch(params)
        if rows:
            break

    result: dict = {
        "symbol": symbol,
        "dates": [], "per": [], "pbr": [], "dividend_yield": [],
        "error": None,
    }

    if not rows:
        result["error"] = f"FinMind 無 PER 資料: {symbol}"
        return result

    for r in rows:
        result["dates"].append(r.get("date", ""))
        result["per"].append(float(r.get("PER", 0)))
        result["pbr"].append(float(r.get("PBR", 0)))
        result["dividend_yield"].append(float(r.get("dividend_yield", 0)))

    return result


def get_month_revenue(symbol: str, days: int = 730) -> dict:
    """
    月營收資料。

    Returns:
        dict: {symbol, dates, revenue, revenue_yoy, error}
    """
    start_date, end_date = _date_range(days)
    rows = _fetch({
        "dataset": "TaiwanStockMonthRevenue",
        "data_id": symbol,
        "start_date": start_date,
        "end_date": end_date,
    })

    result: dict = {
        "symbol": symbol,
        "dates": [], "revenue": [], "revenue_yoy": [],
        "error": None,
    }

    if not rows:
        result["error"] = f"FinMind 無月營收資料: {symbol}"
        return result

    for r in rows:
        result["dates"].append(r.get("date", ""))
        result["revenue"].append(int(r.get("revenue", 0)))
        # YoY 變動率
        yoy = r.get("revenue_month_yoy") or r.get("revenue_year_yoy", 0)
        result["revenue_yoy"].append(float(yoy or 0))

    return result


def get_financial_statements(symbol: str, days: int = 1095) -> dict:
    """
    綜合損益表（約 3 年）。

    Returns:
        dict: {symbol, data: [raw rows], error}
    """
    start_date, end_date = _date_range(days)
    rows = _fetch({
        "dataset": "TaiwanStockFinancialStatements",
        "data_id": symbol,
        "start_date": start_date,
    })

    if not rows:
        return {"symbol": symbol, "data": [], "error": f"FinMind 無財報: {symbol}"}

    return {"symbol": symbol, "data": rows, "error": None}


def get_balance_sheet(symbol: str, days: int = 1095) -> dict:
    """
    資產負債表（約 3 年）。

    Returns:
        dict: {symbol, data: [raw rows], error}
    """
    start_date, _ = _date_range(days)
    rows = _fetch({
        "dataset": "TaiwanStockBalanceSheet",
        "data_id": symbol,
        "start_date": start_date,
    })

    if not rows:
        return {"symbol": symbol, "data": [], "error": f"FinMind 無資產負債表: {symbol}"}

    return {"symbol": symbol, "data": rows, "error": None}


def get_dividend(symbol: str, days: int = 1825) -> dict:
    """
    股利政策（約 5 年）。

    Returns:
        dict: {symbol, data: [raw rows], error}
    """
    start_date, end_date = _date_range(days)
    rows = _fetch({
        "dataset": "TaiwanStockDividend",
        "data_id": symbol,
        "start_date": start_date,
        "end_date": end_date,
    })

    if not rows:
        return {"symbol": symbol, "data": [], "error": f"FinMind 無股利資料: {symbol}"}

    return {"symbol": symbol, "data": rows, "error": None}


def get_stock_info(symbol: Optional[str] = None) -> list[dict]:
    """
    台股基本資訊（公司名稱、產業分類）。
    不帶 symbol 時回傳全量清單。
    """
    params: dict = {"dataset": "TaiwanStockInfo"}
    if symbol:
        params["data_id"] = symbol

    rows = _fetch(params)
    if not rows:
        return []

    return [
        {
            "symbol": r.get("stock_id"),
            "name": r.get("stock_name"),
            "industry": r.get("industry_category"),
            "market": "TWSE" if r.get("type") == "twse" else "TPEX",
            "type": r.get("type", "stock"),
        }
        for r in rows
    ]


def get_current_price(symbol: str) -> Optional[float]:
    """取得台股最近收盤價"""
    data = get_price_data(symbol, days=5)
    if data.get("closes"):
        return data["closes"][-1]
    return None


def get_fundamentals(symbol: str) -> dict:
    """
    台股基本面彙整（PER/PBR + 月營收 + 公司資訊）。
    供 Pipeline 使用，一次呼叫取得所有基本面資料。

    Returns:
        dict: {
            symbol, name, industry, market,
            per, pbr, dividend_yield,
            recent_revenue, revenue_yoy,
            error
        }
    """
    result: dict = {
        "symbol": symbol, "name": symbol, "industry": None,
        "market": "TW", "sector": None,
        "per": None, "pbr": None, "dividend_yield": None,
        "pe_ratio": None, "pb_ratio": None,
        "recent_revenue": None, "revenue_yoy": None,
        "market_cap": None, "currency": "TWD",
        "error": None,
    }

    # 公司資訊
    info_list = get_stock_info(symbol)
    if info_list:
        info = info_list[0]
        result["name"] = info.get("name", symbol)
        result["industry"] = info.get("industry")
        result["sector"] = info.get("industry")

    # PER/PBR
    per_data = get_per_pbr(symbol, days=30)
    if per_data.get("per"):
        result["per"] = per_data["per"][-1]
        result["pe_ratio"] = per_data["per"][-1]
    if per_data.get("pbr"):
        result["pbr"] = per_data["pbr"][-1]
        result["pb_ratio"] = per_data["pbr"][-1]
    if per_data.get("dividend_yield"):
        result["dividend_yield"] = per_data["dividend_yield"][-1]

    # 月營收
    rev_data = get_month_revenue(symbol, days=90)
    if rev_data.get("revenue"):
        result["recent_revenue"] = rev_data["revenue"][-1]
    if rev_data.get("revenue_yoy"):
        result["revenue_yoy"] = rev_data["revenue_yoy"][-1]

    return result


# ═════════════════════════════════════════════════════════
# 公開 API — 美股
# ═════════════════════════════════════════════════════════

def get_us_price_data(symbol: str, days: int = 120) -> dict:
    """
    美股日 K（OHLCV）。

    Returns:
        dict: {symbol, market, dates, opens, highs, lows, closes, volumes, error}
    """
    start_date, end_date = _date_range(days)
    rows = _fetch({
        "dataset": "USStockPrice",
        "data_id": symbol,
        "start_date": start_date,
        "end_date": end_date,
    })

    result: dict = {
        "symbol": symbol, "market": "US",
        "dates": [], "opens": [], "highs": [],
        "lows": [], "closes": [], "volumes": [],
        "error": None,
    }

    if not rows:
        result["error"] = f"FinMind 無美股資料: {symbol}"
        return result

    for r in rows:
        result["dates"].append(r.get("date", ""))
        result["opens"].append(float(r.get("Open", r.get("open", 0))))
        result["highs"].append(float(r.get("High", r.get("high", 0))))
        result["lows"].append(float(r.get("Low", r.get("low", 0))))
        result["closes"].append(float(r.get("Close", r.get("close", 0))))
        result["volumes"].append(int(r.get("Volume", r.get("Trading_Volume", 0))))

    return result


def get_us_current_price(symbol: str) -> Optional[float]:
    """取得美股最近收盤價"""
    data = get_us_price_data(symbol, days=5)
    if data.get("closes"):
        return data["closes"][-1]
    return None


# ═════════════════════════════════════════════════════════
# 搜尋
# ═════════════════════════════════════════════════════════

_stock_info_cache: dict[str, Any] = {"data": None, "ts": 0}


def search_tw_stocks(query: str, limit: int = 20) -> list[dict]:
    """
    搜尋台股（代號或名稱）。
    快取全量 TaiwanStockInfo 避免重複呼叫。
    """
    global _stock_info_cache
    now = time.time()

    if _stock_info_cache["data"] and (now - _stock_info_cache["ts"]) < 3600:
        all_info = _stock_info_cache["data"]
    else:
        all_info = get_stock_info()
        if all_info:
            _stock_info_cache = {"data": all_info, "ts": now}

    if not all_info:
        return []

    q = query.strip().upper()
    results = []
    for item in all_info:
        sym = (item.get("symbol") or "").upper()
        name = (item.get("name") or "").upper()
        if q in sym or q in name:
            results.append(item)
            if len(results) >= limit:
                break

    return results
