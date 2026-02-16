"""
FX Adapter - 匯率資料
"""
import logging
import httpx
from datetime import datetime, timedelta
from typing import Optional, Dict, List
import json



logger = logging.getLogger(__name__)
class FXAdapter:
    """匯率資料 Adapter"""
    
    # 使用免費的 exchangerate-api
    BASE_URL = "https://api.exchangerate-api.com/v4"
    
    # 快取過期時間（秒）
    CACHE_TTL = 3600  # 1 小時
    
    def __init__(self):
        self.client = httpx.AsyncClient(timeout=15.0)
        self._cache: Dict[str, Dict] = {}
        self._cache_time: Dict[str, datetime] = {}
    
    async def get_rate(self, from_currency: str, to_currency: str) -> Optional[float]:
        """
        取得匯率
        
        Args:
            from_currency: 來源貨幣（如 USD）
            to_currency: 目標貨幣（如 TWD）
        
        Returns:
            匯率，如 1 USD = 31.5 TWD，則回傳 31.5
        """
        from_currency = from_currency.upper()
        to_currency = to_currency.upper()
        
        cache_key = from_currency
        
        # 檢查快取
        if cache_key in self._cache:
            cache_time = self._cache_time.get(cache_key)
            if cache_time and (datetime.now() - cache_time).seconds < self.CACHE_TTL:
                rates = self._cache[cache_key]
                return rates.get(to_currency)
        
        try:
            url = f"{self.BASE_URL}/latest/{from_currency}"
            response = await self.client.get(url)
            response.raise_for_status()
            data = response.json()
            
            rates = data.get("rates", {})
            
            # 更新快取
            self._cache[cache_key] = rates
            self._cache_time[cache_key] = datetime.now()
            
            return rates.get(to_currency)
            
        except Exception as e:
            logger.debug(f"[FX] 取得 {from_currency}/{to_currency} 匯率失敗: {e}")
            return None
    
    async def get_usd_twd(self) -> Optional[float]:
        """取得 USD/TWD 匯率"""
        return await self.get_rate("USD", "TWD")
    
    async def convert(
        self, 
        amount: float, 
        from_currency: str, 
        to_currency: str
    ) -> Optional[float]:
        """
        貨幣轉換
        
        Args:
            amount: 金額
            from_currency: 來源貨幣
            to_currency: 目標貨幣
        
        Returns:
            轉換後金額
        """
        rate = await self.get_rate(from_currency, to_currency)
        if rate is None:
            return None
        return amount * rate
    
    async def get_all_rates(self, base_currency: str = "USD") -> Dict[str, float]:
        """取得所有匯率（以指定貨幣為基準）"""
        base_currency = base_currency.upper()
        
        # 檢查快取
        if base_currency in self._cache:
            cache_time = self._cache_time.get(base_currency)
            if cache_time and (datetime.now() - cache_time).seconds < self.CACHE_TTL:
                return self._cache[base_currency]
        
        try:
            url = f"{self.BASE_URL}/latest/{base_currency}"
            response = await self.client.get(url)
            response.raise_for_status()
            data = response.json()
            
            rates = data.get("rates", {})
            
            # 更新快取
            self._cache[base_currency] = rates
            self._cache_time[base_currency] = datetime.now()
            
            return rates
            
        except Exception as e:
            logger.debug(f"[FX] 取得 {base_currency} 所有匯率失敗: {e}")
            return {}
    
    async def get_common_rates(self) -> Dict[str, float]:
        """取得常用匯率（USD 為基準）"""
        all_rates = await self.get_all_rates("USD")
        
        common_currencies = ["TWD", "JPY", "CNY", "EUR", "GBP", "HKD", "KRW"]
        
        return {
            currency: all_rates.get(currency, 0)
            for currency in common_currencies
            if currency in all_rates
        }
    
    def clear_cache(self):
        """清除快取"""
        self._cache.clear()
        self._cache_time.clear()
    
    async def close(self):
        """關閉連線"""
        await self.client.aclose()


# 單例
fx_adapter = FXAdapter()
