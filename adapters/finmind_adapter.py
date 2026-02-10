"""
FinMind Adapter - 主要資料來源 (台股 + 美股)
https://finmindtrade.com/
免費版限制: 600 requests / hour
"""
import os
import httpx
import time
import threading
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
import asyncio


class _FinMindRateLimiter:
    """FinMind API 速率限制器 (600 req/hr for free tier)"""
    def __init__(self, max_requests: int = 550, window_seconds: int = 3600):
        self.max_requests = max_requests  # 留 50 buffer
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


# 台股資訊快取（避免重複呼叫 TaiwanStockInfo）
_stock_info_cache: Dict[str, Any] = {"data": None, "ts": 0}
_STOCK_INFO_CACHE_TTL = 600  # 10 min


class FinMindAdapter:
    """FinMind 資料 Adapter（台股 + 美股主要來源）"""

    BASE_URL = "https://api.finmindtrade.com/api/v4"

    def __init__(self):
        self._token: Optional[str] = None
        self._available = True
        self._last_check: Optional[datetime] = None
        self.rate_limiter = _FinMindRateLimiter()

    def _get_token(self) -> str:
        """取得 FinMind API Token"""
        if not self._token:
            self._token = os.environ.get("FINMIND_TOKEN", "")
        return self._token

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

    async def _request(self, params: Dict) -> Optional[List[Dict]]:
        """發送 API 請求（含速率限制）"""
        if not self.rate_limiter.can_request():
            print(f"[FinMind] 速率限制 — 剩餘 {self.rate_limiter.remaining} req/hr，跳過")
            return None
        params["token"] = self._get_token()
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(f"{self.BASE_URL}/data", params=params)
                self.rate_limiter.record()
                resp.raise_for_status()
                result = resp.json()
                if result.get("status") == 200 and result.get("data"):
                    self._available = True
                    return result["data"]
                return None
        except Exception as e:
            print(f"[FinMind] 請求失敗: {type(e).__name__}: {e}")
            self._available = False
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
        if end_date is None:
            end_date = datetime.now().strftime("%Y-%m-%d")
        data = await self._request({
            "dataset": "TaiwanStockPER",
            "data_id": symbol,
            "start_date": start_date,
            "end_date": end_date,
        })
        return data or []

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
                "open": float(d.get("Open", 0)),
                "high": float(d.get("High", 0)),
                "low": float(d.get("Low", 0)),
                "close": float(d.get("Close", 0)),
                "volume": int(d.get("Volume", 0)),
                "adj_close": float(d.get("Adj_Close", 0)),
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
        """同步 API 請求（含速率限制）"""
        if not self.rate_limiter.can_request():
            print(f"[FinMind] 速率限制 — 剩餘 {self.rate_limiter.remaining} req/hr，跳過")
            return None
        params["token"] = self._get_token()
        if not params["token"]:
            return None
        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.get(f"{self.BASE_URL}/data", params=params)
                self.rate_limiter.record()
                resp.raise_for_status()
                result = resp.json()
                if result.get("status") == 200 and result.get("data"):
                    return result["data"]
                return None
        except Exception as e:
            print(f"[FinMind] 同步請求失敗: {type(e).__name__}: {e}")
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
        if end_date is None:
            end_date = datetime.now().strftime("%Y-%m-%d")
        data = self._sync_request({
            "dataset": "TaiwanStockPER",
            "data_id": symbol,
            "start_date": start_date,
            "end_date": end_date,
        })
        return data or []

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
        if not self.rate_limiter.can_request():
            print(f"[FinMind] 速率限制 — 剩餘 {self.rate_limiter.remaining} req/hr，跳過")
            return []
        token = self._get_token()
        if not token:
            print("[FinMind] FINMIND_TOKEN 未設定，跳過")
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
                self.rate_limiter.record()
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
                print(f"[FinMind] 台股 {symbol} 回傳空資料: status={result.get('status')}")
                return []
        except Exception as e:
            print(f"[FinMind] 同步請求失敗 ({symbol}): {type(e).__name__}: {e}")
            self._available = False
            return []

    def get_tw_stock_info_sync(self, symbol: str = None) -> List[Dict]:
        """同步版本的 get_tw_stock_info"""
        if not self.rate_limiter.can_request():
            print(f"[FinMind] 速率限制 — 剩餘 {self.rate_limiter.remaining} req/hr，跳過")
            return []
        token = self._get_token()
        if not token:
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
            print(f"[FinMind] 股票資訊同步請求失敗: {type(e).__name__}: {e}")
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
                "open": float(d.get("Open", 0)),
                "high": float(d.get("High", 0)),
                "low": float(d.get("Low", 0)),
                "close": float(d.get("Close", 0)),
                "volume": int(d.get("Volume", 0)),
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


# 單例
finmind_adapter = FinMindAdapter()
