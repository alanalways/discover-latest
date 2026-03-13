"""
Pionex Adapter — 加密貨幣行情資料
使用 Pionex 公開 REST API（無需 API key）
https://api.pionex.com
"""
import logging
import time
from typing import Dict, List, Optional, Any

import httpx

logger = logging.getLogger(__name__)

# 預設追蹤的主流幣種（USDT 計價）
DEFAULT_CRYPTO_SYMBOLS = [
    "BTC_USDT",
    "ETH_USDT",
    "SOL_USDT",
    "BNB_USDT",
    "XRP_USDT",
    "DOGE_USDT",
    "ADA_USDT",
    "AVAX_USDT",
    "DOT_USDT",
    "MATIC_USDT",
]

# 幣種中文名稱對照
CRYPTO_NAMES = {
    "BTC": "比特幣",
    "ETH": "以太幣",
    "SOL": "Solana",
    "BNB": "幣安幣",
    "XRP": "瑞波幣",
    "DOGE": "狗狗幣",
    "ADA": "Cardano",
    "AVAX": "Avalanche",
    "DOT": "Polkadot",
    "MATIC": "Polygon",
}


class PionexAdapter:
    """Pionex 公開行情 API Adapter"""

    BASE_URL = "https://api.pionex.com"

    # 快取 TTL（秒）
    TICKER_CACHE_TTL = 60       # ticker 60 秒
    KLINE_CACHE_TTL = 120       # K 線 120 秒
    SYMBOLS_CACHE_TTL = 3600    # 交易對清單 1 小時

    # Rate limit 保護：最少間隔秒數
    MIN_REQUEST_INTERVAL = 1.0

    def __init__(self):
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(15.0, connect=5.0),
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
            headers={"User-Agent": "DiscoverLatest/2.0"},
        )
        # 快取
        self._ticker_cache: Optional[Dict[str, Any]] = None
        self._ticker_cache_time: float = 0
        self._kline_cache: Dict[str, Dict[str, Any]] = {}
        self._symbols_cache: Optional[List[Dict]] = None
        self._symbols_cache_time: float = 0
        # Rate limit
        self._last_request_time: float = 0

    async def _request(self, endpoint: str, params: Optional[Dict] = None) -> Optional[Dict]:
        """發送 API 請求，含 rate limit 保護"""
        now = time.time()
        elapsed = now - self._last_request_time
        if elapsed < self.MIN_REQUEST_INTERVAL:
            import asyncio
            await asyncio.sleep(self.MIN_REQUEST_INTERVAL - elapsed)

        url = f"{self.BASE_URL}{endpoint}"
        try:
            self._last_request_time = time.time()
            resp = await self._client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
            if data.get("result"):
                return data.get("data", {})
            else:
                logger.warning("[Pionex] API 回傳失敗: %s", data)
                return None
        except httpx.TimeoutException:
            logger.warning("[Pionex] 請求超時: %s", endpoint)
            return None
        except Exception as e:
            logger.warning("[Pionex] 請求失敗: %s — %s", endpoint, e)
            return None

    async def get_all_tickers(self, force: bool = False) -> List[Dict]:
        """取得所有交易對的 24h ticker"""
        now = time.time()
        if not force and self._ticker_cache and (now - self._ticker_cache_time) < self.TICKER_CACHE_TTL:
            return self._ticker_cache.get("tickers", [])

        data = await self._request("/api/v1/market/tickers")
        if data and "tickers" in data:
            self._ticker_cache = data
            self._ticker_cache_time = time.time()
            return data["tickers"]

        # 快取過期但請求失敗，回傳舊快取
        if self._ticker_cache:
            return self._ticker_cache.get("tickers", [])
        return []

    async def get_top_cryptos(self, force: bool = False) -> List[Dict]:
        """
        取得主流幣即時行情
        回傳格式統一為 Dashboard 可用的結構
        """
        all_tickers = await self.get_all_tickers(force=force)
        if not all_tickers:
            return []

        # 建立 symbol → ticker 的映射
        ticker_map = {t["symbol"]: t for t in all_tickers}

        results = []
        for symbol in DEFAULT_CRYPTO_SYMBOLS:
            ticker = ticker_map.get(symbol)
            if not ticker:
                continue
            item = self._build_ticker_item(ticker)
            if item:
                results.append(item)

        return results

    async def get_top_gainers(self, limit: int = 10, force: bool = False) -> List[Dict]:
        """
        取得 24h 漲幅前 N 名（僅 USDT 計價 + 最低成交額門檻）
        過濾垃圾幣：成交額至少 $100,000 USDT
        """
        all_tickers = await self.get_all_tickers(force=force)
        if not all_tickers:
            return []

        MIN_AMOUNT = 100_000  # 最低成交額門檻（USDT）

        candidates = []
        for ticker in all_tickers:
            symbol = ticker.get("symbol", "")
            # 只看 USDT 計價的現貨
            if not symbol.endswith("_USDT"):
                continue

            open_price = float(ticker.get("open", 0))
            close = float(ticker.get("close", 0))
            amount = float(ticker.get("amount", 0))

            # 過濾無效或低流動性
            if open_price <= 0 or close <= 0 or amount < MIN_AMOUNT:
                continue

            change_pct = (close - open_price) / open_price * 100
            candidates.append((change_pct, ticker))

        # 按漲幅排序（降序）
        candidates.sort(key=lambda x: x[0], reverse=True)

        results = []
        for _, ticker in candidates[:limit]:
            item = self._build_ticker_item(ticker)
            if item:
                results.append(item)

        return results

    def _build_ticker_item(self, ticker: Dict) -> Optional[Dict]:
        """將原始 ticker 轉為統一的前端結構"""
        symbol = ticker.get("symbol", "")
        if not symbol:
            return None

        parts = symbol.split("_")
        base = parts[0] if parts else symbol
        quote = parts[1] if len(parts) > 1 else "USDT"

        close = float(ticker.get("close", 0))
        open_price = float(ticker.get("open", 0))

        change = close - open_price
        change_pct = (change / open_price * 100) if open_price > 0 else 0

        return {
            "symbol": symbol,
            "name": CRYPTO_NAMES.get(base, base),
            "base": base,
            "quote": quote,
            "price": close,
            "price_str": self._format_price(close),
            "open": open_price,
            "high": float(ticker.get("high", 0)),
            "low": float(ticker.get("low", 0)),
            "change": round(change, 4),
            "change_pct": round(change_pct, 2),
            "change_str": f"{'+' if change >= 0 else ''}{change_pct:.2f}%",
            "color": "green" if change >= 0 else "red",
            "volume": float(ticker.get("volume", 0)),
            "amount": float(ticker.get("amount", 0)),
            "count": int(ticker.get("count", 0)),
            "time": int(ticker.get("time", 0)),
        }

    async def get_ticker(self, symbol: str) -> Optional[Dict]:
        """取得單一交易對 ticker"""
        data = await self._request("/api/v1/market/tickers", params={"symbol": symbol})
        if data and "tickers" in data and len(data["tickers"]) > 0:
            return data["tickers"][0]
        return None

    async def get_klines(
        self,
        symbol: str,
        interval: str = "1D",
        limit: int = 100,
    ) -> List[Dict]:
        """
        取得 K 線數據

        interval: 1M, 5M, 15M, 30M, 60M, 4H, 8H, 12H, 1D
        limit: 最大 500
        """
        cache_key = f"{symbol}:{interval}:{limit}"
        now = time.time()

        cached = self._kline_cache.get(cache_key)
        if cached and (now - cached.get("ts", 0)) < self.KLINE_CACHE_TTL:
            return cached.get("data", [])

        data = await self._request("/api/v1/market/klines", params={
            "symbol": symbol,
            "interval": interval,
            "limit": min(limit, 500),
        })

        if data and "klines" in data:
            klines = data["klines"]
            self._kline_cache[cache_key] = {"data": klines, "ts": time.time()}

            # 限制快取大小（最多 50 組 K 線）
            if len(self._kline_cache) > 50:
                oldest_key = min(self._kline_cache, key=lambda k: self._kline_cache[k].get("ts", 0))
                self._kline_cache.pop(oldest_key, None)

            return klines

        # 快取 fallback
        if cached:
            return cached.get("data", [])
        return []

    async def get_symbols(self, force: bool = False) -> List[Dict]:
        """取得所有可交易的交易對"""
        now = time.time()
        if not force and self._symbols_cache and (now - self._symbols_cache_time) < self.SYMBOLS_CACHE_TTL:
            return self._symbols_cache

        data = await self._request("/api/v1/common/symbols")
        if data and "symbols" in data:
            self._symbols_cache = data["symbols"]
            self._symbols_cache_time = time.time()
            return self._symbols_cache

        return self._symbols_cache or []

    def _format_price(self, price: float) -> str:
        """格式化價格顯示"""
        if price >= 10000:
            return f"{price:,.2f}"
        elif price >= 1:
            return f"{price:,.4f}"
        elif price >= 0.01:
            return f"{price:.6f}"
        else:
            return f"{price:.8f}"

    def clear_cache(self):
        """清除所有快取"""
        self._ticker_cache = None
        self._ticker_cache_time = 0
        self._kline_cache.clear()
        self._symbols_cache = None
        self._symbols_cache_time = 0

    async def close(self):
        """關閉連線池"""
        await self._client.aclose()


# 單例
pionex_adapter = PionexAdapter()
