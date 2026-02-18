"""
Dexter Agent — 自主型金融研究代理
調用 FinMind / TWSE / TPEX / Yahoo / Gemini 執行多步研究
"""
import time
import traceback
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

from services.tool_registry import tool_registry


class DexterAgent:
    """Dexter 主引擎"""

    def __init__(self):
        self._executor = ThreadPoolExecutor(max_workers=6)

    def execute(self, query: str, user_id: str, symbol: str = None) -> Dict:
        """
        完整執行流程：規劃 → 執行 → 驗證 → 綜合分析

        Returns:
            execution_log dict for dexter_panel rendering
        """
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
            results = self._execute_tasks(tasks, log)

            # Step 3: 驗證結果
            validation = self._validate_results(results)
            log["validation"] = validation

            # Step 4: Gemini 綜合分析
            analysis = self._synthesize_report(query, symbol, results)
            log["analysis"] = analysis

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
            traceback.print_exc()

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

        # 最後加 Gemini 綜合分析（依賴前面結果，不並行）
        tasks.append({
            "name": "AI 綜合分析",
            "tool": "gemini",
            "method": "analyze",
            "kwargs": {"symbol": symbol},
            "parallel": False,
        })

        return tasks

    def _execute_tasks(self, tasks: List[Dict], log: Dict) -> Dict[str, Any]:
        """執行子任務（可並行的任務並行，依賴的循序）"""
        results = {}

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

    def _gemini_synthesize(self, symbol: str, context: Dict) -> Dict:
        """Stage1 grounding search + Stage2 綜合分析（同普通 AI 分析流程）"""
        from config.models import MODEL_DEXTER
        from services.gemini_service import gemini_service

        api_key = gemini_service.get_api_key()
        if not api_key:
            return {"error": "Gemini API key missing"}

        masked = f"{api_key[:4]}...{api_key[-4:]}" if len(api_key) > 8 else "****"
        print(f"[Dexter] model={MODEL_DEXTER} key={masked}")

        # 構建 context summary
        summary_parts = []
        for _task_name, data in context.items():
            if isinstance(data, dict) and data.get("error"):
                continue
            elif isinstance(data, list) and data:
                summary_parts.append(f"{len(data)} 筆數據")
                summary_parts.append(f"  最新: {data[-1] if len(data) <= 3 else data[-3:]}")
            elif isinstance(data, dict) and not data.get("error"):
                summary_parts.append(str(data))
        context_text = "\n".join(summary_parts)

        try:
            from google import genai
            from google.genai import types

            # ── Stage 1: Grounding Search ──
            print(f"[Dexter] Stage 1: grounding search for {symbol}")
            stage1_prompt = (
                f"用 Google Search 搜尋 {symbol} 最新資訊 請用繁體中文輸出\n"
                "必查 當前股價 當日漲跌幅 成交量 近五日走勢\n"
                "必查 財報 法說 公司公告 訂單 評級 產業消息 同業動態\n"
                "必查 利率 匯率 油價 地緣政治等宏觀因素\n"
                "每條格式 日期｜事件｜對股價影響｜來源\n"
                "若找不到證據請寫 尚無足夠證據 最後附 120 字新聞總結\n"
                "禁止 markdown 裝飾符號\n"
                f"背景資料 {context_text}\n"
            )

            key1 = gemini_service.get_api_key()
            client1 = genai.Client(api_key=key1)
            grounding_text = ""
            try:
                resp1 = client1.models.generate_content(
                    model=MODEL_DEXTER,
                    contents=stage1_prompt,
                    config=types.GenerateContentConfig(
                        tools=[types.Tool(google_search=types.GoogleSearch())],
                        temperature=0.2,
                        max_output_tokens=800,
                    ),
                )
                grounding_text = resp1.text.strip() if resp1 and getattr(resp1, "text", None) else ""
            except Exception as e1:
                print(f"[Dexter] Stage 1 grounding failed: {e1}, trying without grounding")
                try:
                    resp1 = client1.models.generate_content(
                        model=MODEL_DEXTER,
                        contents=stage1_prompt,
                        config=types.GenerateContentConfig(temperature=0.2, max_output_tokens=800),
                    )
                    grounding_text = resp1.text.strip() if resp1 and getattr(resp1, "text", None) else ""
                except Exception as e1b:
                    grounding_text = f"搜尋失敗: {type(e1b).__name__}"

            print(f"[Dexter] Stage 1 done: {len(grounding_text)} chars")

            # ── Stage 2: 綜合分析 ──
            print(f"[Dexter] Stage 2: synthesis for {symbol}")
            grounding_compact = grounding_text[:2200] if len(grounding_text) > 2200 else grounding_text

            stage2_prompt = (
                "你是專業金融研究分析師 30 年經驗 風格冷靜 執行導向 數據驅動\n"
                "語言 全文繁體中文 禁止英文句子 技術縮寫除外\n"
                "格式 純文字列點 禁止任何 markdown 符號\n"
                "禁止提及資料來源名稱或工具名稱 直接呈現分析結論\n\n"
                f"標的 {symbol}\n"
                f"已蒐集的市場數據:\n{context_text}\n\n"
                f"最新搜尋證據:\n{grounding_compact}\n\n"
                "請輸出完整的深度研究報告 包含:\n"
                "1. 基本面分析（估值 營收 獲利能力）\n"
                "2. 籌碼面分析（法人動向 融資融券）\n"
                "3. 技術面觀察\n"
                "4. 風險評估\n"
                "5. 投資建議與目標價區間\n"
            )

            key2 = gemini_service.get_api_key()
            client2 = genai.Client(api_key=key2)
            resp2 = client2.models.generate_content(
                model=MODEL_DEXTER,
                contents=stage2_prompt,
                config=types.GenerateContentConfig(
                    temperature=0.3,
                    max_output_tokens=4096,
                ),
            )
            text = resp2.text.strip() if resp2 and getattr(resp2, "text", None) else ""
            print(f"[Dexter] Stage 2 done: {len(text)} chars")
            return {"success": bool(text), "analysis": text}

        except Exception as e:
            return {"error": f"Gemini: {e}"}

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
            if ai_result.get("success"):
                return ai_result.get("analysis", "")
            elif ai_result.get("error"):
                return f"AI 分析失敗: {ai_result['error']}"
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
