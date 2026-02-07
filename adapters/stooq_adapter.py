"""
Stooq Adapter - 美股歷史資料備援來源
"""
import httpx
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional, List, Dict
from io import StringIO


class StooqAdapter:
    """Stooq 資料 Adapter（美股歷史資料）"""
    
    BASE_URL = "https://stooq.com/q/d/l/"
    
    def __init__(self):
        self.client = httpx.AsyncClient(
            timeout=30.0,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
        )
    
    async def get_stock_history(
        self, 
        symbol: str, 
        start_date: datetime = None,
        end_date: datetime = None
    ) -> List[Dict]:
        """
        取得美股歷史資料
        
        Args:
            symbol: 股票代號（如 AAPL）
            start_date: 開始日期
            end_date: 結束日期
        """
        if start_date is None:
            start_date = datetime.now() - timedelta(days=365)
        if end_date is None:
            end_date = datetime.now()
        
        try:
            # Stooq URL 格式
            params = {
                "s": symbol.lower() + ".us",  # 美股需加 .us 後綴
                "d1": start_date.strftime("%Y%m%d"),
                "d2": end_date.strftime("%Y%m%d"),
                "i": "d"  # 日線
            }
            
            response = await self.client.get(self.BASE_URL, params=params)
            response.raise_for_status()
            
            # 解析 CSV
            csv_data = response.text
            if "No data" in csv_data or len(csv_data) < 50:
                return []
            
            df = pd.read_csv(StringIO(csv_data))
            
            if df.empty:
                return []
            
            # 標準化欄位名
            df.columns = [c.lower() for c in df.columns]
            
            records = []
            for _, row in df.iterrows():
                records.append({
                    "symbol": symbol.upper(),
                    "date": str(row.get("date", "")),
                    "open": float(row.get("open", 0)),
                    "high": float(row.get("high", 0)),
                    "low": float(row.get("low", 0)),
                    "close": float(row.get("close", 0)),
                    "volume": int(row.get("volume", 0))
                })
            
            return records
            
        except Exception as e:
            print(f"[Stooq] 取得 {symbol} 歷史資料失敗: {e}")
            return []
    
    async def get_index_history(
        self,
        index_symbol: str,
        start_date: datetime = None,
        end_date: datetime = None
    ) -> List[Dict]:
        """
        取得指數歷史資料
        
        常用指數:
        - ^DJI: 道瓊工業
        - ^SPX: S&P 500
        - ^NDX: 納斯達克 100
        """
        if start_date is None:
            start_date = datetime.now() - timedelta(days=365)
        if end_date is None:
            end_date = datetime.now()
        
        try:
            # 指數代號轉換
            stooq_symbol = index_symbol.replace("^", "").lower()
            
            params = {
                "s": stooq_symbol,
                "d1": start_date.strftime("%Y%m%d"),
                "d2": end_date.strftime("%Y%m%d"),
                "i": "d"
            }
            
            response = await self.client.get(self.BASE_URL, params=params)
            response.raise_for_status()
            
            csv_data = response.text
            if "No data" in csv_data or len(csv_data) < 50:
                return []
            
            df = pd.read_csv(StringIO(csv_data))
            df.columns = [c.lower() for c in df.columns]
            
            records = []
            for _, row in df.iterrows():
                records.append({
                    "symbol": index_symbol,
                    "date": str(row.get("date", "")),
                    "open": float(row.get("open", 0)),
                    "high": float(row.get("high", 0)),
                    "low": float(row.get("low", 0)),
                    "close": float(row.get("close", 0)),
                    "volume": int(row.get("volume", 0)) if pd.notna(row.get("volume")) else 0
                })
            
            return records
            
        except Exception as e:
            print(f"[Stooq] 取得 {index_symbol} 指數歷史失敗: {e}")
            return []
    
    async def get_etf_history(
        self,
        etf_symbol: str,
        start_date: datetime = None,
        end_date: datetime = None
    ) -> List[Dict]:
        """
        取得 ETF 歷史資料
        
        常用 ETF:
        - SPY, QQQ, IWM, VTI, VOO
        """
        # ETF 與一般股票同樣處理
        return await self.get_stock_history(etf_symbol, start_date, end_date)
    
    async def close(self):
        """關閉連線"""
        await self.client.aclose()


# 單例
stooq_adapter = StooqAdapter()
