"""
Stock Service - 股票資料服務層
整合各資料來源，提供統一的資料存取介面
"""
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
import asyncio

from adapters import (
    supabase, fx_adapter,
    finmind_adapter, ndc_adapter
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
        
        # 建立並行任務
        tasks = [
            self._get_stock_info(symbol, market),
            self._get_stock_history(symbol, market, period),
        ]

        # 台股額外取得：本益比/股淨比、市值、法人籌碼
        if market in ["TWSE", "TPEX"]:
            start_1y = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
            tasks.append(finmind_adapter.get_tw_per_pbr(symbol, start_date=start_1y))  # Task 2
            tasks.append(finmind_adapter.get_tw_market_value(symbol, start_date=start_1y)) # Task 3
        
        results = await asyncio.gather(*tasks)
        
        info = results[0]
        history = results[1]
        
        # 處理台股額外資料
        per_pbr = []
        market_value_data = []
        if len(results) > 2:
            per_pbr = results[2]
            market_value_data = results[3]

        # 計算 52 週高低點 (若 history 足夠)
        high_52w = None
        low_52w = None
        if history and len(history) > 0:
            # 確保 history 有 sort
            # 轉換為 Lightweight Charts 格式 (增加 time 欄位)
            for h in history:
                h["time"] = h.get("date")  # Alias date -> time
            
            # 取最近 250 筆計算 52w
            recent_250 = history[-250:]
            try:
                high_52w = max(d.get("high", 0) for d in recent_250)
                low_52w = min(d.get("low", 0) for d in recent_250)
            except:
                pass
        
        # 整合最新數值到 info
        if info:
            if high_52w: info["high_52w"] = high_52w
            if low_52w: info["low_52w"] = low_52w
            
            # 整合 PER/PBR
            if per_pbr:
                latest_per = per_pbr[-1]
                info["pe_ratio"] = latest_per.get("PER")
                info["pb_ratio"] = latest_per.get("PBR")
                info["dividend_yield"] = latest_per.get("dividend_yield")
            
            # 整合市值
            if market_value_data:
                latest_mv = market_value_data[-1]
                info["market_cap"] = latest_mv.get("Market_Value")

        return {
            "symbol": symbol,
            "market": market,
            "info": info,
            "history": history,
            "updated_at": datetime.now().isoformat()
        }

    async def get_stock_history(
        self,
        symbol: str,
        period: str = "1y",
        market: str = None,
    ) -> List[Dict]:
        """公開方法：取得歷史資料（供 routes 使用）"""
        if market is None:
            market = await self._detect_market(symbol)
        return await self._get_stock_history(symbol, market, period)

    async def get_stock_data_for_analysis(
        self,
        symbol: str,
        period: str = "1y",
    ) -> Dict[str, Any]:
        """公開方法：提供 AI 分析使用的股票資料"""
        return await self.get_stock_data(symbol=symbol, period=period)
    
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
        """取得股票基本資訊（僅使用 FinMind，失敗時回傳最小資訊）"""
        if market in ["TWSE", "TPEX"]:
            try:
                fm_list = await finmind_adapter.get_tw_stock_info(symbol)
                if fm_list:
                    info = fm_list[0]
                    print(f"[StockInfo] FinMind OK: {symbol}")
                    return {
                        "symbol": info.get("symbol"),
                        "name": info.get("name"),
                        "industry": info.get("industry"),
                        "market": market,
                            "type": info.get("type", "stock"),
                    }
            except Exception as e:
                print(f"[StockInfo] FinMind 失敗 ({symbol}): {e}")
            return {
                "symbol": symbol,
                "name": symbol,
                "industry": "",
                "market": market,
                "type": "stock",
            }

        # 美股：走 FinMind USStockInfo，同步包裝成 async
        try:
            us_info = await asyncio.to_thread(finmind_adapter.get_us_stock_info_sync, symbol)
            if us_info:
                info = us_info[0]
                return {
                    "symbol": info.get("stock_id") or symbol,
                    "name": info.get("stock_name") or symbol,
                    "industry": info.get("industry") or "",
                    "market": "US",
                    "type": "stock",
                }
        except Exception as e:
            print(f"[StockInfo] FinMind US 失敗 ({symbol}): {e}")
        return {
            "symbol": symbol,
            "name": symbol,
            "industry": "",
            "market": "US",
            "type": "stock",
        }
    
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
        
        # 不再使用其他外部來源（維持 FinMind-only）
        return []
    
    async def search_symbols(self, query: str, limit: int = 20) -> List[Dict]:
        """搜尋股票代號（台股先 FinMind，再 DB，再 Yahoo）"""
        query_stripped = (query or "").strip()
        if not query_stripped:
            return []
        results = []

        # 台股：先嘗試 FinMind 搜尋
        try:
            fm_results = await finmind_adapter.search_tw_stocks(query_stripped, limit)
            if fm_results:
                for r in fm_results:
                    results.append({
                        "symbol": r.get("symbol"),
                        "name": r.get("name"),
                        "market": r.get("market", "TWSE"),
                        "type": r.get("type", "stock"),
                    })
                if len(results) >= limit:
                    return results[:limit]
        except Exception as e:
            print(f"[StockService] FinMind 搜尋失敗: {e}")

        # 從資料庫補充
        try:
            db_result = await supabase.get_client().from_("symbol_index").select("*").or_(f"symbol.ilike.%{query_stripped}%,name.ilike.%{query_stripped}%").limit(limit - len(results)).execute()
            if db_result.data:
                existing = {r["symbol"] for r in results}
                for d in db_result.data:
                    if d.get("symbol") not in existing:
                        results.append(d)
        except Exception as e:
            print(f"[StockService] DB 搜尋失敗: {e}")

        return results[:limit]

    async def get_stock_fundamentals(self, symbol: str, market: str = None) -> Dict:
        """取得基本面資料（PER/PBR/月營收/損益表）- 台股限定"""
        if market is None:
            market = await self._detect_market(symbol)
        if market not in ["TWSE", "TPEX"]:
            return {}
        from datetime import datetime, timedelta
        start_1y = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
        start_3y = (datetime.now() - timedelta(days=1095)).strftime("%Y-%m-%d")
        result = {}
        try:
            per_data = await finmind_adapter.get_tw_per_pbr(symbol, start_1y)
            result["per_pbr"] = per_data[-30:] if per_data else []
        except Exception as e:
            print(f"[Fundamentals] PER/PBR 失敗 ({symbol}): {e}")
            result["per_pbr"] = []
        try:
            rev_data = await finmind_adapter.get_tw_revenue(symbol, start_3y)
            result["revenue"] = rev_data if rev_data else []
        except Exception as e:
            print(f"[Fundamentals] 月營收失敗 ({symbol}): {e}")
            result["revenue"] = []
        try:
            fin_data = await finmind_adapter.get_tw_financial_statements(symbol, start_3y)
            result["financials"] = fin_data if fin_data else []
        except Exception as e:
            print(f"[Fundamentals] 損益表失敗 ({symbol}): {e}")
            result["financials"] = []
        try:
            div_data = await finmind_adapter.get_tw_dividend(symbol, start_3y)
            result["dividend"] = div_data if div_data else []
        except Exception as e:
            print(f"[Fundamentals] 股利失敗 ({symbol}): {e}")
            result["dividend"] = []
        return result

    async def get_stock_chips(self, symbol: str, market: str = None) -> Dict:
        """取得籌碼面資料（三大法人 + 融資融券）- 台股限定"""
        if market is None:
            market = await self._detect_market(symbol)
        if market not in ["TWSE", "TPEX"]:
            return {}
        from datetime import datetime, timedelta
        start_3m = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
        result = {}
        try:
            inst_data = await finmind_adapter.get_tw_institutional(symbol, start_3m)
            result["institutional"] = inst_data if inst_data else []
        except Exception as e:
            print(f"[Chips] 法人買賣超失敗 ({symbol}): {e}")
            result["institutional"] = []
        try:
            margin_data = await finmind_adapter.get_tw_margin(symbol, start_3m)
            result["margin"] = margin_data if margin_data else []
        except Exception as e:
            print(f"[Chips] 融資融券失敗 ({symbol}): {e}")
            result["margin"] = []
        return result
    
    async def get_market_indices(self) -> Dict[str, List[Dict]]:
        """取得市場指數（FinMind proxy）"""
        proxies = {
            "TW": [
                {"symbol": "TAIEX", "name": "加權指數", "proxy": "0050", "market": "TW"},
            ],
            "US": [
                {"symbol": "DJI", "name": "道瓊工業", "proxy": "DIA", "market": "US"},
                {"symbol": "SPX", "name": "S&P 500", "proxy": "SPY", "market": "US"},
                {"symbol": "IXIC", "name": "納斯達克", "proxy": "QQQ", "market": "US"},
            ],
        }
        results = {"TW": [], "US": []}
        start = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        end = datetime.now().strftime("%Y-%m-%d")

        for market, items in proxies.items():
            for item in items:
                try:
                    if item["market"] == "TW":
                        rows = await asyncio.to_thread(finmind_adapter.get_tw_stock_price_sync, item["proxy"], start, end)
                    else:
                        rows = await asyncio.to_thread(finmind_adapter.get_us_stock_price_sync, item["proxy"], start, end)
                    if rows and len(rows) >= 2:
                        last_row = rows[-1]
                        prev_row = rows[-2]
                        price = float(last_row.get("close", 0))
                        prev = float(prev_row.get("close", 0))
                        change = price - prev
                        change_pct = (change / prev * 100) if prev else 0.0
                        results[market].append({
                            "symbol": item["symbol"],
                            "name": item["name"],
                            "price": price,
                            "change": change,
                            "change_percent": change_pct,
                        })
                        continue
                except Exception:
                    pass
                results[market].append({"symbol": item["symbol"], "name": item["name"]})

        return results
    
    async def get_popular_etfs(self) -> List[Dict]:
        """取得熱門 ETF（FinMind only）"""
        etfs = [
            {"symbol": "0050", "name": "台灣50", "market": "TWSE"},
            {"symbol": "0056", "name": "高股息", "market": "TWSE"},
            {"symbol": "00878", "name": "國泰永續高股息", "market": "TWSE"},
            {"symbol": "00929", "name": "復華台灣科技優息", "market": "TWSE"},
            {"symbol": "SPY", "name": "S&P 500 ETF", "market": "US"},
            {"symbol": "QQQ", "name": "Nasdaq 100 ETF", "market": "US"},
        ]
        
        results = []
        start = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        end = datetime.now().strftime("%Y-%m-%d")
        for etf in etfs:
            try:
                if etf["market"] == "US":
                    rows = await asyncio.to_thread(finmind_adapter.get_us_stock_price_sync, etf["symbol"], start, end)
                else:
                    rows = await asyncio.to_thread(finmind_adapter.get_tw_stock_price_sync, etf["symbol"], start, end)
                if rows and len(rows) >= 2:
                    last_row = rows[-1]
                    prev_row = rows[-2]
                    price = float(last_row.get("close", 0))
                    prev = float(prev_row.get("close", 0))
                    change = price - prev
                    change_percent = (change / prev * 100) if prev else 0.0
                    results.append({
                        **etf,
                        "price": price,
                        "change": change,
                        "change_percent": change_percent,
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
            stocks = await asyncio.to_thread(finmind_adapter.get_tw_stock_info_all_sync)
            if market == "TWSE":
                stocks = [s for s in stocks if s.get("market") == "TWSE"]
            elif market == "TPEX":
                stocks = [s for s in stocks if s.get("market") == "TPEX"]
            else:
                stocks = []
            symbols = [s.get("symbol") for s in stocks if s.get("symbol")]
        
        success = 0
        failed = 0
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        
        for symbol in symbols:
            try:
                # 取得最新資料（FinMind）
                if market in ("TWSE", "TPEX"):
                    rows = await asyncio.to_thread(finmind_adapter.get_tw_stock_price_sync, symbol, start_date, end_date)
                else:
                    rows = await asyncio.to_thread(finmind_adapter.get_us_stock_price_sync, symbol, start_date, end_date)
                if rows:
                    latest = rows[-1]
                    quote = {
                        "date": latest.get("date"),
                        "open": latest.get("open"),
                        "high": latest.get("high"),
                        "low": latest.get("low"),
                        "close": latest.get("close"),
                        "volume": latest.get("volume"),
                    }
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
        stocks = await asyncio.to_thread(finmind_adapter.get_tw_stock_info_all_sync)
        if market == "TWSE":
            stocks = [s for s in stocks if s.get("market") == "TWSE"]
        elif market == "TPEX":
            stocks = [s for s in stocks if s.get("market") == "TPEX"]
        else:
            return 0
        
        count = 0
        for stock in stocks:
            try:
                await supabase.get_client().from_("symbol_index").upsert({
                    "symbol": stock.get("symbol"),
                    "name": stock.get("name"),
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
