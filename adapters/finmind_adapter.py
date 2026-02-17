"""
FinMind Adapter - 主要資料來源 (台股 + 美股)
https://finmindtrade.com/

雙 Token 系統：
  FINMIND_TOKEN   — 主帳號 (600 req/hr)
  FINMIND_TOKEN_2 — 備用帳號 (600 req/hr)
  總額度：~1200 req/hr，主 token 用完自動切備用
"""
import logging
import os
import httpx
import time
import threading
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Set, Tuple
import asyncio



logger = logging.getLogger(__name__)
class _FinMindRateLimiter:
    """FinMind API 速率限制器"""
    def __init__(self, max_requests: int = 550, window_seconds: int = 3600):
        self.max_requests = max_requests
        self.window = window_seconds
        self._timestamps: list = []
        self._lock = threading.Lock()

    def can_request(self) -> bool:
        with self._lock:
            now = time.time()
            self._timestamps = [t for t in self._timestamps if now - t < self.window]
            return len(self._timestamps) < self.max_requests

    def record(self):
        with self._lock:
            self._timestamps.append(time.time())

    @property
    def remaining(self) -> int:
        with self._lock:
            now = time.time()
            self._timestamps = [t for t in self._timestamps if now - t < self.window]
            return max(0, self.max_requests - len(self._timestamps))


# ===== 多層快取系統 =====
_cache: Dict[str, Dict[str, Any]] = {}

# 各資料集 TTL（秒）
_CACHE_TTL = {
    "TaiwanStockInfo": 3600,       # 1 小時（全量清單極少變動）
    "TaiwanStockPrice": 900,       # 15 分鐘（盤中更新）
    "TaiwanStockPER": 7200,        # 2 小時（每日更新一次）
    "TaiwanStockMonthRevenue": 86400,  # 24 小時（月更新）
    "TaiwanStockFinancialStatements": 86400,  # 24 小時
    "TaiwanStockBalanceSheet": 86400,  # 24 小時
    "TaiwanStockCashFlowsStatement": 86400,  # 24 小時
    "TaiwanStockDividend": 86400,  # 24 小時
    "TaiwanStockMarketValue": 7200,  # 2 小時
    "USStockPrice": 900,           # 15 分鐘
    "_default": 600,               # 預設 10 分鐘
}


def _cache_key(dataset: str, data_id: str = "", extra: str = "") -> str:
    return f"{dataset}:{data_id}:{extra}"


def _get_cached(key: str) -> Optional[Any]:
    """取得快取資料（未過期才回傳）"""
    if key not in _cache:
        return None
    entry = _cache[key]
    dataset = key.split(":")[0]
    ttl = _CACHE_TTL.get(dataset, _CACHE_TTL["_default"])
    if time.time() - entry["ts"] < ttl:
        return entry["data"]
    return None


def _set_cache(key: str, data: Any):
    """寫入快取"""
    _cache[key] = {"data": data, "ts": time.time()}


