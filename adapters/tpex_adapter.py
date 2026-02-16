"""
TPEX Adapter - 櫃買中心資料抓取
"""
import logging
import httpx
from datetime import datetime
from typing import Optional, List, Dict
import json



logger = logging.getLogger(__name__)
class TPEXAdapter:
    """櫃買中心資料 Adapter"""
    
    BASE_URL = "https://www.tpex.org.tw"
    
    def __init__(self):
        self.client = httpx.AsyncClient(
            timeout=30.0,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "application/json"
            }
        )
    
    async def get_daily_quote(self, symbol: str, date: datetime = None) -> Optional[Dict]:
        """
        取得上櫃個股日成交資訊
        
        Args:
            symbol: 股票代號（如 6547）
            date: 日期，預設今日
        """
        if date is None:
            date = datetime.now()
        
        # TPEX 使用民國年格式
        roc_date = f"{date.year - 1911}/{date.month:02d}/{date.day:02d}"
        
        try:
            url = f"{self.BASE_URL}/web/stock/aftertrading/daily_trading_info/st43_result.php"
            params = {
                "l": "zh-tw",
                "d": roc_date,
                "stkno": symbol
            }
            
            response = await self.client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            
            if not data.get("aaData"):
                return None
            
            # 取最後一筆
            latest = data["aaData"][-1]
            
            return {
                "symbol": symbol,
                "date": latest[0],
                "volume": self._parse_number(latest[1]),
                "value": self._parse_number(latest[2]),
                "open": self._parse_price(latest[3]),
                "high": self._parse_price(latest[4]),
                "low": self._parse_price(latest[5]),
                "close": self._parse_price(latest[6]),
                "change": latest[7],
                "transactions": self._parse_number(latest[8])
            }
            
        except Exception as e:
            logger.debug(f"[TPEX] 取得 {symbol} 日成交失敗: {e}")
            return None
    
    async def get_stock_history(
        self, 
        symbol: str, 
        start_date: datetime,
        end_date: datetime = None
    ) -> List[Dict]:
        """
        取得上櫃股歷史資料（逐月抓取）
        """
        if end_date is None:
            end_date = datetime.now()
        
        all_data = []
        current = start_date.replace(day=1)
        
        while current <= end_date:
            roc_date = f"{current.year - 1911}/{current.month:02d}/01"
            
            try:
                url = f"{self.BASE_URL}/web/stock/aftertrading/daily_trading_info/st43_result.php"
                params = {
                    "l": "zh-tw",
                    "d": roc_date,
                    "stkno": symbol
                }
                
                response = await self.client.get(url, params=params)
                response.raise_for_status()
                data = response.json()
                
                if data.get("aaData"):
                    for row in data["aaData"]:
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
                logger.debug(f"[TPEX] 取得 {symbol} {roc_date} 歷史失敗: {e}")
            
            # 下個月
            if current.month == 12:
                current = current.replace(year=current.year + 1, month=1)
            else:
                current = current.replace(month=current.month + 1)
        
        return all_data
    
    async def get_index_daily(self, date: datetime = None) -> Optional[Dict]:
        """取得櫃買指數資訊"""
        if date is None:
            date = datetime.now()
        
        roc_date = f"{date.year - 1911}/{date.month:02d}/{date.day:02d}"
        
        try:
            url = f"{self.BASE_URL}/web/stock/aftertrading/daily_close_quotes/stk_quote_result.php"
            params = {"l": "zh-tw", "d": roc_date}
            
            response = await self.client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            
            if data.get("mmData"):
                index_data = data["mmData"]
                return {
                    "date": roc_date,
                    "close": self._parse_price(index_data.get("代號指數", "0")),
                    "change": index_data.get("漲跌", "0")
                }
                
        except Exception as e:
            logger.debug(f"[TPEX] 取得櫃買指數失敗: {e}")
        
        return None
    
    async def get_all_stocks_list(self) -> List[Dict]:
        """取得上櫃公司代號列表"""
        try:
            url = f"{self.BASE_URL}/web/stock/aftertrading/otc_quotes_no1430/stk_wn1430_result.php"
            params = {"l": "zh-tw"}
            
            response = await self.client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            
            stocks = []
            if data.get("aaData"):
                for row in data["aaData"]:
                    stocks.append({
                        "symbol": row[0],
                        "name": row[1],
                        "market": "TPEX",
                        "type": "stock"
                    })
            
            return stocks
            
        except Exception as e:
            logger.debug(f"[TPEX] 取得股票列表失敗: {e}")
            return []
    
    def _parse_number(self, value: str) -> int:
        """解析數字"""
        try:
            return int(str(value).replace(",", ""))
        except:
            return 0
    
    def _parse_price(self, value: str) -> float:
        """解析價格"""
        try:
            return float(str(value).replace(",", ""))
        except:
            return 0.0
    
    def _parse_roc_date(self, roc_date: str) -> str:
        """解析民國日期為西元日期"""
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
tpex_adapter = TPEXAdapter()
