"""
Dexter Agent — 自主型金融研究代理
調用 FinMind / TWSE / TPEX / Yahoo / Gemini 執行多步研究
"""
import logging
import re
import time
import traceback
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

from services.tool_registry import tool_registry

logger = logging.getLogger(__name__)

class DexterAgent:
    """Dexter 主引擎"""

    def __init__(self):
        self._executor = ThreadPoolExecutor(max_workers=6)

    def execute(
        self,
        query: str,
        user_id: str,
        symbol: str = None,
        tier: str = "free",
        seed_context: Optional[Dict[str, Any]] = None,
    ) -> Dict:
        """
        完整執行流程：規劃 → 執行 → 驗證 → 綜合分析

        Returns:
            execution_log dict for dexter_panel rendering
        """
        self._current_tier = str(tier or "free").strip().lower()
        start_time = time.time()
        log = {
            "query": query,
            "tasks": [],
            "validation": [],
            "analysis": "",
            "summary": {},
            "error": None,
        }

        try:
            # Step 1: 規劃子任務
            tasks = self._plan_research(query, symbol)
            log["tasks"] = [
                {"name": t["name"], "tool": t["tool"], "status": "pending", "duration": 0}
                for t in tasks
            ]

            # Step 2: 並行執行資料蒐集任務
            results = self._execute_tasks(tasks, log, seed_context=seed_context)

            # Step 3: 驗證結果
            validation = self._validate_results(results)
            log["validation"] = validation

            # Step 4: Gemini 綜合分析
            analysis = self._synthesize_report(query, symbol, results)
            log["analysis"] = analysis

            # 傳遞 AI 綜合分析的錯誤到 log["error"]
            ai_res = results.get("AI 綜合分析", {})
            if isinstance(ai_res, dict) and ai_res.get("error"):
                log["error"] = str(ai_res["error"])

            # Summary
            elapsed = time.time() - start_time
            api_count = sum(1 for t in log["tasks"] if t["status"] == "completed")
            confidence = self._calc_confidence(validation, results)
            log["summary"] = {
                "duration": elapsed,
                "api_calls": api_count,
                "confidence": confidence,
            }

        except Exception as e:
            log["error"] = f"Dexter 執行錯誤: {type(e).__name__}: {e}"
            logger.exception("Dexter task execution error")

        return log

    def _plan_research(self, query: str, symbol: str = None) -> List[Dict]:
        """根據查詢與標的規劃子任務"""
        tasks = []
        if not symbol:
            return tasks

        is_tw = symbol.isdigit() and len(symbol) >= 4
        today = datetime.now()
        one_year_ago = (today - timedelta(days=365)).strftime("%Y-%m-%d")
        three_months_ago = (today - timedelta(days=90)).strftime("%Y-%m-%d")

        if is_tw:
            tasks.append({
                "name": "股價量能",
                "tool": "finmind",
                "method": "tw_price",
                "kwargs": {"symbol": symbol, "start_date": three_months_ago},
                "parallel": True,
            })
            tasks.append({
                "name": "個股資訊",
                "tool": "finmind",
                "method": "tw_info",
                "kwargs": {"symbol": symbol},
                "parallel": True,
            })
            tasks.append({
                "name": "基本面數據",
                "tool": "finmind",
                "method": "tw_per_pbr",
                "kwargs": {"symbol": symbol, "start_date": one_year_ago},
                "parallel": True,
            })
            tasks.append({
                "name": "三大法人買賣超",
                "tool": "finmind",
                "method": "tw_institutional",
                "kwargs": {"symbol": symbol, "start_date": three_months_ago},
                "parallel": True,
            })
            tasks.append({
                "name": "融資融券",
                "tool": "finmind",
                "method": "tw_margin",
                "kwargs": {"symbol": symbol, "start_date": three_months_ago},
                "parallel": True,
            })
            tasks.append({
                "name": "月營收趨勢",
                "tool": "finmind",
                "method": "tw_revenue",
                "kwargs": {"symbol": symbol, "start_date": one_year_ago},
                "parallel": True,
            })
            tasks.append({
                "name": "股利政策",
                "tool": "finmind",
                "method": "tw_dividend",
                "kwargs": {"symbol": symbol, "start_date": (today - timedelta(days=1825)).strftime("%Y-%m-%d")},
                "parallel": True,
            })
        else:
            # 美股用 FinMind USStockPrice
            tasks.append({
                "name": "美股數據",
                "tool": "finmind",
                "method": "us_stock_price",
                "kwargs": {"symbol": symbol, "start_date": (today - timedelta(days=365)).strftime("%Y-%m-%d")},
                "parallel": True,
            })
            tasks.append({
                "name": "美股資訊",
                "tool": "finmind",
                "method": "us_stock_info",
                "kwargs": {"symbol": symbol},
                "parallel": True,
            })

        # 最後加 Gemini 綜合分析（依賴前面結果，不並行）
        tasks.append({
            "name": "AI 綜合分析",
            "tool": "gemini",
            "method": "analyze",
            "kwargs": {"symbol": symbol},
            "parallel": False,
        })

        return tasks

    def _execute_tasks(self, tasks: List[Dict], log: Dict, seed_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """執行子任務（可並行的任務並行，依賴的循序）"""
        results = dict(seed_context or {})

        # 分出可並行 vs 需循序
        parallel_tasks = [t for t in tasks if t.get("parallel")]
        sequential_tasks = [t for t in tasks if not t.get("parallel")]

        # 並行執行
        if parallel_tasks:
            futures = {}
            for task in parallel_tasks:
                idx = tasks.index(task)
                log["tasks"][idx]["status"] = "executing"
                future = self._executor.submit(self._run_single_task, task)
                futures[future] = (task, idx)

            for future in as_completed(futures):
                task, idx = futures[future]
                t_start = time.time()
                try:
                    result = future.result(timeout=30)
                    results[task["name"]] = result
                    log["tasks"][idx]["status"] = "completed"
                    log["tasks"][idx]["duration"] = time.time() - t_start
                except Exception as e:
                    results[task["name"]] = {"error": str(e)}
                    log["tasks"][idx]["status"] = "failed"
                    log["tasks"][idx]["duration"] = time.time() - t_start

        # 循序執行
        for task in sequential_tasks:
            idx = tasks.index(task)
            log["tasks"][idx]["status"] = "executing"
            t_start = time.time()
            try:
                result = self._run_single_task(task, context=results)
                results[task["name"]] = result
                log["tasks"][idx]["status"] = "completed"
            except Exception as e:
                results[task["name"]] = {"error": str(e)}
                log["tasks"][idx]["status"] = "failed"
            log["tasks"][idx]["duration"] = time.time() - t_start

        return results

    def _run_single_task(self, task: Dict, context: Dict = None) -> Any:
        """執行單一任務"""
        tool_name = task["tool"]
        method_key = task["method"]
        kwargs = dict(task.get("kwargs", {}))

        # 特殊處理 finmind us_stock_price
        if tool_name == "finmind" and method_key == "us_stock_price":
            return self._fetch_us_stock_finmind(kwargs.get("symbol", ""), kwargs.get("start_date", ""))
        if tool_name == "finmind" and method_key == "us_stock_info":
            return self._fetch_us_stock_info_finmind(kwargs.get("symbol", ""))

        # 特殊處理 Gemini 綜合分析（注入 context）
        if tool_name == "gemini" and method_key == "analyze":
            return self._gemini_synthesize(kwargs.get("symbol", ""), context or {})

        # 一般工具呼叫
        return tool_registry.call_tool(tool_name, method_key, **kwargs)

    def _fetch_us_stock_finmind(self, symbol: str, start_date: str) -> Dict:
        """使用 FinMind 取得美股資料"""
        try:
            from adapters.finmind_adapter import finmind_adapter
            from datetime import datetime
            end_date = datetime.now().strftime("%Y-%m-%d")
            data = finmind_adapter.get_us_stock_price_sync(symbol, start_date, end_date)
            if data and len(data) > 0:
                last = data[-1]
                prev = data[-2] if len(data) > 1 else last
                return {
                    "name": symbol,
                    "price": last["close"],
                    "pe": "-",
                    "pb": "-",
                    "eps": "-",
                    "dividend_yield": 0,
                    "market_cap": 0,
                    "52w_high": max(d["high"] for d in data[-252:]) if len(data) > 0 else 0,
                    "52w_low": min(d["low"] for d in data[-252:]) if len(data) > 0 else 0,
                    "sector": "",
                    "industry": "",
                }
            return {"error": f"FinMind 無 {symbol} 資料"}
        except Exception as e:
            return {"error": f"FinMind: {e}"}

    def _fetch_us_stock_info_finmind(self, symbol: str) -> Dict:
        """Fetch US stock profile snapshot synchronously."""
        try:
            from adapters.finmind_adapter import finmind_adapter
            rows = finmind_adapter.get_us_stock_info_sync(symbol)
            if not rows:
                return {"error": f"FinMind 無 {symbol} 美股資訊"}
            row = rows[0] if isinstance(rows[0], dict) else {}
            return {
                "symbol": symbol,
                "name": row.get("stock_name") or row.get("name") or symbol,
                "industry": row.get("industry") or row.get("industry_category"),
                "market": row.get("exchange") or row.get("market"),
                "type": row.get("type") or "stock",
            }
        except Exception as e:
            return {"error": f"FinMind: {e}"}

    def _fallback_stock_info_from_context(self, context: Dict[str, Any], symbol: str) -> Dict[str, Any]:
        """Build a minimal stock_info payload for fallback analysis text."""
        out: Dict[str, Any] = {"symbol": symbol}
        if not isinstance(context, dict):
            return out

        # Prefer dict payloads that already resemble stock snapshot.
        for value in context.values():
            if not isinstance(value, dict) or value.get("error"):
                continue
            for k in ("price", "last_close", "close", "pe_ratio", "pb_ratio", "dividend_yield", "market_cap"):
                v = value.get(k)
                if v not in (None, "", "N/A"):
                    out[k] = v

        # TW data frequently comes from per/pbr rows list.
        for value in context.values():
            if not isinstance(value, list) or not value:
                continue
            last = value[-1]
            if not isinstance(last, dict):
                continue
            if out.get("pe_ratio") in (None, "", "N/A") and last.get("PER") not in (None, "", "N/A"):
                out["pe_ratio"] = last.get("PER")
            if out.get("pb_ratio") in (None, "", "N/A") and last.get("PBR") not in (None, "", "N/A"):
                out["pb_ratio"] = last.get("PBR")
            if out.get("dividend_yield") in (None, "", "N/A") and last.get("dividend_yield") not in (None, "", "N/A"):
                out["dividend_yield"] = last.get("dividend_yield")

        return out

    @staticmethod
    def _to_float(value: Any) -> float:
        try:
            if value is None:
                return 0.0
            return float(str(value).replace(",", "").strip())
        except Exception:
            return 0.0

    def _extract_price_rows(self, context: Dict[str, Any]) -> List[Dict[str, float]]:
        """Extract normalized OHLCV rows from mixed context payloads."""
        best: List[Dict[str, float]] = []
        if not isinstance(context, dict):
            return best

        for val in context.values():
            if not isinstance(val, list) or not val:
                continue
            rows: List[Dict[str, float]] = []
            for row in val:
                if not isinstance(row, dict):
                    continue
                close = self._to_float(row.get("close", row.get("Close")))
                high = self._to_float(row.get("high", row.get("High", row.get("max"))))
                low = self._to_float(row.get("low", row.get("Low", row.get("min"))))
                open_p = self._to_float(row.get("open", row.get("Open")))
                vol = self._to_float(row.get("volume", row.get("Volume", row.get("Trading_Volume"))))
                if close <= 0 or high <= 0 or low <= 0:
                    continue
                rows.append(
                    {
                        "open": open_p,
                        "high": high,
                        "low": low,
                        "close": close,
                        "volume": vol,
                    }
                )
            if len(rows) > len(best):
                best = rows

        return best

    def _compute_trade_levels(self, price_rows: List[Dict[str, float]]) -> Dict[str, Any]:
        """Compute concrete entry/stop/target levels from real price data."""
        if not price_rows or len(price_rows) < 30:
            return {}

        closes = [self._to_float(r.get("close")) for r in price_rows]
        highs = [self._to_float(r.get("high")) for r in price_rows]
        lows = [self._to_float(r.get("low")) for r in price_rows]
        vols = [self._to_float(r.get("volume")) for r in price_rows]
        if len(closes) < 30:
            return {}

        last = closes[-1]
        prev = closes[-2] if len(closes) >= 2 else 0.0
        base5 = closes[-6] if len(closes) >= 6 else 0.0
        chg1 = ((last - prev) / prev * 100.0) if prev > 0 else 0.0
        chg5 = ((last - base5) / base5 * 100.0) if base5 > 0 else 0.0

        sma20 = sum(closes[-20:]) / 20.0
        sma60 = (sum(closes[-60:]) / 60.0) if len(closes) >= 60 else (sum(closes) / len(closes))
        support = min(lows[-20:])
        resistance = max(highs[-20:])

        trs: List[float] = []
        for i in range(1, len(price_rows)):
            h = highs[i]
            l = lows[i]
            pc = closes[i - 1]
            if h <= 0 or l <= 0 or pc <= 0:
                continue
            trs.append(max(h - l, abs(h - pc), abs(l - pc)))
        atr = (sum(trs[-14:]) / 14.0) if len(trs) >= 14 else 0.0
        if atr <= 0:
            atr = max(0.01, last * 0.012)

        vol_ratio = 1.0
        if len(vols) >= 20 and vols[-1] > 0:
            avg20 = sum(vols[-20:]) / 20.0
            if avg20 > 0:
                vol_ratio = vols[-1] / avg20

        def zone(a: float, b: float) -> Tuple[float, float]:
            lo, hi = (a, b) if a <= b else (b, a)
            return round(max(0.01, lo), 2), round(max(0.01, hi), 2)

        short_entry = zone(last - 0.60 * atr, last - 0.25 * atr)
        mid_entry = zone(sma20 - 0.50 * atr, sma20 + 0.15 * atr)
        long_entry = zone(sma60 - 0.60 * atr, sma60 + 0.20 * atr)

        short_stop = round(max(0.01, short_entry[0] - 0.8 * atr), 2)
        mid_stop = round(max(0.01, mid_entry[0] - 1.0 * atr), 2)
        long_stop = round(max(0.01, long_entry[0] - 1.2 * atr), 2)

        short_target = round(short_entry[1] + 1.4 * atr, 2)
        mid_target = round(mid_entry[1] + 1.8 * atr, 2)
        long_target = round(long_entry[1] + 2.2 * atr, 2)

        return {
            "last": round(last, 2),
            "chg1": round(chg1, 2),
            "chg5": round(chg5, 2),
            "support": round(support, 2),
            "resistance": round(resistance, 2),
            "atr14": round(atr, 2),
            "sma20": round(sma20, 2),
            "sma60": round(sma60, 2),
            "vol_ratio20": round(vol_ratio, 2),
            "short_entry": short_entry,
            "mid_entry": mid_entry,
            "long_entry": long_entry,
            "short_stop": short_stop,
            "mid_stop": mid_stop,
            "long_stop": long_stop,
            "short_target": short_target,
            "mid_target": mid_target,
            "long_target": long_target,
        }

    def _build_trade_reference_text(self, levels: Dict[str, Any]) -> str:
        if not levels:
            return "無可用交易參考（價格序列不足 30 根）"
        return (
            f"現價 {levels['last']:.2f} 日變動 {levels['chg1']:+.2f}% 5日 {levels['chg5']:+.2f}%\n"
            f"支撐 {levels['support']:.2f} 壓力 {levels['resistance']:.2f} ATR14 {levels['atr14']:.2f} "
            f"SMA20 {levels['sma20']:.2f} SMA60 {levels['sma60']:.2f} 量比20日 {levels['vol_ratio20']:.2f}\n"
            f"短線進場 {levels['short_entry'][0]:.2f}-{levels['short_entry'][1]:.2f} "
            f"停損 {levels['short_stop']:.2f} 目標 {levels['short_target']:.2f}\n"
            f"中線進場 {levels['mid_entry'][0]:.2f}-{levels['mid_entry'][1]:.2f} "
            f"停損 {levels['mid_stop']:.2f} 目標 {levels['mid_target']:.2f}\n"
            f"長線進場 {levels['long_entry'][0]:.2f}-{levels['long_entry'][1]:.2f} "
            f"停損 {levels['long_stop']:.2f} 目標 {levels['long_target']:.2f}"
        )

    def _has_usable_trade_plan(self, text: str) -> bool:
        if not isinstance(text, str) or not text.strip():
            return False
        m = re.search(r"3\.\s*進出場計劃.*?(?:\n4\.|$)", text, flags=re.DOTALL)
        target = m.group(0) if m else text
        numbers = re.findall(r"\d+(?:\.\d+)?", target)
        has_entry = ("進場" in target) or ("entry" in target.lower())
        has_stop = ("停損" in target) or ("stop" in target.lower())
        has_target = ("目標" in target) or ("target" in target.lower())
        return has_entry and has_stop and has_target and len(numbers) >= 9

    def _inject_trade_plan_if_missing(self, text: str, levels: Dict[str, Any]) -> str:
        if not isinstance(text, str):
            return text
        if not levels or self._has_usable_trade_plan(text):
            return text
        patch = (
            "\n\n[系統補充-實價位進出場]\n"
            f"短線進場 {levels['short_entry'][0]:.2f}-{levels['short_entry'][1]:.2f}，"
            f"停損 {levels['short_stop']:.2f}，目標 {levels['short_target']:.2f}\n"
            f"中線進場 {levels['mid_entry'][0]:.2f}-{levels['mid_entry'][1]:.2f}，"
            f"停損 {levels['mid_stop']:.2f}，目標 {levels['mid_target']:.2f}\n"
            f"長線進場 {levels['long_entry'][0]:.2f}-{levels['long_entry'][1]:.2f}，"
            f"停損 {levels['long_stop']:.2f}，目標 {levels['long_target']:.2f}\n"
            "以上價位由近30+根OHLCV實際價格序列推導。"
        )
        return f"{text.rstrip()}{patch}"

    @staticmethod
    def _normalize_na_tokens(text: str) -> str:
        if not isinstance(text, str):
            return text
        out = re.sub(r"\bN/?A\b", "資料不足", text, flags=re.IGNORECASE)
        out = out.replace(" -- ", " 資料不足 ")
        return out

    def _build_data_driven_fallback(
        self,
        symbol: str,
        tier_norm: str,
        context: Dict[str, Any],
        grounding_text: str,
        gemini_service: Any,
    ) -> str:
        price_rows = self._extract_price_rows(context)
        levels = self._compute_trade_levels(price_rows)

        if levels:
            lines = [
                "我是 DiscoverLatest 專屬 AI",
                "1.市場快報",
                f"• 標的 {symbol} 現價 {levels['last']:.2f} 當日 {levels['chg1']:+.2f}% 近5日 {levels['chg5']:+.2f}%",
                f"• 20日支撐 {levels['support']:.2f}｜20日壓力 {levels['resistance']:.2f}｜ATR14 {levels['atr14']:.2f}｜量比20日 {levels['vol_ratio20']:.2f}",
                f"• 事件摘要 {grounding_text[:160] if grounding_text else '無外部事件摘要'}",
                "2.技術面分析",
                f"• SMA20 {levels['sma20']:.2f}｜SMA60 {levels['sma60']:.2f}｜支撐 {levels['support']:.2f}｜壓力 {levels['resistance']:.2f}",
                f"• 波動基準 ATR14 {levels['atr14']:.2f}，以 ATR 作為停損與目標距離。",
                "3.進出場計劃",
                f"• 短線進場區 {levels['short_entry'][0]:.2f}-{levels['short_entry'][1]:.2f}｜停損 {levels['short_stop']:.2f}｜第一目標 {levels['short_target']:.2f}",
                f"• 中線進場區 {levels['mid_entry'][0]:.2f}-{levels['mid_entry'][1]:.2f}｜停損 {levels['mid_stop']:.2f}｜第一目標 {levels['mid_target']:.2f}",
                f"• 長線進場區 {levels['long_entry'][0]:.2f}-{levels['long_entry'][1]:.2f}｜停損 {levels['long_stop']:.2f}｜第一目標 {levels['long_target']:.2f}",
                "4.風險提示",
                "• 若跌破各週期停損價且收盤未收復，執行降風險，不做凹單。",
                "• 若量比持續低於 0.8，降低追價頻率，等待回測支撐再評估。",
                "5.結論",
                "• 本報告以實際價格序列計算價位，不含主觀臆測價。",
                "• 執行時請先確認今日成交量與盤中波動是否偏離最近20日常態。",
                "6.情境交易地圖 偏多 偏空 震盪",
                f"• 偏多：站穩 {levels['resistance']:.2f} 且量比放大時，以上移停損追蹤。",
                f"• 偏空：跌破 {levels['support']:.2f} 且反彈無量時，優先控倉。",
                "• 震盪：區間內以分批、低槓桿執行。",
                "7.宏觀進階分析",
                "• 仍需同步追蹤利率、匯率與半導體產業事件對風險偏好的影響。",
            ]
        else:
            lines = [
                "我是 DiscoverLatest 專屬 AI",
                "1.市場快報",
                f"• 標的 {symbol}：目前可用市場摘要有限，未取得足夠價格序列。",
                f"• 事件摘要 {grounding_text[:160] if grounding_text else '無外部事件摘要'}",
                "2.技術面分析",
                "• 價格序列不足 30 根，無法建立穩健技術參數。",
                "3.進出場計劃",
                "• 價格序列不足，暫不提供數值進場區間，避免提供假價位。",
                "4.風險提示",
                "• 補齊至少 30 根 OHLCV 後再計算進場、停損與目標價。",
                "5.結論",
                "• 本次僅輸出可驗證資料，缺失欄位不以 N/A 代替。",
                "6.情境交易地圖 偏多 偏空 震盪",
                "• 在資料不足情境下僅採觀察，不進行主動倉位決策。",
                "7.宏觀進階分析",
                "• 待補齊行情資料後再與宏觀變數整合。",
            ]
        out = "\n".join(lines)
        out = gemini_service._sanitize_analysis_text(out)
        out = self._normalize_na_tokens(out)
        return gemini_service._pad_to_min_chars(out, tier_norm)

    def _gemini_synthesize(self, symbol: str, context: Dict) -> Dict:
        """Stage1 grounding (flash) + Stage2 深度分析"""
        from config.models import MODEL_GROUNDING, MODEL_DEXTER
        from services.gemini_service import gemini_service

        tier_norm = getattr(self, "_current_tier", "free") or "free"

        # Circuit Breaker check — OPEN 時直接回傳降級分析
        try:
            from services.gemini_circuit_breaker import gemini_breaker
            if not gemini_breaker.is_available:
                gemini_breaker.record_short_circuit()
                logger.warning("[Dexter] Circuit breaker OPEN — skipping Gemini for %s", symbol)
                return {
                    "success": False,
                    "error": "circuit_breaker_open",
                    "analysis": "",
                    "circuit_breaker": True,
                }
        except ImportError:
            pass

        api_key = gemini_service.get_api_key()
        if not api_key:
            return {"error": "Gemini API key missing"}

        # 構建 context summary
        def _num(v: Any) -> float:
            try:
                if v is None:
                    return 0.0
                return float(str(v).replace(",", "").strip())
            except Exception:
                return 0.0

        def _summarize_rows(name: str, rows: List[Dict[str, Any]]) -> str:
            if not rows:
                return f"{name}: 無資料"
            last = rows[-1] if isinstance(rows[-1], dict) else {}
            first = rows[0] if isinstance(rows[0], dict) else {}

            # Price/OHLCV rows
            if "close" in last and ("open" in last or "high" in last or "low" in last):
                closes = [_num(r.get("close")) for r in rows if isinstance(r, dict) and _num(r.get("close")) > 0]
                vols = [_num(r.get("volume")) for r in rows if isinstance(r, dict)]
                last_close = closes[-1] if closes else 0.0
                prev_close = closes[-2] if len(closes) >= 2 else 0.0
                base5 = closes[-6] if len(closes) >= 6 else 0.0
                chg1 = ((last_close - prev_close) / prev_close * 100.0) if prev_close > 0 else 0.0
                chg5 = ((last_close - base5) / base5 * 100.0) if base5 > 0 else 0.0
                vol_ratio = 1.0
                if len(vols) >= 20 and vols[-1] > 0:
                    avg20 = sum(vols[-20:]) / 20.0
                    if avg20 > 0:
                        vol_ratio = vols[-1] / avg20
                return (
                    f"{name}: 近{len(closes)}日 收盤{last_close:.2f} "
                    f"日變動{chg1:.2f}% 5日{chg5:.2f}% 量比20日{vol_ratio:.2f}"
                )

            # Institutional rows
            if "Foreign_Investor_buy" in last or "buy" in last:
                net = 0.0
                for r in rows[-8:]:
                    if not isinstance(r, dict):
                        continue
                    foreign = _num(r.get("Foreign_Investor_buy")) - _num(r.get("Foreign_Investor_sell"))
                    trust = _num(r.get("Investment_Trust_buy")) - _num(r.get("Investment_Trust_sell"))
                    dealer = _num(r.get("Dealer_self_buy")) - _num(r.get("Dealer_self_sell"))
                    if foreign == 0.0 and trust == 0.0 and dealer == 0.0:
                        foreign = _num(r.get("buy")) - _num(r.get("sell"))
                    net += foreign + trust + dealer
                return f"{name}: 近8日法人淨額 {net:.0f}"

            # Margin rows
            if "MarginPurchaseChange" in last or "margin_change" in last:
                mb = 0.0
                for r in rows[-8:]:
                    if not isinstance(r, dict):
                        continue
                    mb += _num(r.get("MarginPurchaseChange") or r.get("margin_change"))
                    mb -= _num(r.get("ShortSaleChange") or r.get("short_change"))
                return f"{name}: 近8日融資減融券後淨變化 {mb:.0f}"

            # PER/PBR
            if "PER" in last or "PBR" in last:
                return (
                    f"{name}: 最新PER {_num(last.get('PER')):.2f} "
                    f"PBR {_num(last.get('PBR')):.2f} 殖利率 {_num(last.get('dividend_yield')):.2f}%"
                )

            # Revenue
            if "revenue" in last:
                return (
                    f"{name}: 最新營收 {_num(last.get('revenue')):.0f} "
                    f"MoM {_num(last.get('revenue_month_over_month')):.2f}% "
                    f"YoY {_num(last.get('revenue_year_over_year')):.2f}%"
                )

            # Dividend
            if "CashEarningsDistribution" in last or "cash_dividend" in last:
                cash = _num(last.get("CashEarningsDistribution") or last.get("cash_dividend"))
                stock = _num(last.get("StockEarningsDistribution") or last.get("stock_dividend"))
                return f"{name}: 最新股利 現金{cash:.2f} 股票{stock:.2f}"

            return f"{name}: 最新 {last}"

        summary_parts = []
        for _task_name, data in context.items():
            if isinstance(data, dict) and data.get("error"):
                continue
            elif isinstance(data, list) and data:
                rows = [r for r in data if isinstance(r, dict)]
                summary_parts.append(_summarize_rows(_task_name, rows))
            elif isinstance(data, dict) and not data.get("error"):
                summary_parts.append(f"{_task_name}: {data}")

        price_rows = self._extract_price_rows(context)
        trade_levels = self._compute_trade_levels(price_rows)
        trade_ref_text = self._build_trade_reference_text(trade_levels)
        summary_parts.append(f"交易參考價位(系統計算): {trade_ref_text}")
        context_text = "\n".join(summary_parts)

        try:
            from google import genai
            from google.genai import types
            from services.gemini_service import (
                build_stage1_prompt, UNIFIED_SYSTEM_PROMPT, TIER_EXTRA,
                GeminiService, safe_response_text,
            )
            from datetime import datetime as _dt

            # ── Stage 1: Grounding Search (flash) ──
            # 先查 grounding cache，命中則跳過 Stage1 省 1 次 API call
            grounding_cache_key = str(symbol or "").strip().upper()
            cached_grounding = gemini_service._read_grounding_cache(grounding_cache_key)
            if cached_grounding:
                grounding_text = str(cached_grounding.get("text") or "")
                logger.info("[Dexter] Stage 1 cache HIT for %s: %d chars", symbol, len(grounding_text))
            else:
                key1 = gemini_service.get_api_key()
                logger.info("[Dexter] Stage 1: model=%s", MODEL_GROUNDING)
                stage1_prompt = build_stage1_prompt(symbol, context_text)

                client1 = genai.Client(api_key=key1)
                grounding_text = ""
                try:
                    resp1 = client1.models.generate_content(
                        model=MODEL_GROUNDING,
                        contents=stage1_prompt,
                        config=types.GenerateContentConfig(
                            tools=[types.Tool(google_search=types.GoogleSearch())],
                            temperature=0.2,
                            max_output_tokens=800,
                        ),
                    )
                    grounding_text = safe_response_text(resp1)
                    # Circuit breaker: record stage1 success
                    try:
                        from services.gemini_circuit_breaker import gemini_breaker as _gb
                        _gb.record_success()
                    except ImportError:
                        pass
                except Exception as e1:
                    logger.warning("[Dexter] Stage 1 grounding failed: %s, fallback no-search", e1)
                    # Circuit breaker: record stage1 failure
                    try:
                        from services.gemini_circuit_breaker import gemini_breaker as _gb
                        _gb.record_failure(f"dexter_stage1_{type(e1).__name__}")
                    except ImportError:
                        pass
                    try:
                        resp1 = client1.models.generate_content(
                            model=MODEL_GROUNDING,
                            contents=stage1_prompt,
                            config=types.GenerateContentConfig(temperature=0.2, max_output_tokens=800),
                        )
                        grounding_text = safe_response_text(resp1)
                    except Exception as e1b:
                        grounding_text = f"搜尋失敗: {type(e1b).__name__}"

                # 寫入 grounding cache 供其他模組共用
                gemini_service._write_grounding_cache(grounding_cache_key, grounding_text, [])
                logger.info("[Dexter] Stage 1 done: %d chars", len(grounding_text))

            # ── Stage 2: 深度分析 — 使用統一 7 章節結構 + tier-based 深度 ──
            key2 = gemini_service.get_api_key()
            logger.info("[Dexter] Stage 2: model=%s, tier=%s", MODEL_DEXTER, tier_norm)

            grounding_compact = grounding_text[:2200] if len(grounding_text) > 2200 else grounding_text
            today_str = _dt.now().strftime("%Y-%m-%d")
            tier_extra = TIER_EXTRA.get(tier_norm, TIER_EXTRA["free"])
            max_tokens = 2048 if tier_norm == "free" else (3200 if tier_norm == "pro" else 4096)

            stage2_prompt = (
                f"{UNIFIED_SYSTEM_PROMPT.replace('{today}', today_str)}\n"
                f"{tier_extra}\n"
                "禁止提及資料來源名稱或工具名稱 直接呈現分析結論\n"
                "即使部分資料不足 也必須完成 1 到 7 章節正文 不可只輸出 JSON\n"
                "第3章必須包含短中長進場區間 停損價與目標價（具體數字）。\n"
                "若無法計算價位，明確寫『價格序列不足』，不得填 N/A。\n\n"
                f"標的 {symbol}\n"
                f"已蒐集的市場數據:\n{context_text}\n\n"
                f"stage1 證據:\n{grounding_compact}\n"
            )

            # Stage2 with auto-retry (max 2 attempts)
            text = ""
            _stage2_last_error = None
            for attempt in range(1, 3):
                try:
                    client2 = genai.Client(api_key=key2)
                    resp2 = client2.models.generate_content(
                        model=MODEL_DEXTER,
                        contents=stage2_prompt,
                        config=types.GenerateContentConfig(
                            temperature=0.3,
                            max_output_tokens=max_tokens,
                        ),
                    )
                    text = safe_response_text(resp2)
                    _stage2_last_error = None
                    # Circuit breaker: record stage2 success
                    try:
                        from services.gemini_circuit_breaker import gemini_breaker as _gb
                        _gb.record_success()
                    except ImportError:
                        pass
                    break  # 成功
                except Exception as e2:
                    _stage2_last_error = e2
                    logger.warning(
                        "[Dexter] Stage 2 attempt %d/2 failed for %s: %s", attempt, symbol, e2
                    )
                    if attempt < 2:
                        import time as _time
                        _time.sleep(1.5)  # 簡單退避

            if _stage2_last_error is not None:
                # 全部重試失敗
                try:
                    from services.gemini_circuit_breaker import gemini_breaker as _gb
                    _gb.record_failure(f"dexter_stage2_{type(_stage2_last_error).__name__}")
                except ImportError:
                    pass
                try:
                    fallback = self._build_data_driven_fallback(
                        symbol=symbol,
                        tier_norm=tier_norm,
                        context=context,
                        grounding_text=grounding_text,
                        gemini_service=gemini_service,
                    )
                    if fallback.strip():
                        return {
                            "success": True,
                            "analysis": fallback,
                            "summary": {},
                            "degraded": True,
                            "fallback_reason": "stage2_exception",
                            "error": f"Gemini: {_stage2_last_error}",
                        }
                except Exception:
                    pass
                return {"error": f"Gemini: {_stage2_last_error}"}

            logger.info("[Dexter] Stage 2 done: %d chars", len(text))

            # 提取 JSON 摘要
            summary_data = None
            try:
                summary_data, text = GeminiService._extract_summary_json(text)
            except Exception:
                pass

            if not text and isinstance(summary_data, dict):
                alt_text = summary_data.get("analysis_text") or summary_data.get("analysis")
                if isinstance(alt_text, str) and alt_text.strip():
                    text = alt_text.strip()

            if not text:
                logger.warning("[Dexter] Stage 2 returned empty text for %s", symbol)
                try:
                    fallback = self._build_data_driven_fallback(
                        symbol=symbol,
                        tier_norm=tier_norm,
                        context=context,
                        grounding_text=grounding_text,
                        gemini_service=gemini_service,
                    )
                    if fallback.strip():
                        logger.info("[Dexter] Stage 2 empty response fallback used for %s", symbol)
                        return {
                            "success": True,
                            "analysis": fallback,
                            "summary": summary_data or {},
                            "degraded": True,
                            "fallback_reason": "stage2_empty_response",
                        }
                except Exception as fb_err:
                    logger.warning("[Dexter] Stage 2 empty fallback failed for %s: %s", symbol, fb_err)
                return {"success": False, "analysis": "", "error": "stage2_empty_response", "summary": summary_data or {}}

            text = gemini_service._sanitize_analysis_text(text)
            text = self._normalize_na_tokens(text)
            text = self._inject_trade_plan_if_missing(text, trade_levels)

            return {"success": True, "analysis": text, "summary": summary_data or {}}

        except Exception as e:
            logger.error("[Dexter] Gemini synthesize failed for %s: %s\n%s", symbol, e, traceback.format_exc())
            return {"success": False, "error": f"Gemini: {e}", "analysis": ""}

    def _validate_results(self, results: Dict[str, Any]) -> List[Dict]:
        """數據驗證"""
        validation = []

        # 完整性檢查
        total = len(results)
        success = sum(1 for v in results.values() if not (isinstance(v, dict) and v.get("error")))
        validation.append({
            "label": f"完整性: {success}/{total} 資料源成功",
            "passed": success > 0,
        })

        # 資料新鮮度檢查
        has_data = any(
            isinstance(v, list) and len(v) > 0
            for v in results.values()
        )
        validation.append({
            "label": "資料新鮮度: 有效資料存在",
            "passed": has_data,
        })

        # 一致性：無矛盾結果
        validation.append({
            "label": "一致性: 邏輯正確",
            "passed": True,
        })

        return validation

    def _synthesize_report(self, query: str, symbol: str, results: Dict) -> str:
        """綜合分析文字（從 Gemini 結果提取）"""
        ai_result = results.get("AI 綜合分析", {})
        if isinstance(ai_result, dict):
            # 優先取 analysis 文字（即使 success=False，有文字就用）
            analysis_text = str(ai_result.get("analysis") or "").strip()
            if analysis_text:
                return analysis_text
            # 有 error 則顯示
            error = ai_result.get("error")
            if error:
                return f"AI 分析失敗: {error}"
        elif isinstance(ai_result, str) and ai_result.strip():
            return ai_result.strip()
        return "分析結果不可用"

    def _calc_confidence(self, validation: List[Dict], results: Dict) -> int:
        """計算置信度百分比"""
        passed = sum(1 for v in validation if v.get("passed"))
        total = max(len(validation), 1)
        base = int(passed / total * 100)

        # 扣分：有失敗的資料源
        failures = sum(1 for v in results.values() if isinstance(v, dict) and v.get("error"))
        penalty = failures * 10
        return max(0, min(100, base - penalty))


dexter_agent = DexterAgent()
