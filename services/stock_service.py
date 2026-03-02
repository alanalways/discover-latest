"""
Stock Service - ?∠巨鞈???撅?
?游?????皞???蝯曹?????????
"""
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
import asyncio
import math
import os
import copy
import threading
from collections import OrderedDict

from adapters import (
    supabase, fx_adapter,
    finmind_adapter, ndc_adapter
)

_STOCK_DATA_CACHE_TTL_SEC = max(30, int((os.environ.get("STOCK_DATA_CACHE_TTL_SEC") or "300").strip() or 300))
_STOCK_DATA_CACHE_TTL_OFF_HOURS = max(300, int((os.environ.get("STOCK_DATA_CACHE_TTL_OFF_HOURS") or "14400").strip() or 14400))
_STOCK_DATA_CACHE_MAXSIZE = max(32, int((os.environ.get("STOCK_DATA_CACHE_MAXSIZE") or "256").strip() or 256))
_stock_data_cache: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()
_stock_data_cache_lock = threading.Lock()


class StockService:
    """?∠巨鞈???"""
    
    # 撣隞??
    MARKETS = {
        "TWSE": {"name": "?啁霅鈭斗??", "currency": "TWD"},
        "TPEX": {"name": "瑹眺銝剖?", "currency": "TWD"},
        "US": {"name": "蝢??∪?", "currency": "USD"},
    }

    @staticmethod
    def _to_float(value: Any) -> Optional[float]:
        """撠???銝剔??詨潭?雿???float嚗捆?臬?銝???/蝛箏潘?"""
        if value is None:
            return None
        if isinstance(value, (int, float)):
            v = float(value)
            return v if math.isfinite(v) else None
        if isinstance(value, str):
            text = value.strip().replace(",", "")
            if not text or text in {"-", "N/A", "nan", "None"}:
                return None
            if text.endswith("%"):
                text = text[:-1].strip()
                if not text:
                    return None
            # Unit suffix support: K/M/B/T and Chinese units (萬/億/兆)
            unit_map = {
                "K": 1e3,
                "M": 1e6,
                "B": 1e9,
                "T": 1e12,
                "萬": 1e4,
                "億": 1e8,
                "兆": 1e12,
            }
            last = text[-1:]
            multiplier = unit_map.get(last.upper()) or unit_map.get(last)
            if multiplier:
                text = text[:-1].strip()
                if not text:
                    return None
                try:
                    v = float(text) * multiplier
                    return v if math.isfinite(v) else None
                except Exception:
                    return None
            try:
                v = float(text)
                return v if math.isfinite(v) else None
            except Exception:
                return None
        return None

    def _pick_latest_numeric(self, rows: List[Dict[str, Any]], keys: List[str]) -> Optional[float]:
        """敺????偏蝡臬??曄洵銝?????"""
        if not rows:
            return None
        for row in reversed(rows):
            for key in keys:
                val = self._to_float(row.get(key))
                if val is not None:
                    return val
        return None

    def _normalize_per_pbr_rows(self, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        normalized: List[Dict[str, Any]] = []
        for r in rows or []:
            normalized.append({
                "date": r.get("date"),
                "PER": self._to_float(
                    r.get("PER")
                    or r.get("per")
                    or r.get("pe_ratio")
                    or r.get("PriceEarningRatio")
                ),
                "PBR": self._to_float(
                    r.get("PBR")
                    or r.get("pbr")
                    or r.get("pb_ratio")
                    or r.get("PriceBookRatio")
                ),
                "dividend_yield": self._to_float(
                    r.get("dividend_yield")
                    or r.get("DividendYield")
                    or r.get("DividendYieldRatio")
                    or r.get("dividend_yield_ratio")
                    or r.get("yield")
                    or r.get("Yield")
                    or r.get("cash_dividend_yield")
                    or r.get("CashDividendYield")
                ),
            })
        return normalized

    def _normalize_revenue_rows(self, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        normalized: List[Dict[str, Any]] = []
        for r in rows or []:
            date_text = (
                r.get("date")
                or r.get("revenue_date")
                or r.get("RevenueMonth")
                or r.get("month")
            )
            revenue = self._to_float(r.get("revenue") or r.get("Revenue") or r.get("month_revenue"))
            mom = self._to_float(r.get("revenue_month_over_month") or r.get("month_growth_rate") or r.get("mom"))
            yoy = self._to_float(r.get("revenue_year_over_year") or r.get("year_growth_rate") or r.get("yoy"))
            normalized.append({
                "date": str(date_text or ""),
                "revenue_date": str(date_text or ""),
                "revenue": revenue or 0.0,
                "revenue_month_over_month": mom,
                "revenue_year_over_year": yoy,
            })

        normalized.sort(key=lambda x: x.get("date") or "")
        month_map: Dict[str, float] = {}
        for i, row in enumerate(normalized):
            date_text = row.get("date") or ""
            revenue = self._to_float(row.get("revenue")) or 0.0

            if row.get("revenue_month_over_month") is None and i > 0:
                prev_rev = self._to_float(normalized[i - 1].get("revenue")) or 0.0
                if prev_rev > 0:
                    row["revenue_month_over_month"] = round((revenue - prev_rev) / prev_rev * 100, 2)

            if row.get("revenue_year_over_year") is None and len(date_text) >= 7:
                month_key = date_text[:7]
                year = date_text[:4]
                month = date_text[5:7]
                if year.isdigit() and month.isdigit():
                    prev_year_key = f"{int(year) - 1:04d}-{month}"
                    prev_year_rev = month_map.get(prev_year_key)
                    if prev_year_rev and prev_year_rev > 0:
                        row["revenue_year_over_year"] = round((revenue - prev_year_rev) / prev_year_rev * 100, 2)
                month_map[month_key] = revenue

        return normalized

    def _normalize_institutional_rows(self, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        normalized: List[Dict[str, Any]] = []
        for r in rows or []:
            normalized.append({
                "date": r.get("date"),
                "Foreign_Investor_buy": self._to_float(r.get("Foreign_Investor_buy") or r.get("foreign_investor_buy")) or 0.0,
                "Foreign_Investor_sell": self._to_float(r.get("Foreign_Investor_sell") or r.get("foreign_investor_sell")) or 0.0,
                "Investment_Trust_buy": self._to_float(r.get("Investment_Trust_buy") or r.get("investment_trust_buy")) or 0.0,
                "Investment_Trust_sell": self._to_float(r.get("Investment_Trust_sell") or r.get("investment_trust_sell")) or 0.0,
                "Dealer_self_buy": self._to_float(r.get("Dealer_self_buy") or r.get("dealer_self_buy")) or 0.0,
                "Dealer_self_sell": self._to_float(r.get("Dealer_self_sell") or r.get("dealer_self_sell")) or 0.0,
                "buy": self._to_float(r.get("buy")) or 0.0,
                "sell": self._to_float(r.get("sell")) or 0.0,
            })
        return normalized

    def _normalize_margin_rows(self, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        normalized: List[Dict[str, Any]] = []
        for r in rows or []:
            normalized.append({
                "date": r.get("date"),
                "MarginPurchaseLimit": self._to_float(r.get("MarginPurchaseLimit") or r.get("margin_purchase_limit") or r.get("margin_balance")) or 0.0,
                "MarginPurchaseChange": self._to_float(r.get("MarginPurchaseChange") or r.get("margin_purchase_change") or r.get("margin_change")) or 0.0,
                "ShortSaleLimit": self._to_float(r.get("ShortSaleLimit") or r.get("short_sale_limit") or r.get("short_balance")) or 0.0,
                "ShortSaleChange": self._to_float(r.get("ShortSaleChange") or r.get("short_sale_change") or r.get("short_change")) or 0.0,
                "margin_balance": self._to_float(r.get("margin_balance")) or 0.0,
                "margin_change": self._to_float(r.get("margin_change")) or 0.0,
                "short_balance": self._to_float(r.get("short_balance")) or 0.0,
                "short_change": self._to_float(r.get("short_change")) or 0.0,
            })
        return normalized

    @staticmethod
    def _stock_data_cache_key(symbol: str, market: str, period: str) -> str:
        return f"{str(symbol or '').strip().upper()}|{str(market or '').strip().upper()}|{str(period or '').strip().lower()}"

    def _read_stock_data_cache(self, key: str) -> Optional[Dict[str, Any]]:
        now = datetime.now().timestamp()
        # 智慧 cache TTL：非交易時段延長到 4 小時
        market_tag = key.split("|")[1] if "|" in key else ""
        ttl = self._smart_cache_ttl(market_tag)
        with _stock_data_cache_lock:
            row = _stock_data_cache.get(key)
            if not isinstance(row, dict):
                return None
            ts = float(row.get("ts") or 0.0)
            payload = row.get("payload")
            if ts <= 0 or (now - ts) > ttl:
                _stock_data_cache.pop(key, None)
                return None
            if not isinstance(payload, dict):
                return None
            _stock_data_cache.move_to_end(key)
            return copy.deepcopy(payload)

    @staticmethod
    def _smart_cache_ttl(market: str) -> int:
        """非交易時段延長 cache TTL，避免收盤後重複呼叫外部 API"""
        now = datetime.now()
        weekday = now.weekday()  # 0=Mon, 6=Sun
        hour = now.hour
        minute = now.minute
        current_minutes = hour * 60 + minute

        market_upper = (market or "").strip().upper()

        if market_upper in ("TWSE", "TPEX"):
            # 台股交易時間：09:00-13:30（週一到週五）
            if weekday < 5 and 9 * 60 <= current_minutes <= 13 * 60 + 30:
                return _STOCK_DATA_CACHE_TTL_SEC
        elif market_upper == "US":
            # 美股交易時間（台灣時間約 21:30-04:00 隔天）
            if weekday < 5 and (current_minutes >= 21 * 60 + 30 or current_minutes <= 4 * 60):
                return _STOCK_DATA_CACHE_TTL_SEC
        else:
            return _STOCK_DATA_CACHE_TTL_SEC

        return _STOCK_DATA_CACHE_TTL_OFF_HOURS

    def _write_stock_data_cache(self, key: str, payload: Dict[str, Any]) -> None:
        with _stock_data_cache_lock:
            _stock_data_cache[key] = {"ts": datetime.now().timestamp(), "payload": copy.deepcopy(payload)}
            _stock_data_cache.move_to_end(key)
            while len(_stock_data_cache) > _STOCK_DATA_CACHE_MAXSIZE:
                _stock_data_cache.popitem(last=False)

    async def _backfill_metrics_with_grounding(self, symbol: str, market: str, info: Dict[str, Any]) -> None:
        """Backfill key valuation fields via grounding when FinMind fields are missing."""
        if not isinstance(info, dict):
            return
        need_market_cap = self._to_float(info.get("market_cap")) is None
        need_pe = self._to_float(info.get("pe_ratio")) is None
        need_pb = self._to_float(info.get("pb_ratio")) is None
        need_dy = self._to_float(info.get("dividend_yield")) is None
        if not (need_market_cap or need_pe or need_pb or need_dy):
            return

        try:
            from services.gemini_service import gemini_service
            if not gemini_service.is_available():
                return
            grounded = await asyncio.wait_for(
                asyncio.to_thread(
                    gemini_service.ground_company_metrics,
                    symbol,
                    market,
                    info.get("name") or symbol,
                ),
                timeout=18,
            )
            metrics = grounded.get("metrics") if isinstance(grounded, dict) else None
            if not isinstance(metrics, dict):
                return

            if need_market_cap:
                mv = self._to_float(metrics.get("market_cap"))
                if mv is not None and mv > 0:
                    info["market_cap"] = mv
            if need_pe:
                pe = self._to_float(metrics.get("pe_ratio"))
                if pe is not None and pe > 0:
                    info["pe_ratio"] = pe
            if need_pb:
                pb = self._to_float(metrics.get("pb_ratio"))
                if pb is not None and pb > 0:
                    info["pb_ratio"] = pb
            if need_dy:
                dy = self._to_float(metrics.get("dividend_yield"))
                if dy is not None and dy >= 0:
                    info["dividend_yield"] = dy
        except Exception:
            return
    
    async def get_stock_data(
        self, 
        symbol: str, 
        market: str = None,
        period: str = "1y",
        allow_grounding_backfill: bool = False,
    ) -> Dict[str, Any]:
        """
        ??摰?∠巨鞈?嚗?祈?閮?+ 甇瑕鞈?嚗?
        
        Args:
            symbol: ?∠巨隞??
            market: 撣嚗WSE/TPEX/US嚗???None ????
            period: 甇瑕鞈???
        """
        if market is None:
            market = await self._detect_market(symbol)

        cache_key = self._stock_data_cache_key(symbol, market, period)
        cached_payload = self._read_stock_data_cache(cache_key)
        if cached_payload is not None:
            return cached_payload
        
        # 撱箇?銝西?隞餃?
        tasks = [
            self._get_stock_info(symbol, market),
            self._get_stock_history(symbol, market, period),
        ]

        # ?啗憿???嚗??/?⊥楊瘥??潦?鈭箇?蝣?
        if market in ["TWSE", "TPEX"]:
            start_1y = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
            tasks.append(finmind_adapter.get_tw_per_pbr(symbol, start_date=start_1y))  # Task 2
            tasks.append(finmind_adapter.get_tw_market_value(symbol, start_date=start_1y)) # Task 3
        
        results = await asyncio.gather(*tasks)
        
        info = results[0]
        history = results[1]
        
        # ???啗憿?鞈?
        per_pbr = []
        market_value_data = []
        if len(results) > 2:
            per_pbr = results[2]
            market_value_data = results[3]

        # 閮? 52 ?梢?雿? (??history 頞喳?)
        high_52w = None
        low_52w = None
        if history and len(history) > 0:
            # 蝣箔? history ??sort
            # 頧???Lightweight Charts ?澆? (憓? time 甈?)
            for h in history:
                h["time"] = h.get("date")  # Alias date -> time
            
            # ??餈?250 蝑?蝞?52w
            recent_250 = history[-250:]
            try:
                high_52w = max(d.get("high", 0) for d in recent_250)
                low_52w = min(d.get("low", 0) for d in recent_250)
            except:
                pass
        
        # ?游???唳?澆 info
        if info:
            if high_52w: info["high_52w"] = high_52w
            if low_52w: info["low_52w"] = low_52w

            # ?冽風?脰???朣??啣?撞頝?嚗?頛?/????閬?
            try:
                if history and len(history) >= 1:
                    last_close = self._to_float(history[-1].get("close"))
                    prev_close = self._to_float(history[-2].get("close")) if len(history) >= 2 else None
                    if last_close is not None:
                        info["price"] = round(last_close, 4)
                    if last_close is not None and prev_close and prev_close > 0:
                        change = last_close - prev_close
                        info["change"] = round(change, 4)
                        info["change_percent"] = round(change / prev_close * 100, 4)
            except Exception:
                pass
            
            # ?游? PER/PBR
            if per_pbr:
                normalized_per = self._normalize_per_pbr_rows(per_pbr)
                pe_val = self._pick_latest_numeric(normalized_per, ["PER"])
                pb_val = self._pick_latest_numeric(normalized_per, ["PBR"])
                dy_val = self._pick_latest_numeric(normalized_per, ["dividend_yield"])
                if pe_val is not None:
                    info["pe_ratio"] = pe_val
                if pb_val is not None:
                    info["pb_ratio"] = pb_val
                if dy_val is not None:
                    info["dividend_yield"] = dy_val
                # Some FinMind responses include market value fields in TaiwanStockPER payload.
                if self._to_float(info.get("market_cap")) is None:
                    mv_from_per = self._pick_latest_numeric(
                        per_pbr,
                        ["Market_Value", "market_value", "market_cap", "marketValue", "marketCapitalization"],
                    )
                    if mv_from_per is not None:
                        info["market_cap"] = mv_from_per
             
            # ?游?撣?
            if market_value_data:
                mv_val = self._pick_latest_numeric(
                    market_value_data,
                    ["Market_Value", "market_value", "market_cap", "marketValue", "marketCapitalization"],
                )
                if mv_val is not None:
                    info["market_cap"] = mv_val

            # ?啗畾???潘???PER 鞈??⊥??拍?嚗?刻?抵???+ 餈??∪隡啁?
            if market in ["TWSE", "TPEX"] and self._to_float(info.get("dividend_yield")) is None:
                try:
                    start_3y = (datetime.now() - timedelta(days=1095)).strftime("%Y-%m-%d")
                    div_rows = await finmind_adapter.get_tw_dividend(symbol, start_3y)
                    cash_dividend = self._pick_latest_numeric(
                        div_rows or [],
                        [
                            "CashEarningsDistribution",
                            "cash_dividend",
                            "cash_dividend_per_share",
                            "cash_dividend_rate",
                        ],
                    )
                    last_close = self._to_float(info.get("price"))
                    if last_close is None and history:
                        last_close = self._to_float(history[-1].get("close"))
                    if cash_dividend is not None and last_close and last_close > 0:
                        info["dividend_yield"] = round(cash_dividend / last_close * 100, 4)
                except Exception:
                    pass

            # US嚗 USStockInfo ?摯?潭?雿?鋆蝯曹?甈?
            if market == "US":
                if not info.get("market_cap"):
                    mv_val = self._pick_latest_numeric(
                        [info],
                        [
                            "market_cap", "market_value", "marketValue", "marketCapitalization",
                            "market_capitalization", "MarketCapitalization", "Market_Capitalization", "marketCap",
                        ],
                    )
                    if mv_val is not None:
                        info["market_cap"] = mv_val
                if not info.get("pe_ratio"):
                    pe_val = self._pick_latest_numeric([info], ["pe_ratio", "PER", "price_earning_ratio", "PriceEarningRatio"])
                    if pe_val is not None:
                        info["pe_ratio"] = pe_val
                if not info.get("pb_ratio"):
                    pb_val = self._pick_latest_numeric([info], ["pb_ratio", "PBR", "price_book_ratio", "PriceBookRatio"])
                    if pb_val is not None:
                        info["pb_ratio"] = pb_val
                if not info.get("dividend_yield"):
                    dy_val = self._pick_latest_numeric([info], ["dividend_yield", "DividendYield", "yield"])
                    if dy_val is not None:
                        info["dividend_yield"] = dy_val

            # Final fallback: derive market cap by shares_outstanding * latest price.
            if not info.get("market_cap"):
                shares_outstanding = self._to_float(
                    info.get("shares_outstanding")
                    or info.get("sharesOutstanding")
                    or info.get("shares")
                    or info.get("issued_shares")
                    or info.get("number_of_shares")
                )
                latest_price = self._to_float(info.get("price"))
                if latest_price is None and history:
                    latest_price = self._to_float(history[-1].get("close"))
                if shares_outstanding and latest_price and shares_outstanding > 0 and latest_price > 0:
                    info["market_cap"] = round(shares_outstanding * latest_price, 2)

            # Grounding backfill is optional to avoid unnecessary Gemini usage on hot paths.
            if allow_grounding_backfill:
                await self._backfill_metrics_with_grounding(symbol, market, info)

        payload = {
            "symbol": symbol,
            "market": market,
            "info": info,
            "history": history,
            "updated_at": datetime.now().isoformat()
        }
        # 只快取有 history 的結果，避免空結果被快取導致後續請求永遠拿不到資料
        if history:
            self._write_stock_data_cache(cache_key, payload)
        return payload

    async def get_stock_history(
        self,
        symbol: str,
        period: str = "1y",
        market: str = None,
    ) -> List[Dict]:
        """?祇??寞?嚗?敺風?脰???靘?routes 雿輻嚗?"""
        if market is None:
            market = await self._detect_market(symbol)
        return await self._get_stock_history(symbol, market, period)

    async def get_stock_data_for_analysis(
        self,
        symbol: str,
        period: str = "1y",
    ) -> Dict[str, Any]:
        """?祇??寞?嚗?靘?AI ??雿輻?蟡刻???"""
        return await self.get_stock_data(symbol=symbol, period=period)
    
    async def _detect_market(self, symbol: str) -> str:
        """?芸??菜葫撣"""
        # ?啗隞???虜??4-6 雿摮?
        if symbol.isdigit() and 4 <= len(symbol) <= 6:
            # ??閰行閰Ｘ?血鞈?摨急?閮?
            try:
                result = supabase.get_client().table("symbol_index").select("market").eq("symbol", symbol).limit(1).execute()
                data = result.data
                if isinstance(data, list) and data:
                    return str(data[0].get("market") or "").upper() or "TWSE"
                if isinstance(data, dict):
                    return str(data.get("market") or "").upper() or "TWSE"
            except:
                pass
            
            # ?身?啗
            return "TWSE"
        
        return "US"
    
    async def _get_stock_info(self, symbol: str, market: str) -> Optional[Dict]:
        """???∠巨?箸鞈?嚗?雿輻 FinMind嚗仃????撠?閮?"""
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
                        "shares_outstanding": self._to_float(
                            info.get("shares")
                            or info.get("issued_shares")
                            or info.get("number_of_shares")
                            or info.get("shares_outstanding")
                            or (info.get("raw") or {}).get("shares")
                            or (info.get("raw") or {}).get("issued_shares")
                            or (info.get("raw") or {}).get("shares_outstanding")
                            or (info.get("raw") or {}).get("number_of_shares")
                            or (info.get("raw") or {}).get("capital_stock")
                            or (info.get("raw") or {}).get("company_capital")
                        ),
                        "market_cap": self._to_float(
                            info.get("market_cap")
                            or info.get("market_value")
                            or (info.get("raw") or {}).get("market_cap")
                            or (info.get("raw") or {}).get("market_value")
                            or (info.get("raw") or {}).get("Market_Value")
                            or (info.get("raw") or {}).get("marketCapitalization")
                        ),
                    }
            except Exception as e:
                print(f"[StockInfo] FinMind 憭望? ({symbol}): {e}")
            return {
                "symbol": symbol,
                "name": symbol,
                "industry": "",
                "market": market,
                "type": "stock",
                "shares_outstanding": None,
            }

        # 蝢嚗粥 FinMind USStockInfo嚗?甇亙?鋆? async
        try:
            normalized_symbol = str(symbol or "").strip().upper()
            us_info = await asyncio.to_thread(finmind_adapter.get_us_stock_info_sync, normalized_symbol)
            if not us_info and "." in normalized_symbol:
                us_info = await asyncio.to_thread(finmind_adapter.get_us_stock_info_sync, normalized_symbol.replace(".", "-"))
            if us_info:
                info = us_info[0]
                market_cap = self._to_float(
                    info.get("market_cap")
                    or info.get("market_value")
                    or info.get("marketValue")
                    or info.get("marketCapitalization")
                    or info.get("market_capitalization")
                    or info.get("MarketCapitalization")
                    or info.get("Market_Capitalization")
                    or info.get("marketCap")
                    or info.get("MarketCap")
                    or info.get("market_capital")
                    or info.get("MarketCapUSD")
                    or info.get("capitalization")
                )
                pe_ratio = self._to_float(
                    info.get("pe_ratio")
                    or info.get("PER")
                    or info.get("price_earning_ratio")
                    or info.get("PriceEarningRatio")
                    or info.get("trailingPE")
                )
                pb_ratio = self._to_float(
                    info.get("pb_ratio")
                    or info.get("PBR")
                    or info.get("price_book_ratio")
                    or info.get("PriceBookRatio")
                    or info.get("priceToBook")
                )
                dividend_yield = self._to_float(
                    info.get("dividend_yield")
                    or info.get("DividendYield")
                    or info.get("yield")
                    or info.get("dividendYield")
                )
                return {
                    "symbol": info.get("stock_id") or normalized_symbol,
                    "name": info.get("stock_name") or normalized_symbol,
                    "industry": info.get("industry") or "",
                    "market": "US",
                    "type": "stock",
                    "market_cap": market_cap,
                    "pe_ratio": pe_ratio,
                    "pb_ratio": pb_ratio,
                    "dividend_yield": dividend_yield,
                    "shares_outstanding": self._to_float(
                        info.get("sharesOutstanding")
                        or info.get("shares_outstanding")
                        or info.get("shares")
                        or info.get("totalShares")
                    ),
                }
        except Exception as e:
            print(f"[StockInfo] FinMind US 憭望? ({symbol}): {e}")
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
        """取得歷史資料（FinMind → DB → 縮短期間重試）"""
        end_date = datetime.now()
        period_days = {"1mo": 30, "3mo": 90, "6mo": 180, "1y": 365, "2y": 730, "3y": 1095, "5y": 1825, "max": 3650}
        days = period_days.get(period, 365)
        start_date = end_date - timedelta(days=days)

        # 嘗試 FinMind
        fm_data = await self._fetch_finmind_history(symbol, market, start_date, end_date)
        if fm_data:
            print(f"[DataSource] FinMind OK: {symbol} ({len(fm_data)} rows)")
            return fm_data

        # FinMind 空結果 → 嘗試縮短期間（1y→6mo→3mo）
        fallback_periods = {"1y": 180, "2y": 365, "3y": 730, "5y": 1095}
        fallback_days = fallback_periods.get(period)
        if fallback_days and fallback_days < days:
            shorter_start = end_date - timedelta(days=fallback_days)
            fm_data = await self._fetch_finmind_history(symbol, market, shorter_start, end_date)
            if fm_data:
                print(f"[DataSource] FinMind OK (fallback): {symbol} ({len(fm_data)} rows)")
                return fm_data

        print(f"[DataSource] FinMind empty: {symbol} (period={period})")

        # Fallback: Supabase DB
        try:
            result = supabase.get_client().table("stock_daily").select("*").eq("symbol", symbol).gte("date", start_date.strftime("%Y-%m-%d")).order("date", desc=False).execute()
            data = result.data
            rows = data if isinstance(data, list) else ([data] if isinstance(data, dict) else [])
            if rows:
                print(f"[DataSource] Supabase DB OK: {symbol}")
                return rows
        except:
            pass

        return []

    async def _fetch_finmind_history(
        self, symbol: str, market: str, start_date, end_date
    ) -> List[Dict]:
        """FinMind 資料抓取（單次嘗試）"""
        if market not in ["TWSE", "TPEX", "US"]:
            return []
        try:
            if market in ["TWSE", "TPEX"]:
                return await finmind_adapter.get_tw_stock_price(
                    symbol, start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")
                ) or []
            else:
                us_symbol = str(symbol or "").strip().upper()
                fm_data = await finmind_adapter.get_us_stock_price(
                    us_symbol, start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")
                )
                if (not fm_data) and "." in us_symbol:
                    fm_data = await finmind_adapter.get_us_stock_price(
                        us_symbol.replace(".", "-"),
                        start_date.strftime("%Y-%m-%d"),
                        end_date.strftime("%Y-%m-%d")
                    )
                return fm_data or []
        except Exception as e:
            print(f"[DataSource] FinMind failed ({symbol}): {e}")
            return []
    
    async def search_symbols(self, query: str, limit: int = 20) -> List[Dict]:
        """???∠巨隞??嚗?∪? FinMind嚗? DB嚗? Yahoo嚗?"""
        query_stripped = (query or "").strip()
        if not query_stripped:
            return []
        results = []

        # ?啗嚗??岫 FinMind ??
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
            print(f"[StockService] FinMind ??憭望?: {e}")

        # 敺??澈鋆?
        try:
            db_result = supabase.get_client().table("symbol_index").select("*").or_(f"symbol.ilike.%{query_stripped}%,name.ilike.%{query_stripped}%").limit(limit - len(results)).execute()
            data = db_result.data
            rows = data if isinstance(data, list) else ([data] if isinstance(data, dict) else [])
            if rows:
                existing = {r["symbol"] for r in results}
                for d in rows:
                    if d.get("symbol") not in existing:
                        results.append(d)
        except Exception as e:
            print(f"[StockService] DB ??憭望?: {e}")

        return results[:limit]

    async def get_stock_fundamentals(self, symbol: str, market: str = None) -> Dict:
        """???箸?Ｚ???PER/PBR/??????銵剁?- ?啗??"""
        try:
            if market is None:
                market = await self._detect_market(symbol)

            if market not in ["TWSE", "TPEX"]:
                # US: 欄位名稱在不同 FinMind 帳號可能不同，做關鍵字容錯
                def pick_from_exact(source: Dict[str, Any], keys: List[str]) -> Optional[float]:
                    if not isinstance(source, dict):
                        return None
                    lut = {str(k or "").strip().lower(): v for k, v in source.items()}
                    for key in keys:
                        raw = lut.get(str(key or "").strip().lower())
                        val = self._to_float(raw)
                        if val is not None:
                            return val
                    return None

                def pick_by_keywords(source: Dict[str, Any], keyword_groups: List[List[str]]) -> Optional[float]:
                    if not isinstance(source, dict):
                        return None
                    for key, raw in source.items():
                        key_text = str(key or "").strip().lower()
                        if not key_text:
                            continue
                        for group in keyword_groups:
                            if all(token in key_text for token in group):
                                val = self._to_float(raw)
                                if val is not None:
                                    return val
                    return None

                try:
                    stock_data = await self.get_stock_data(symbol=symbol, market=market, period="1y")
                except Exception as e:
                    print(f"[Fundamentals] US data failed ({symbol}): {type(e).__name__}: {e}")
                    stock_data = {}

                info = stock_data.get("info", {}) if isinstance(stock_data, dict) else {}
                if not isinstance(info, dict):
                    info = {}

                try:
                    raw_info = await self._get_stock_info(symbol, "US")
                    if not isinstance(raw_info, dict):
                        raw_info = {}
                except Exception:
                    raw_info = {}

                merged = dict(raw_info)
                merged.update(info)

                today = datetime.now().strftime("%Y-%m-%d")
                per = self._to_float(merged.get("pe_ratio"))
                if per is None:
                    per = pick_from_exact(
                        merged,
                        [
                            "per",
                            "pe",
                            "pe_ratio",
                            "price_earning_ratio",
                            "priceearningratio",
                            "trailingpe",
                            "forwardpe",
                        ],
                    )
                if per is None:
                    per = pick_by_keywords(merged, [["price", "earning"], ["trailing", "pe"], ["forward", "pe"]])

                pbr = self._to_float(merged.get("pb_ratio"))
                if pbr is None:
                    pbr = pick_from_exact(
                        merged,
                        [
                            "pbr",
                            "pb",
                            "pb_ratio",
                            "price_book_ratio",
                            "pricebookratio",
                            "pricetobook",
                        ],
                    )
                if pbr is None:
                    pbr = pick_by_keywords(merged, [["price", "book"]])

                dy = self._to_float(merged.get("dividend_yield"))
                if dy is None:
                    dy = pick_from_exact(
                        merged,
                        [
                            "dividend_yield",
                            "dividendyield",
                            "dividend_yield_ratio",
                            "trailingannualdividendyield",
                            "yield",
                        ],
                    )
                if dy is None:
                    dy = pick_by_keywords(merged, [["dividend", "yield"]])

                # Grounding backfill for key valuation fields if FinMind/merged info is missing.
                if per is None or pbr is None or dy is None:
                    try:
                        from services.gemini_service import gemini_service
                        if gemini_service.is_available():
                            grounded = await asyncio.wait_for(
                                asyncio.to_thread(
                                    gemini_service.ground_company_metrics,
                                    symbol,
                                    market,
                                    merged.get("name") or symbol,
                                ),
                                timeout=18,
                            )
                            metrics = grounded.get("metrics") if isinstance(grounded, dict) else {}
                            if per is None:
                                per = self._to_float(metrics.get("pe_ratio"))
                            if pbr is None:
                                pbr = self._to_float(metrics.get("pb_ratio"))
                            if dy is None:
                                dy = self._to_float(metrics.get("dividend_yield"))
                    except Exception:
                        pass

                per_pbr = []
                if per is not None or pbr is not None or dy is not None:
                    per_pbr.append({
                        "date": today,
                        "PER": per,
                        "PBR": pbr,
                        "dividend_yield": dy,
                    })
                return {
                    "revenue": [],
                    "per_pbr": per_pbr,
                    "financials": [],
                    "dividend": [],
                }

            start_1y = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
            start_3y = (datetime.now() - timedelta(days=1095)).strftime("%Y-%m-%d")
            result = {}
            try:
                per_data = await finmind_adapter.get_tw_per_pbr(symbol, start_1y)
                normalized = self._normalize_per_pbr_rows(per_data or [])
                result["per_pbr"] = normalized[-30:] if normalized else []
            except Exception as e:
                print(f"[Fundamentals] PER/PBR 憭望? ({symbol}): {e}")
                result["per_pbr"] = []
            try:
                rev_data = await finmind_adapter.get_tw_revenue(symbol, start_3y)
                result["revenue"] = self._normalize_revenue_rows(rev_data or [])
            except Exception as e:
                print(f"[Fundamentals] ???嗅仃??({symbol}): {e}")
                result["revenue"] = []
            try:
                fin_data = await finmind_adapter.get_tw_financial_statements(symbol, start_3y)
                result["financials"] = fin_data if fin_data else []
            except Exception as e:
                print(f"[Fundamentals] ??銵典仃??({symbol}): {e}")
                result["financials"] = []
            try:
                div_data = await finmind_adapter.get_tw_dividend(symbol, start_3y)
                result["dividend"] = div_data if div_data else []
            except Exception as e:
                print(f"[Fundamentals] ?∪憭望? ({symbol}): {e}")
                result["dividend"] = []

            # If FinMind valuation rows are empty, fallback from merged stock info (with grounding backfill).
            if not result.get("per_pbr"):
                try:
                    overview = await self.get_stock_data(symbol=symbol, market=market, period="1y")
                    info = overview.get("info") if isinstance(overview, dict) else {}
                    if isinstance(info, dict):
                        per = self._to_float(info.get("pe_ratio"))
                        pbr = self._to_float(info.get("pb_ratio"))
                        dy = self._to_float(info.get("dividend_yield"))
                        if per is not None or pbr is not None or dy is not None:
                            result["per_pbr"] = [{
                                "date": datetime.now().strftime("%Y-%m-%d"),
                                "PER": per,
                                "PBR": pbr,
                                "dividend_yield": dy,
                            }]
                except Exception:
                    pass
            return result
        except Exception as e:
            print(f"[Fundamentals] unexpected error ({symbol}): {type(e).__name__}: {e}")
            return {
                "revenue": [],
                "per_pbr": [],
                "financials": [],
                "dividend": [],
            }

    async def get_stock_chips(self, symbol: str, market: str = None) -> Dict:
        """??蝐Ⅳ?Ｚ???銝之瘜犖 + ???嚗? ?啗??"""
        if market is None:
            market = await self._detect_market(symbol)
        if market not in ["TWSE", "TPEX"]:
            # US ?∠??蝣潸???嚗誑?漱???賣?靘隞??閮?
            history = await self._get_stock_history(symbol, market, period="3mo")
            institutional = []
            margin = []
            for i in range(1, len(history)):
                curr = history[i]
                prev = history[i - 1]
                close_now = self._to_float(curr.get("close")) or 0.0
                close_prev = self._to_float(prev.get("close")) or 0.0
                vol_now = self._to_float(curr.get("volume")) or 0.0
                vol_prev = self._to_float(prev.get("volume")) or 0.0
                up_day = close_now >= close_prev
                institutional.append({
                    "date": curr.get("date"),
                    "buy": vol_now if up_day else 0.0,
                    "sell": 0.0 if up_day else vol_now,
                })
                margin.append({
                    "date": curr.get("date"),
                    "margin_balance": vol_now,
                    "margin_change": vol_now - vol_prev,
                    "short_balance": 0.0,
                    "short_change": 0.0,
                })
            return {
                "institutional": institutional[-20:],
                "margin": margin[-20:],
            }
        start_3m = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
        result = {}
        try:
            inst_data = await finmind_adapter.get_tw_institutional(symbol, start_3m)
            result["institutional"] = self._normalize_institutional_rows(inst_data or [])
        except Exception as e:
            print(f"[Chips] 瘜犖鞎瑁都頞仃??({symbol}): {e}")
            result["institutional"] = []
        try:
            margin_data = await finmind_adapter.get_tw_margin(symbol, start_3m)
            result["margin"] = self._normalize_margin_rows(margin_data or [])
        except Exception as e:
            print(f"[Chips] ???憭望? ({symbol}): {e}")
            result["margin"] = []
        return result
    
    async def get_market_indices(self) -> Dict[str, List[Dict]]:
        """??撣?嚗inMind proxy嚗?"""
        proxies = {
            "TW": [
                {"symbol": "TAIEX", "name": "???", "proxy": "0050", "market": "TW"},
            ],
            "US": [
                {"symbol": "DJI", "name": "??撌交平", "proxy": "DIA", "market": "US"},
                {"symbol": "SPX", "name": "S&P 500", "proxy": "SPY", "market": "US"},
                {"symbol": "IXIC", "name": "蝝??", "proxy": "QQQ", "market": "US"},
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
        """Get popular ETFs from FinMind."""
        etfs = [
            {"symbol": "0050", "name": "元大台灣50", "market": "TWSE"},
            {"symbol": "0056", "name": "元大高股息", "market": "TWSE"},
            {"symbol": "00878", "name": "國泰永續高股息", "market": "TWSE"},
            {"symbol": "00929", "name": "群益台灣精選高息", "market": "TWSE"},
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
        ?寞活?湔?∠巨鞈???Supabase
        
        Args:
            symbols: ?∠巨隞???”嚗one ??啣??
            market: 撣
        
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
                # ????啗???FinMind嚗?
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
                    # 撖怠鞈?摨?
                    await supabase.upsert_stock_data(symbol, quote)
                    success += 1
                else:
                    failed += 1
                    
            except Exception as e:
                print(f"[StockService] ?湔 {symbol} 憭望?: {e}")
                failed += 1
            
            # ?批隢??餌?
            await asyncio.sleep(0.1)
        
        return {"success": success, "failed": failed}
    
    async def update_symbol_index(self, market: str = "TWSE") -> int:
        """
        ?湔隞??蝝Ｗ?銵?
        
        Returns:
            ?啣?/?湔?誨???
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
                supabase.get_client().table("symbol_index").upsert({
                    "symbol": stock.get("symbol"),
                    "name": stock.get("name"),
                    "market": market,
                    "type": stock.get("type", "stock"),
                    "updated_at": datetime.now().isoformat()
                }).execute()
                count += 1
            except Exception as e:
                print(f"[StockService] ?湔隞??蝝Ｗ? {stock['symbol']} 憭望?: {e}")
        
        return count
    
    async def get_fx_rate(self, from_currency: str = "USD", to_currency: str = "TWD") -> float:
        """???舐?"""
        rate = await fx_adapter.get_rate(from_currency, to_currency)
        return rate or 0.0


# ?桐?
stock_service = StockService()
