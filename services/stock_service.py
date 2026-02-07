"""
Stock Service - 股票資料服務層
整合各資料來源，提供統一的資料存取介面
"""
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
import asyncio

from adapters import (
    supabase, twse_adapter, tpex_adapter, 
    yahoo_adapter, stooq_adapter, fx_adapter,
    finmind_adapter
)


class StockService:
    """股票資料服務"""
    
    # 市場代號
    MARKETS = {
        "TWSE": {"name": "台灣證券交易所", "currency": "TWD"},
        "TPEX": {"name": "櫃買中心", "currency": "TWD"},
        "US": {"name": "美國股市", "currency": "USD"},
    }
    
    async def get_stock_data(
        self, 
        symbol: str, 
        market: str = None,
        period: str = "1y"
    ) -> Dict[str, Any]:
        """
        取得完整股票資料（基本資訊 + 歷史資料）
        
        Args:
            symbol: 股票代號
            market: 市場（TWSE/TPEX/US），若 None 則自動判斷
            period: 歷史資料期間
        """
        if market is None:
            market = await self._detect_market(symbol)
        
        # 並行取得資訊與歷史
        info_task = self._get_stock_info(symbol, market)
        history_task = self._get_stock_history(symbol, market, period)
        
        info, history = await asyncio.gather(info_task, history_task)
        
        return {
            "symbol": symbol,
            "market": market,
            "info": info,
            "history": history,
            "updated_at": datetime.now().isoformat()
        }
    
    async def _detect_market(self, symbol: str) -> str:
        """自動偵測市場"""
        # 台股代號通常是 4-6 位數字
        if symbol.isdigit() and 4 <= len(symbol) <= 6:
            # 先嘗試查詢是否在資料庫有記錄
            try:
                result = await supabase.get_client().from_("symbol_index").select("market").eq("symbol", symbol).limit(1).execute()
                if result.data:
                    return result.data[0]["market"]
            except:
                pass
            
            # 預設台股
            return "TWSE"
        
        return "US"
    
    async def _get_stock_info(self, symbol: str, market: str) -> Optional[Dict]:
        """取得股票基本資訊"""
        if market in ["TWSE", "TPEX"]:
            # 台股使用 Yahoo 取得基本資訊
            return await yahoo_adapter.get_stock_info(symbol, market)
        else:
            return await yahoo_adapter.get_stock_info(symbol, "US")
    
    async def _get_stock_history(
        self, 
        symbol: str, 
        market: str,
        period: str = "1y"
    ) -> List[Dict]:
        """取得歷史資料（優先 FinMind → DB → TWSE/TPEX/Yahoo）"""
        end_date = datetime.now()
        period_days = {"1mo": 30, "3mo": 90, "6mo": 180, "1y": 365, "2y": 730, "5y": 1825}
        start_date = end_date - timedelta(days=period_days.get(period, 365))

        # 台股優先使用 FinMind
        if market in ["TWSE", "TPEX"]:
            try:
                fm_data = await finmind_adapter.get_tw_stock_price(
                    symbol, start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")
                )
                if fm_data:
                    print(f"[DataSource] FinMind OK: {symbol} ({len(fm_data)} rows)")
                    return fm_data
                else:
                    print(f"[DataSource] FinMind 回傳空資料: {symbol}")
            except Exception as e:
                print(f"[DataSource] FinMind failed ({symbol}): {e}")

        # Fallback: 嘗試從資料庫取得
        try:
            result = await supabase.get_client().from_("stock_daily").select("*").eq("symbol", symbol).gte("date", start_date.strftime("%Y-%m-%d")).order("date", desc=False).execute()
            
            if result.data and len(result.data) > 0:
                print(f"[DataSource] Supabase DB OK: {symbol}")
                return result.data
        except:
            pass
        
        # Fallback: 從其他 API 取得
        if market == "TWSE":
            print(f"[DataSource] fallback TWSE adapter: {symbol}")
            return await twse_adapter.get_stock_history(symbol, end_date - timedelta(days=365), end_date)
        elif market == "TPEX":
            print(f"[DataSource] fallback TPEX adapter: {symbol}")
            return await tpex_adapter.get_stock_history(symbol, end_date - timedelta(days=365), end_date)
        else:
            return await yahoo_adapter.get_stock_history(symbol, "US", period)
    
    async def search_symbols(self, query: str, limit: int = 20) -> List[Dict]:
        """
        搜尋股票代號
        
        優先從本地 symbol_index 搜尋，沒有結果再從 API 搜尋
        """
        results = []
        
        # 從資料庫搜尋
        try:
            db_result = await supabase.get_client().from_("symbol_index").select("*").or_(f"symbol.ilike.%{query}%,name.ilike.%{query}%").limit(limit).execute()
            
            if db_result.data:
                results.extend(db_result.data)
        except Exception as e:
            print(f"[StockService] 資料庫搜尋失敗: {e}")
        
        # 如果結果不夠，從 Yahoo 補充
        if len(results) < limit:
            try:
                yahoo_results = await yahoo_adapter.search_symbols(query, limit - len(results))
                results.extend(yahoo_results)
            except:
                pass
        
        return results[:limit]
    
    async def get_market_indices(self) -> Dict[str, List[Dict]]:
        """取得市場指數"""
        indices = {
            "TW": [
                {"symbol": "^TWII", "name": "加權指數"},
                {"symbol": "^TWOII", "name": "櫃買指數"},
            ],
            "US": [
                {"symbol": "^DJI", "name": "道瓊工業"},
                {"symbol": "^GSPC", "name": "S&P 500"},
                {"symbol": "^IXIC", "name": "納斯達克"},
            ]
        }
        
        results = {"TW": [], "US": []}
        
        for market, index_list in indices.items():
            for index in index_list:
                try:
                    quote = await yahoo_adapter.get_realtime_quote(index["symbol"], "US")
                    if quote:
                        results[market].append({
                            **index,
                            "price": quote.get("price"),
                            "change": quote.get("change"),
                            "change_percent": quote.get("change_percent")
                        })
                except:
                    results[market].append(index)
        
        return results
    
    async def get_popular_etfs(self) -> List[Dict]:
        """取得熱門 ETF"""
        etfs = [
            {"symbol": "0050", "name": "台灣50", "market": "TWSE"},
            {"symbol": "0056", "name": "高股息", "market": "TWSE"},
            {"symbol": "00878", "name": "國泰永續高股息", "market": "TWSE"},
            {"symbol": "00929", "name": "復華台灣科技優息", "market": "TWSE"},
            {"symbol": "SPY", "name": "S&P 500 ETF", "market": "US"},
            {"symbol": "QQQ", "name": "Nasdaq 100 ETF", "market": "US"},
        ]
        
        results = []
        for etf in etfs:
            try:
                quote = await yahoo_adapter.get_realtime_quote(etf["symbol"], etf["market"])
                if quote:
                    results.append({
                        **etf,
                        "price": quote.get("price"),
                        "change": quote.get("change"),
                        "change_percent": quote.get("change_percent")
                    })
                else:
                    results.append(etf)
            except:
                results.append(etf)
        
        return results
    
    async def batch_update_stock_data(
        self, 
        symbols: List[str] = None,
        market: str = "TWSE"
    ) -> Dict[str, int]:
        """
        批次更新股票資料到 Supabase
        
        Args:
            symbols: 股票代號列表，None 則更新全部
            market: 市場
        
        Returns:
            {"success": n, "failed": m}
        """
        if symbols is None:
            # 取得全部代號
            if market == "TWSE":
                stocks = await twse_adapter.get_all_stocks_list()
            elif market == "TPEX":
                stocks = await tpex_adapter.get_all_stocks_list()
            else:
                stocks = []
            symbols = [s["symbol"] for s in stocks]
        
        success = 0
        failed = 0
        
        for symbol in symbols:
            try:
                # 取得最新資料
                if market == "TWSE":
                    quote = await twse_adapter.get_daily_quote(symbol)
                elif market == "TPEX":
                    quote = await tpex_adapter.get_daily_quote(symbol)
                else:
                    quote = await yahoo_adapter.get_realtime_quote(symbol, market)
                
                if quote:
                    # 寫入資料庫
                    await supabase.upsert_stock_data(symbol, quote)
                    success += 1
                else:
                    failed += 1
                    
            except Exception as e:
                print(f"[StockService] 更新 {symbol} 失敗: {e}")
                failed += 1
            
            # 控制請求頻率
            await asyncio.sleep(0.1)
        
        return {"success": success, "failed": failed}
    
    async def update_symbol_index(self, market: str = "TWSE") -> int:
        """
        更新代號索引表
        
        Returns:
            新增/更新的代號數量
        """
        if market == "TWSE":
            stocks = await twse_adapter.get_all_stocks_list()
        elif market == "TPEX":
            stocks = await tpex_adapter.get_all_stocks_list()
        else:
            return 0
        
        count = 0
        for stock in stocks:
            try:
                await supabase.get_client().from_("symbol_index").upsert({
                    "symbol": stock["symbol"],
                    "name": stock["name"],
                    "market": market,
                    "type": stock.get("type", "stock"),
                    "updated_at": datetime.now().isoformat()
                }).execute()
                count += 1
            except Exception as e:
                print(f"[StockService] 更新代號索引 {stock['symbol']} 失敗: {e}")
        
        return count
    
    async def get_fx_rate(self, from_currency: str = "USD", to_currency: str = "TWD") -> float:
        """取得匯率"""
        rate = await fx_adapter.get_rate(from_currency, to_currency)
        return rate or 0.0


# 單例
stock_service = StockService()
