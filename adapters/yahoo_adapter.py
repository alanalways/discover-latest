"""
Yahoo Finance Adapter - 使用 yfinance 封裝
"""
import logging
import yfinance as yf
from datetime import datetime
from typing import Optional, List, Dict
import asyncio
from concurrent.futures import ThreadPoolExecutor



logger = logging.getLogger(__name__)
class YahooAdapter:
    """Yahoo Finance 資料 Adapter"""
    
    def __init__(self):
        self.executor = ThreadPoolExecutor(max_workers=4)
    
    def _get_symbol_suffix(self, symbol: str, market: str = "US") -> str:
        """
        取得 Yahoo Finance 代號格式
        
        台股: 2330.TW (上市), 6547.TWO (上櫃)
        美股: AAPL (無後綴)
        """
        if market == "TWSE":
            return f"{symbol}.TW"
        elif market == "TPEX":
            return f"{symbol}.TWO"
        else:
            return symbol
    
    async def get_stock_info(self, symbol: str, market: str = "US") -> Optional[Dict]:
        """
        取得股票基本資訊
        
        Args:
            symbol: 股票代號
            market: 市場（US/TWSE/TPEX）
        """
        yf_symbol = self._get_symbol_suffix(symbol, market)
        
        def _fetch():
            try:
                ticker = yf.Ticker(yf_symbol)
                info = ticker.info
                
                return {
                    "symbol": symbol,
                    "name": info.get("longName") or info.get("shortName", ""),
                    "sector": info.get("sector", ""),
                    "industry": info.get("industry", ""),
                    "market_cap": info.get("marketCap", 0),
                    "pe_ratio": info.get("forwardPE") or info.get("trailingPE"),
                    "pb_ratio": info.get("priceToBook"),
                    "dividend_yield": info.get("dividendYield"),
                    "eps": info.get("trailingEps"),
                    "beta": info.get("beta"),
                    "52_week_high": info.get("fiftyTwoWeekHigh"),
                    "52_week_low": info.get("fiftyTwoWeekLow"),
                    "avg_volume": info.get("averageVolume"),
                    "currency": info.get("currency", "USD"),
                    "exchange": info.get("exchange", "")
                }
            except Exception as e:
                logger.debug(f"[Yahoo] 取得 {yf_symbol} 基本資訊失敗: {e}")
                return None
        
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self.executor, _fetch)
    
    async def get_stock_history(
        self, 
        symbol: str, 
        market: str = "US",
        period: str = "1y",
        interval: str = "1d"
    ) -> List[Dict]:
        """
        取得股票歷史資料
        
        Args:
            symbol: 股票代號
            market: 市場
            period: 期間（1d/5d/1mo/3mo/6mo/1y/2y/5y/10y/ytd/max）
            interval: 間隔（1m/2m/5m/15m/30m/60m/90m/1h/1d/5d/1wk/1mo/3mo）
        """
        yf_symbol = self._get_symbol_suffix(symbol, market)
        
        def _fetch():
            try:
                ticker = yf.Ticker(yf_symbol)
                df = ticker.history(period=period, interval=interval)
                
                if df.empty:
                    return []
                
                # 轉換為 dict 列表
                records = []
                for date, row in df.iterrows():
                    records.append({
                        "symbol": symbol,
                        "date": date.strftime("%Y-%m-%d"),
                        "open": round(row["Open"], 4),
                        "high": round(row["High"], 4),
                        "low": round(row["Low"], 4),
                        "close": round(row["Close"], 4),
                        "volume": int(row["Volume"]),
                        "adj_close": round(row.get("Adj Close", row["Close"]), 4)
                    })
                
                return records
                
            except Exception as e:
                logger.debug(f"[Yahoo] 取得 {yf_symbol} 歷史資料失敗: {e}")
                return []
        
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self.executor, _fetch)
    
    async def get_stock_history_by_date(
        self,
        symbol: str,
        start_date: datetime,
        end_date: datetime = None,
        market: str = "US"
    ) -> List[Dict]:
        """
        依日期範圍取得歷史資料
        """
        if end_date is None:
            end_date = datetime.now()
        
        yf_symbol = self._get_symbol_suffix(symbol, market)
        
        def _fetch():
            try:
                ticker = yf.Ticker(yf_symbol)
                df = ticker.history(start=start_date, end=end_date)
                
                if df.empty:
                    return []
                
                records = []
                for date, row in df.iterrows():
                    records.append({
                        "symbol": symbol,
                        "date": date.strftime("%Y-%m-%d"),
                        "open": round(row["Open"], 4),
                        "high": round(row["High"], 4),
                        "low": round(row["Low"], 4),
                        "close": round(row["Close"], 4),
                        "volume": int(row["Volume"]),
                        "adj_close": round(row.get("Adj Close", row["Close"]), 4)
                    })
                
                return records
                
            except Exception as e:
                logger.debug(f"[Yahoo] 取得 {yf_symbol} 日期範圍歷史失敗: {e}")
                return []
        
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self.executor, _fetch)
    
    async def get_realtime_quote(self, symbol: str, market: str = "US") -> Optional[Dict]:
        """取得即時報價（盤中）"""
        yf_symbol = self._get_symbol_suffix(symbol, market)
        
        def _fetch():
            try:
                ticker = yf.Ticker(yf_symbol)
                info = ticker.info
                
                return {
                    "symbol": symbol,
                    "price": info.get("currentPrice") or info.get("regularMarketPrice"),
                    "open": info.get("regularMarketOpen"),
                    "high": info.get("regularMarketDayHigh"),
                    "low": info.get("regularMarketDayLow"),
                    "volume": info.get("regularMarketVolume"),
                    "previous_close": info.get("regularMarketPreviousClose"),
                    "change": info.get("regularMarketChange"),
                    "change_percent": info.get("regularMarketChangePercent"),
                    "market_state": info.get("marketState", "CLOSED")
                }
                
            except Exception as e:
                logger.debug(f"[Yahoo] 取得 {yf_symbol} 即時報價失敗: {e}")
                return None
        
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self.executor, _fetch)
    
    async def search_symbols(self, query: str, limit: int = 10) -> List[Dict]:
        """搜尋股票代號"""
        def _search():
            try:
                # yfinance 沒有原生搜尋，這裡是簡易實作
                # 實際可考慮使用其他 API
                results = []
                
                # 嘗試直接查詢
                ticker = yf.Ticker(query)
                info = ticker.info
                
                if info.get("symbol"):
                    results.append({
                        "symbol": info["symbol"],
                        "name": info.get("longName") or info.get("shortName", ""),
                        "exchange": info.get("exchange", ""),
                        "type": info.get("quoteType", "")
                    })
                
                return results[:limit]
                
            except Exception:
                return []
        
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self.executor, _search)
    
    def close(self):
        """關閉執行緒池"""
        self.executor.shutdown(wait=False)


# 單例
yahoo_adapter = YahooAdapter()