class FinMindAdapter:
    """FinMind 資料 Adapter（台股 + 美股主要來源，多 Token 輪替）"""

    BASE_URL = "https://api.finmindtrade.com/api/v4"

    def __init__(self):
        self._tokens: List[Optional[str]] = [None, None, None, None]  # 支援最多 4 組 Token
        self._active_token_idx = 0
        self._available = True
        self._last_check: Optional[datetime] = None
        self._token_cooldown_until: List[float] = [0.0, 0.0, 0.0, 0.0]
        self._dataset_cooldown_until: Dict[str, float] = {}
        # 多組 Rate Limiter（每組 600/hr，留 50 buffer）
        self.rate_limiters = [
            _FinMindRateLimiter(max_requests=550, window_seconds=3600),
            _FinMindRateLimiter(max_requests=550, window_seconds=3600),
            _FinMindRateLimiter(max_requests=550, window_seconds=3600),
            _FinMindRateLimiter(max_requests=550, window_seconds=3600),
        ]
        # 共享連線池（覆用 TCP 連線，避免每次新建）
        self._async_client = httpx.AsyncClient(
            timeout=30.0,
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )

    async def close(self):
        """關閉共享 httpx client"""
        await self._async_client.aclose()

    @property
    def rate_limiter(self):
        """相容舊 API：回傳當前 active limiter"""
        return self.rate_limiters[self._active_token_idx]

    def _load_tokens(self):
        """載入環境變數中的 Token"""
        env_keys = ["FINMIND_TOKEN", "FINMIND_TOKEN_2", "FINMIND_TOKEN_3", "FINMIND_TOKEN_4"]
        for i, key in enumerate(env_keys):
            if not self._tokens[i]:
                self._tokens[i] = os.environ.get(key, "")

    def _token_is_usable(self, idx: int) -> bool:
        token = self._tokens[idx]
        if not token:
            return False
        if time.time() < self._token_cooldown_until[idx]:
            return False
        if not self.rate_limiters[idx].can_request():
            return False
        return True

    def _pick_token(self, exclude: Optional[Set[int]] = None) -> Tuple[str, int]:
        """挑選可用 token，必要時自動切換"""
        self._load_tokens()
        exclude = exclude or set()
        order = [self._active_token_idx] + [i for i in range(len(self._tokens)) if i != self._active_token_idx]

        old_idx = self._active_token_idx
        for i in order:
            if i in exclude:
                continue
            if self._token_is_usable(i):
                self._active_token_idx = i
                if i != old_idx:
                    remaining = [str(self.rate_limiters[j].remaining) for j in range(len(self._tokens))]
                    logger.info(f"[FinMind] Token 切換 #{old_idx}→#{i}（剩餘 {'/'.join(remaining)}）")
                return self._tokens[i] or "", i

        remaining = [str(self.rate_limiters[j].remaining) for j in range(len(self._tokens))]
        logger.info(f"[FinMind] 所有 Token 額度耗盡（剩餘 {'/'.join(remaining)}）")
        return "", -1

    def _mark_token_cooldown(self, idx: int, seconds: int, reason: str):
        until = time.time() + seconds
        self._token_cooldown_until[idx] = max(self._token_cooldown_until[idx], until)
        logger.info(f"[FinMind] Token #{idx} 暫停 {seconds}s（{reason}）")

    def _is_dataset_cooling_down(self, dataset: str) -> bool:
        if not dataset:
            return False
        until = self._dataset_cooldown_until.get(dataset, 0.0)
        now = time.time()
        if now < until:
            return True
        if until:
            self._dataset_cooldown_until.pop(dataset, None)
        return False

    def _mark_dataset_cooldown(self, dataset: str, seconds: int, reason: str):
        if not dataset:
            return
        until = time.time() + seconds
        self._dataset_cooldown_until[dataset] = max(self._dataset_cooldown_until.get(dataset, 0.0), until)
        logger.info(f"[FinMind] Dataset {dataset} 暫停 {seconds}s（{reason}）")

    def _get_token(self) -> str:
        """取得 FinMind API Token（多 Token 自動切換）"""
        token, _ = self._pick_token()
        return token

    @staticmethod
    def _normalize_start_date(start_date: Optional[str], fallback_days: int = 365) -> str:
        """防呆：避免送出空 start_date 造成 FinMind 400"""
        if isinstance(start_date, str) and start_date.strip():
            return start_date.strip()
        return (datetime.now() - timedelta(days=fallback_days)).strftime("%Y-%m-%d")

    async def health_check(self) -> bool:
        """可用性偵測"""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{self.BASE_URL}/data",
                    params={"dataset": "TaiwanStockInfo", "token": self._get_token()},
                )
                self._available = resp.status_code == 200
                self._last_check = datetime.now()
                return self._available
        except Exception:
            self._available = False
            self._last_check = datetime.now()
            return False

    @property
    def is_available(self) -> bool:
        if self._last_check and (datetime.now() - self._last_check).seconds < 300:
            return self._available
        return True  # 假設可用，下次請求時偵測

    async def _request(self, params: Dict, use_cache: bool = True) -> Optional[List[Dict]]:
        """發送 API 請求（含快取 + 雙 Token 速率限制）"""
        # 快取檢查
        dataset = params.get("dataset", "")
        if self._is_dataset_cooling_down(dataset):
            return None

        data_id = params.get("data_id", "")
        start = params.get("start_date", "")
        ckey = _cache_key(dataset, data_id, start)
        if use_cache:
            cached = _get_cached(ckey)
            if cached is not None:
                return cached

        self._load_tokens()
        total_tokens = len([t for t in self._tokens if t])
        if total_tokens == 0:
            logger.debug("[FinMind] 無可用 Token")
            return None

        attempted: Set[int] = set()
        had_payment_limit = False
        had_rate_limit = False
        for _ in range(total_tokens):
            token, token_idx = self._pick_token(exclude=attempted)
            if not token or token_idx < 0:
                break

            attempted.add(token_idx)
            limiter = self.rate_limiters[token_idx]
            req_params = dict(params)
            if "start_date" in req_params:
                req_params["start_date"] = self._normalize_start_date(req_params.get("start_date"))
            req_params["token"] = token

            try:
                resp = await self._async_client.get(f"{self.BASE_URL}/data", params=req_params)
                limiter.record()
                resp.raise_for_status()
                result = resp.json()
                if result.get("status") == 200 and result.get("data"):
                    self._available = True
                    _set_cache(ckey, result["data"])  # 寫入快取
                    return result["data"]
                return None
            except httpx.HTTPStatusError as e:
                status = e.response.status_code if e.response else None
                if status == 400 and dataset == "TaiwanStockMarketValue":
                    # This dataset is unstable for some accounts and often returns persistent 400.
                    # Cool it down to avoid repeated noisy retries on every request path.
                    self._mark_dataset_cooldown(dataset, 3600, "HTTP 400（資料集暫不可用）")
                    return None
                if status in (402, 429):
                    cooldown = 900 if status == 402 else 120
                    self._mark_token_cooldown(token_idx, cooldown, f"HTTP {status}")
                    if status == 402:
                        had_payment_limit = True
                    elif status == 429:
                        had_rate_limit = True
                    continue
                logger.debug(f"[FinMind] 請求失敗: HTTP {status}: {e}")
                self._available = False
                return None
            except Exception as e:
                logger.debug(f"[FinMind] 請求失敗: {type(e).__name__}: {e}")
                self._available = False
                return None

        if had_payment_limit:
            dataset_cooldown = 180 if dataset == "USStockPrice" else 120
            self._mark_dataset_cooldown(dataset, dataset_cooldown, "所有 Token 付費限制或配額不足")
        elif had_rate_limit:
            self._mark_dataset_cooldown(dataset, 60, "所有 Token 速率限制")
        return None

    # ===== 台股資料 =====

    async def get_tw_stock_price(
        self, symbol: str, start_date: str, end_date: str = None
    ) -> List[Dict]:
        """取得台股日K資料 (OHLCV)"""
        if end_date is None:
            end_date = datetime.now().strftime("%Y-%m-%d")
        data = await self._request({
            "dataset": "TaiwanStockPrice",
            "data_id": symbol,
            "start_date": start_date,
            "end_date": end_date,
        })
        if not data:
            return []
        return [
            {
                "symbol": d.get("stock_id", symbol),
                "date": d.get("date"),
                "open": float(d.get("open", 0)),
                "high": float(d.get("max", 0)),
                "low": float(d.get("min", 0)),
                "close": float(d.get("close", 0)),
                "volume": int(d.get("Trading_Volume", 0)),
                "value": float(d.get("Trading_money", 0)),
            }
            for d in data
        ]

    async def get_tw_stock_info(self, symbol: str = None) -> List[Dict]:
        """取得台股基本資訊列表"""
        params = {"dataset": "TaiwanStockInfo"}
        if symbol:
            params["data_id"] = symbol
        data = await self._request(params)
        if not data:
            return []
        return [
            {
                "symbol": d.get("stock_id"),
                "name": d.get("stock_name"),
                "industry": d.get("industry_category"),
                "market": "TWSE" if d.get("type") == "twse" else "TPEX",
                "type": d.get("type", "stock"),
            }
            for d in data
        ]

    async def get_tw_institutional(self, symbol: str, start_date: str, end_date: str = None) -> List[Dict]:
        """取得台股三大法人買賣超"""
        if end_date is None:
            end_date = datetime.now().strftime("%Y-%m-%d")
        data = await self._request({
            "dataset": "TaiwanStockInstitutionalInvestorsBuySell",
            "data_id": symbol,
            "start_date": start_date,
            "end_date": end_date,
        })
        return data or []

    async def get_tw_margin(self, symbol: str, start_date: str, end_date: str = None) -> List[Dict]:
        """取得台股融資融券"""
        if end_date is None:
            end_date = datetime.now().strftime("%Y-%m-%d")
        data = await self._request({
            "dataset": "TaiwanStockMarginPurchaseShortSale",
            "data_id": symbol,
            "start_date": start_date,
            "end_date": end_date,
        })
        return data or []

    async def get_tw_revenue(self, symbol: str, start_date: str, end_date: str = None) -> List[Dict]:
        """取得台股月營收"""
        if end_date is None:
            end_date = datetime.now().strftime("%Y-%m-%d")
        data = await self._request({
            "dataset": "TaiwanStockMonthRevenue",
            "data_id": symbol,
            "start_date": start_date,
            "end_date": end_date,
        })
        return data or []

    async def get_tw_per_pbr(
        self, symbol: str, start_date: str, end_date: str = None
    ) -> List[Dict]:
        """取得台股 PER / PBR / 殖利率 (TaiwanStockPER)"""
        # TaiwanStockPER 在不同帳號下參數容忍度不同，採兩段式重試
        start_date = self._normalize_start_date(start_date, fallback_days=365)
        if end_date is None:
            end_date = datetime.now().strftime("%Y-%m-%d")
        attempts = [
            {
                "dataset": "TaiwanStockPER",
                "data_id": symbol,
                "start_date": start_date,
                "end_date": end_date,
            },
            {
                "dataset": "TaiwanStockPER",
                "data_id": symbol,
                "start_date": start_date,
            },
            {
                "dataset": "TaiwanStockPER",
                "data_id": symbol,
            },
        ]
        for params in attempts:
            data = await self._request(params)
            if data:
                return data
        return []

    async def get_tw_financial_statements(
        self, symbol: str, start_date: str
    ) -> List[Dict]:
        """取得台股綜合損益表 (TaiwanStockFinancialStatements)"""
        data = await self._request({
            "dataset": "TaiwanStockFinancialStatements",
            "data_id": symbol,
            "start_date": start_date,
        })
        return data or []

    async def get_tw_dividend(
        self, symbol: str, start_date: str, end_date: str = None
    ) -> List[Dict]:
        """取得台股股利政策 (TaiwanStockDividend)"""
        if end_date is None:
            end_date = datetime.now().strftime("%Y-%m-%d")
        data = await self._request({
            "dataset": "TaiwanStockDividend",
            "data_id": symbol,
            "start_date": start_date,
            "end_date": end_date,
        })
        return data or []

    async def get_tw_stock_info_all(self) -> List[Dict]:
        """取得全部台股清單 + 產業分類 (TaiwanStockInfo，不帶 data_id)"""
        data = await self._request({"dataset": "TaiwanStockInfo"})
        if not data:
            return []
        return [
            {
                "symbol": d.get("stock_id"),
                "name": d.get("stock_name"),
                "industry": d.get("industry_category"),
                "market": "TWSE" if d.get("type") == "twse" else "TPEX",
                "type": d.get("type", "stock"),
            }
            for d in data
        ]

    # ===== 美股資料 =====

    async def get_us_stock_price(
        self, symbol: str, start_date: str, end_date: str = None
    ) -> List[Dict]:
        """取得美股日K資料"""
        if end_date is None:
            end_date = datetime.now().strftime("%Y-%m-%d")
        data = await self._request({
            "dataset": "USStockPrice",
            "data_id": symbol,
            "start_date": start_date,
            "end_date": end_date,
        })
        if not data:
            return []
        return [
            {
                "symbol": d.get("stock_id", symbol),
                "date": d.get("date"),
                "open": float(d.get("Open", d.get("open", 0))),
                "high": float(d.get("High", d.get("high", 0))),
                "low": float(d.get("Low", d.get("low", 0))),
                "close": float(d.get("Close", d.get("close", 0))),
                "volume": int(d.get("Volume", d.get("Trading_Volume", d.get("volume", 0)))),
                "adj_close": float(d.get("Adj_Close", d.get("adj_close", d.get("close", 0)))),
            }
            for d in data
        ]

    async def get_us_stock_info(self, symbol: str = None) -> List[Dict]:
        """取得美股基本資訊"""
        params = {"dataset": "USStockInfo"}
        if symbol:
            params["data_id"] = symbol
        data = await self._request(params)
        return data or []

    # ===== 台股指數 =====

    async def get_tw_index(self, start_date: str, end_date: str = None) -> List[Dict]:
        """取得台股加權指數"""
        if end_date is None:
            end_date = datetime.now().strftime("%Y-%m-%d")
        data = await self._request({
            "dataset": "TaiwanStockTotalMarketValue",
            "start_date": start_date,
            "end_date": end_date,
        })
        return data or []

    # ===== 搜尋 =====

    async def search_tw_stocks(self, query: str, limit: int = 20) -> List[Dict]:
        """搜尋台股代號/名稱（使用快取避免重複呼叫）"""
        global _stock_info_cache
        now = time.time()
        if _stock_info_cache["data"] and (now - _stock_info_cache["ts"]) < _STOCK_INFO_CACHE_TTL:
            all_info = _stock_info_cache["data"]
        else:
            all_info = await self.get_tw_stock_info()
            if all_info:
                _stock_info_cache = {"data": all_info, "ts": now}
        results = []
        query_lower = query.lower()
        for info in (all_info or []):
            sym = info.get("symbol", "").lower()
            name = info.get("name", "").lower()
            if query_lower in sym or query_lower in name:
                results.append(info)
                if len(results) >= limit:
                    break
        return results

    # ===== 同步包裝 =====

    def _sync_request(self, params: Dict) -> Optional[List[Dict]]:
        """同步 API 請求（含速率限制 + 多 Token 自動切換）"""
        dataset = params.get("dataset", "")
        if self._is_dataset_cooling_down(dataset):
            return None

        self._load_tokens()
        total_tokens = len([t for t in self._tokens if t])
        if total_tokens == 0:
            logger.debug("[FinMind] 無可用 Token")
            return None

        attempted: Set[int] = set()
        had_payment_limit = False
        had_rate_limit = False
        for _ in range(total_tokens):
            token, token_idx = self._pick_token(exclude=attempted)
            if not token or token_idx < 0:
                break

            attempted.add(token_idx)
            limiter = self.rate_limiters[token_idx]
            req_params = dict(params)
            if "start_date" in req_params:
                req_params["start_date"] = self._normalize_start_date(req_params.get("start_date"))
            req_params["token"] = token

            try:
                with httpx.Client(timeout=30.0) as client:
                    resp = client.get(f"{self.BASE_URL}/data", params=req_params)
                    limiter.record()
                    resp.raise_for_status()
                    result = resp.json()
                    if result.get("status") == 200 and result.get("data"):
                        return result["data"]
                    return None
            except httpx.HTTPStatusError as e:
                status = e.response.status_code if e.response else None
                if status == 400 and dataset == "TaiwanStockMarketValue":
                    self._mark_dataset_cooldown(dataset, 3600, "HTTP 400（資料集暫不可用）")
                    return None
                if status in (402, 429):
                    cooldown = 900 if status == 402 else 120
                    self._mark_token_cooldown(token_idx, cooldown, f"HTTP {status}")
                    if status == 402:
                        had_payment_limit = True
                    elif status == 429:
                        had_rate_limit = True
                    continue
                logger.debug(f"[FinMind] 同步請求失敗: HTTP {status}: {e}")
                return None
            except Exception as e:
                logger.debug(f"[FinMind] 同步請求失敗: {type(e).__name__}: {e}")
                return None

        if had_payment_limit:
            dataset_cooldown = 180 if dataset == "USStockPrice" else 120
            self._mark_dataset_cooldown(dataset, dataset_cooldown, "所有 Token 付費限制或配額不足")
        elif had_rate_limit:
            self._mark_dataset_cooldown(dataset, 60, "所有 Token 速率限制")
        return None

    def get_tw_institutional_sync(
        self, symbol: str, start_date: str, end_date: str = None
    ) -> List[Dict]:
        """同步：三大法人買賣超"""
        if end_date is None:
            end_date = datetime.now().strftime("%Y-%m-%d")
        data = self._sync_request({
            "dataset": "TaiwanStockInstitutionalInvestorsBuySell",
            "data_id": symbol,
            "start_date": start_date,
            "end_date": end_date,
        })
        return data or []

    def get_tw_margin_sync(
        self, symbol: str, start_date: str, end_date: str = None
    ) -> List[Dict]:
        """同步：融資融券"""
        if end_date is None:
            end_date = datetime.now().strftime("%Y-%m-%d")
        data = self._sync_request({
            "dataset": "TaiwanStockMarginPurchaseShortSale",
            "data_id": symbol,
            "start_date": start_date,
            "end_date": end_date,
        })
        return data or []

    def get_tw_revenue_sync(
        self, symbol: str, start_date: str, end_date: str = None
    ) -> List[Dict]:
        """同步：月營收"""
        if end_date is None:
            end_date = datetime.now().strftime("%Y-%m-%d")
        data = self._sync_request({
            "dataset": "TaiwanStockMonthRevenue",
            "data_id": symbol,
            "start_date": start_date,
            "end_date": end_date,
        })
        return data or []

    def get_tw_per_pbr_sync(
        self, symbol: str, start_date: str, end_date: str = None
    ) -> List[Dict]:
        """同步：PER/PBR/殖利率"""
        # TaiwanStockPER 在不同帳號下參數容忍度不同，採兩段式重試
        start_date = self._normalize_start_date(start_date, fallback_days=365)
        if end_date is None:
            end_date = datetime.now().strftime("%Y-%m-%d")
        attempts = [
            {
                "dataset": "TaiwanStockPER",
                "data_id": symbol,
                "start_date": start_date,
                "end_date": end_date,
            },
            {
                "dataset": "TaiwanStockPER",
                "data_id": symbol,
                "start_date": start_date,
            },
            {
                "dataset": "TaiwanStockPER",
                "data_id": symbol,
            },
        ]
        for params in attempts:
            data = self._sync_request(params)
            if data:
                return data
        return []

    def get_tw_financial_statements_sync(self, symbol: str, start_date: str) -> List[Dict]:
        """同步：綜合損益表"""
        data = self._sync_request({
            "dataset": "TaiwanStockFinancialStatements",
            "data_id": symbol,
            "start_date": start_date,
        })
        return data or []

    def get_tw_dividend_sync(
        self, symbol: str, start_date: str, end_date: str = None
    ) -> List[Dict]:
        """同步：股利政策"""
        if end_date is None:
            end_date = datetime.now().strftime("%Y-%m-%d")
        data = self._sync_request({
            "dataset": "TaiwanStockDividend",
            "data_id": symbol,
            "start_date": start_date,
            "end_date": end_date,
        })
        return data or []

    def get_tw_stock_info_all_sync(self) -> List[Dict]:
        """同步：全部台股清單 + 產業分類"""
        data = self._sync_request({"dataset": "TaiwanStockInfo"})
        if not data:
            return []
        return [
            {
                "symbol": d.get("stock_id"),
                "name": d.get("stock_name"),
                "industry": d.get("industry_category"),
                "market": "TWSE" if d.get("type") == "twse" else "TPEX",
                "type": d.get("type", "stock"),
            }
            for d in data
        ]

    def search_tw_stocks_sync(self, query: str, limit: int = 20) -> List[Dict]:
        """同步：搜尋台股代號/名稱（從全量 TaiwanStockInfo 篩選）"""
        all_info = self.get_tw_stock_info_all_sync()
        results = []
        query_lower = query.lower()
        for info in all_info:
            sym = (info.get("symbol") or "").lower()
            name = (info.get("name") or "").lower()
            if query_lower in sym or query_lower in name:
                results.append(info)
                if len(results) >= limit:
                    break
        return results

    def get_tw_stock_price_sync(
        self, symbol: str, start_date: str, end_date: str = None
    ) -> List[Dict]:
        """同步版本的 get_tw_stock_price，供非 async 函式呼叫"""
        # 先取 token（會自動切換到有額度的 token）
        token = self._get_token()
        if not token:
            logger.debug("[FinMind] FINMIND_TOKEN 未設定，跳過")
            return []
        limiter = self.rate_limiters[self._active_token_idx]
        if not limiter.can_request():
            remaining = [str(self.rate_limiters[j].remaining) for j in range(len(self._tokens))]
            logger.info(f"[FinMind] 所有 Token 速率限制已滿（剩餘 {'/'.join(remaining)}），跳過")
            return []
        params = {
            "dataset": "TaiwanStockPrice",
            "data_id": symbol,
            "start_date": start_date,
            "token": token,
        }
        if end_date is None:
            end_date = datetime.now().strftime("%Y-%m-%d")
        params["end_date"] = end_date

        try:
            import httpx as _httpx
            with _httpx.Client(timeout=30.0) as client:
                resp = client.get(f"{self.BASE_URL}/data", params=params)
                limiter.record()
                resp.raise_for_status()
                result = resp.json()
                if result.get("status") == 200 and result.get("data"):
                    self._available = True
                    data = result["data"]
                    return [
                        {
                            "symbol": d.get("stock_id", symbol),
                            "date": d.get("date"),
                            "open": float(d.get("open", 0)),
                            "high": float(d.get("max", 0)),
                            "low": float(d.get("min", 0)),
                            "close": float(d.get("close", 0)),
                            "volume": int(d.get("Trading_Volume", 0)),
                            "value": float(d.get("Trading_money", 0)),
                        }
                        for d in data
                    ]
                logger.debug(f"[FinMind] 台股 {symbol} 回傳空資料: status={result.get('status')}")
                return []
        except Exception as e:
            logger.debug(f"[FinMind] 同步請求失敗 ({symbol}): {type(e).__name__}: {e}")
            self._available = False
            return []

    def get_tw_stock_info_sync(self, symbol: str = None) -> List[Dict]:
        """同步版本的 get_tw_stock_info"""
        # 先取 token（會自動切換）
        token = self._get_token()
        if not token:
            return []
        limiter = self.rate_limiters[self._active_token_idx]
        if not limiter.can_request():
            remaining = [str(self.rate_limiters[j].remaining) for j in range(len(self._tokens))]
            logger.info(f"[FinMind] 所有 Token 速率限制已滿（剩餘 {'/'.join(remaining)}），跳過")
            return []
        params = {"dataset": "TaiwanStockInfo", "token": token}
        if symbol:
            params["data_id"] = symbol
        try:
            import httpx as _httpx
            with _httpx.Client(timeout=30.0) as client:
                resp = client.get(f"{self.BASE_URL}/data", params=params)
                self.rate_limiter.record()
                resp.raise_for_status()
                result = resp.json()
                if result.get("status") == 200 and result.get("data"):
                    return [
                        {
                            "symbol": d.get("stock_id"),
                            "name": d.get("stock_name"),
                            "industry": d.get("industry_category"),
                            "market": "TWSE" if d.get("type") == "twse" else "TPEX",
                            "type": d.get("type", "stock"),
                        }
                        for d in result["data"]
                    ]
                return []
        except Exception as e:
            logger.debug(f"[FinMind] 股票資訊同步請求失敗: {type(e).__name__}: {e}")
            return []


    def get_us_stock_price_sync(
        self, symbol: str, start_date: str, end_date: str = None
    ) -> List[Dict]:
        """同步：美股日K"""
        if end_date is None:
            end_date = datetime.now().strftime("%Y-%m-%d")
        data = self._sync_request({
            "dataset": "USStockPrice",
            "data_id": symbol,
            "start_date": start_date,
            "end_date": end_date,
        })
        if not data:
            return []
        return [
            {
                "symbol": d.get("stock_id", symbol),
                "date": d.get("date"),
                "open": float(d.get("Open", d.get("open", 0))),
                "high": float(d.get("High", d.get("high", 0))),
                "low": float(d.get("Low", d.get("low", 0))),
                "close": float(d.get("Close", d.get("close", 0))),
                "volume": int(d.get("Volume", d.get("Trading_Volume", d.get("volume", 0)))),
            }
            for d in data
        ]

    def get_us_stock_info_sync(self, symbol: str = None) -> List[Dict]:
        """同步：美股基本資訊"""
        params = {"dataset": "USStockInfo"}
        if symbol:
            params["data_id"] = symbol
        data = self._sync_request(params)
        return data or []

    # ===== C 區塊：新增高價值 datasets =====

    async def get_tw_market_value(
        self, symbol: str, start_date: str, end_date: str = None
    ) -> List[Dict]:
        """取得台股市值 (TaiwanStockMarketValue)"""
        # TaiwanStockMarketValue 在部分帳號常見 400，採容錯重試
        start_date = self._normalize_start_date(start_date, fallback_days=365)
        if end_date is None:
            end_date = datetime.now().strftime("%Y-%m-%d")
        attempts = [
            {
                "dataset": "TaiwanStockMarketValue",
                "data_id": symbol,
                "start_date": start_date,
                "end_date": end_date,
            },
            {
                "dataset": "TaiwanStockMarketValue",
                "data_id": symbol,
                "start_date": start_date,
            },
            {
                "dataset": "TaiwanStockMarketValue",
                "data_id": symbol,
            },
        ]
        for params in attempts:
            data = await self._request(params)
            if data:
                return data
        return []

    def get_tw_market_snapshot_sync(self, start_date: str, end_date: str = None) -> List[Dict]:
        """同步：取得台股市場快照（不帶 data_id，回傳多檔股票）"""
        if end_date is None:
            end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = self._normalize_start_date(start_date, fallback_days=7)
        data = self._sync_request({
            "dataset": "TaiwanStockPrice",
            "start_date": start_date,
            "end_date": end_date,
        })
        return data or []

    async def get_tw_balance_sheet(
        self, symbol: str, start_date: str
    ) -> List[Dict]:
        """取得台股資產負債表 (TaiwanStockBalanceSheet)"""
        data = await self._request({
            "dataset": "TaiwanStockBalanceSheet",
            "data_id": symbol,
            "start_date": start_date,
        })
        return data or []

    async def get_tw_cash_flow(
        self, symbol: str, start_date: str
    ) -> List[Dict]:
        """取得台股現金流量表 (TaiwanStockCashFlowsStatement)"""
        data = await self._request({
            "dataset": "TaiwanStockCashFlowsStatement",
            "data_id": symbol,
            "start_date": start_date,
        })
        return data or []

    def get_api_usage(self) -> Dict:
        """取得 API 用量統計"""
        return {
            "token_0_remaining": self.rate_limiters[0].remaining,
            "token_1_remaining": self.rate_limiters[1].remaining,
            "active_token": self._active_token_idx,
            "cache_entries": len(_cache),
        }


# 單例
finmind_adapter = FinMindAdapter()
