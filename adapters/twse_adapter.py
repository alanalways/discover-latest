"""
TWSE Adapter - 台灣證券交易所資料抓取
"""
import logging
import time
import httpx
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
import json



logger = logging.getLogger(__name__)
class TWSEAdapter:
    """台灣證券交易所資料 Adapter（含快取）"""
    
    BASE_URL = "https://www.twse.com.tw"
    _CACHE_TTL = 3600  # 1 hour
    
    def __init__(self):
        self.client = httpx.AsyncClient(
            timeout=30.0,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "application/json"
            }
        )
        self._cache: Dict = {}  # key → (data, timestamp)
    
    def _cache_get(self, key: str):
        """從快取取得資料"""
        if key in self._cache:
            data, ts = self._cache[key]
            if time.time() - ts < self._CACHE_TTL:
                return data
            del self._cache[key]
        return None

    def _cache_set(self, key: str, data):
        """寫入快取"""
        self._cache[key] = (data, time.time())
        # LRU cleanup
        if len(self._cache) > 500:
            oldest = min(self._cache, key=lambda k: self._cache[k][1])
            del self._cache[oldest]

    async def get_daily_quote(self, symbol: str, date: datetime = None) -> Optional[Dict]:
        """取得個股日成交資訊（含快取）"""
        if date is None:
            date = datetime.now()
        
        cache_key = f"twse_daily_{symbol}_{date.strftime('%Y%m%d')}"
        cached = self._cache_get(cache_key)
        if cached:
            return cached

        date_str = date.strftime("%Y%m%d")
        
        try:
            # 個股日成交資訊
            url = f"{self.BASE_URL}/exchangeReport/STOCK_DAY"
            params = {
                "response": "json",
                "date": date_str,
                "stockNo": symbol
            }
            
            response = await self.client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            
            if data.get("stat") != "OK" or not data.get("data"):
                return None
            
            # 取最後一筆資料（最新日期）
            latest = data["data"][-1]
            
            result = {
                "symbol": symbol,
                "date": latest[0],
                "volume": self._parse_number(latest[1]),
                "value": self._parse_number(latest[2]),
                "open": self._parse_price(latest[3]),
                "high": self._parse_price(latest[4]),
                "low": self._parse_price(latest[5]),
                "close": self._parse_price(latest[6]),
                "change": latest[7],
                "transactions": self._parse_number(latest[8]),
            }
            self._cache_set(cache_key, result)
            return result
            
        except Exception as e:
            logger.debug(f"[TWSE] 取得 {symbol} 日成交失敗: {e}")
            return None
    
    async def get_stock_history(
        self, 
        symbol: str, 
        start_date: datetime,
        end_date: datetime = None
    ) -> List[Dict]:
        """
        取得個股歷史資料（逐月抓取）
        
        Args:
            symbol: 股票代號
            start_date: 開始日期
            end_date: 結束日期，預設今日
        """
        if end_date is None:
            end_date = datetime.now()
        
        all_data = []
        current = start_date.replace(day=1)
        
        while current <= end_date:
            date_str = current.strftime("%Y%m%d")
            
            try:
                url = f"{self.BASE_URL}/exchangeReport/STOCK_DAY"
                params = {
                    "response": "json",
                    "date": date_str,
                    "stockNo": symbol
                }
                
                response = await self.client.get(url, params=params)
                response.raise_for_status()
                data = response.json()
                
                if data.get("stat") == "OK" and data.get("data"):
                    for row in data["data"]:
                        all_data.append({
                            "symbol": symbol,
                            "date": self._parse_roc_date(row[0]),
                            "volume": self._parse_number(row[1]),
                            "open": self._parse_price(row[3]),
                            "high": self._parse_price(row[4]),
                            "low": self._parse_price(row[5]),
                            "close": self._parse_price(row[6]),
                            "change": row[7]
                        })
                        
            except Exception as e:
                logger.debug(f"[TWSE] 取得 {symbol} {date_str} 歷史失敗: {e}")
            
            # 下個月
            if current.month == 12:
                current = current.replace(year=current.year + 1, month=1)
            else:
                current = current.replace(month=current.month + 1)
        
        return all_data
    
    async def get_index_daily(self, date: datetime = None) -> Optional[Dict]:
        """取得大盤指數資訊"""
        if date is None:
            date = datetime.now()
        
        date_str = date.strftime("%Y%m%d")
        
        try:
            url = f"{self.BASE_URL}/exchangeReport/FMTQIK"
            params = {"response": "json", "date": date_str}
            
            response = await self.client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            
            if data.get("stat") == "OK" and data.get("data"):
                latest = data["data"][-1]
                return {
                    "date": latest[0],
                    "open": self._parse_price(latest[1]),
                    "high": self._parse_price(latest[2]),
                    "low": self._parse_price(latest[3]),
                    "close": self._parse_price(latest[4])
                }
                
        except Exception as e:
            logger.debug(f"[TWSE] 取得大盤指數失敗: {e}")
        
        return None
    
    async def get_all_stocks_list(self) -> List[Dict]:
        """取得上市公司代號列表"""
        try:
            url = f"{self.BASE_URL}/exchangeReport/STOCK_DAY_ALL"
            params = {"response": "json"}
            
            response = await self.client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            
            stocks = []
            if data.get("data"):
                for row in data["data"]:
                    stocks.append({
                        "symbol": row[0],
                        "name": row[1],
                        "market": "TWSE",
                        "type": "stock"
                    })
            
            return stocks
            
        except Exception as e:
            logger.debug(f"[TWSE] 取得股票列表失敗: {e}")
            return []
    
    def _parse_number(self, value: str) -> int:
        """解析數字（移除逗號）"""
        try:
            return int(value.replace(",", ""))
        except:
            return 0
    
    def _parse_price(self, value: str) -> float:
        """解析價格"""
        try:
            return float(value.replace(",", ""))
        except:
            return 0.0
    
    def _parse_roc_date(self, roc_date: str) -> str:
        """解析民國日期為西元日期（YYYY-MM-DD）"""
        try:
            parts = roc_date.split("/")
            year = int(parts[0]) + 1911
            return f"{year}-{parts[1]}-{parts[2]}"
        except:
            return roc_date
    
    async def close(self):
        """關閉連線"""
        await self.client.aclose()


# 單例
twse_adapter = TWSEAdapter()
