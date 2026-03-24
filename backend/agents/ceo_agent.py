"""
backend/agents/ceo_agent.py
CEO 調度官（Opus 撰寫）

職責：
1. 最高層級 Agent 協調者 — 排程驅動 + 手動觸發
2. 掃描所有使用者自選股，自動入隊分析工作
3. 執行完整 Pipeline：6 部門 → 仲裁 → 首席分析師
4. 協調盤前/盤後/週度回測/儲存檢查等排程任務
5. 透過 TaskQueue 實現非同步工作調度
6. 透過 BudgetGuard 確保 Gemini API 用量不超標

設計原則：
- 所有 Agent 延遲實例化，避免啟動時載入全部模組
- 資料來源模組 (yahoo, finmind) 可能尚未實作，全部 try/except 防呆
- 單一部門 Agent 失敗不會中斷整條 Pipeline，其他部門照常執行
- 所有重要動作均寫入 audit_log，方便事後追蹤
- 模組級單例 + threading.Lock，支援多執行緒安全存取
"""

import json
import logging
import threading
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ═════════════════════════════════════════════════════════════
# 常量
# ═════════════════════════════════════════════════════════════

# 每次完整分析預估的 Gemini 呼叫數（6 部門 + 仲裁 + 首席分析師）
_ESTIMATED_CALLS_PER_STOCK = 8

# 相同 symbol 不重複分析的最小間隔（小時）
_REPORT_FRESHNESS_HOURS = 2

# 盤前掃描的工作優先級（1 = 最高）
_PREMARKET_PRIORITY = 1

# 一般排程掃描優先級
_NORMAL_PRIORITY = 5

# 回測工作優先級
_BACKTEST_PRIORITY = 3

# run_pending_jobs 預設單批次處理上限
_DEFAULT_MAX_JOBS = 20

# Agent 顯示名稱（用於日誌）
_AGENT_DISPLAY = "CEOAgent"


# ═════════════════════════════════════════════════════════════
# CEOAgent
# ═════════════════════════════════════════════════════════════

class CEOAgent:
    """
    CEO 調度官 — DiscoverLatest 2.0 的最高層級 Agent。

    負責：
    - 掃描使用者自選股清單，為需要更新的股票入隊分析工作
    - 執行完整的 6 部門 + 仲裁 + 首席分析師 Pipeline
    - 排程盤前掃描、盤後總結、週度回測、儲存檢查
    - 從 TaskQueue 取出待處理工作並分派執行

    使用方式：
        ceo = get_ceo_agent()
        ceo.hourly_watchlist_scan()
        ceo.run_pending_jobs(max_jobs=5)

    執行緒安全：本類別本身無共用可變狀態（TaskQueue / BudgetGuard
    各自有鎖），可安全被 APScheduler 多 job 並發呼叫。
    """

    def __init__(self) -> None:
        """
        初始化 CEO Agent。

        TaskQueue 和 BudgetGuard 透過各自的 get_ 函式取得單例，
        部門 Agent 延遲到第一次使用時才實例化。
        """
        from backend.core.task_queue import get_task_queue
        from backend.core.budget_guard import get_budget_guard

        self._task_queue = get_task_queue()
        self._budget_guard = get_budget_guard()

        # 延遲實例化的 Agent 快取
        self._agents: dict[str, Any] = {}
        self._agents_lock = threading.Lock()

        logger.info(f"[{_AGENT_DISPLAY}] 初始化完成")

    # ═════════════════════════════════════════════════════════
    # 排程入口方法（供 heartbeat.py 呼叫）
    # ═════════════════════════════════════════════════════════

    def hourly_watchlist_scan(self, market_filter: Optional[str] = None) -> dict:
        """
        每小時自選股掃描。

        流程：
        1. 從 user_prefs 表取得所有使用者的自選股（去重）
        2. 檢查每支股票是否有最近 2 小時內的報告
        3. 對缺少新報告的股票，檢查 API 預算後入隊分析工作
        4. 記錄掃描結果

        Returns:
            {
                "scanned": int,      -- 掃描的不重複股票數
                "enqueued": int,     -- 新入隊的分析工作數
                "skipped_fresh": int, -- 已有新報告而跳過的數量
                "skipped_budget": int, -- 預算不足而跳過的數量
            }
        """
        return self._scan_watchlist(
            priority=_NORMAL_PRIORITY,
            scan_label="每小時掃描",
            market_filter=market_filter,
        )

    def premarket_scan(self, market_filter: Optional[str] = None) -> dict:
        """
        盤前掃描（台股盤前 08:25 執行）。

        與 hourly_watchlist_scan 相同邏輯，但工作優先級為 1（最高），
        確保盤前報告能優先處理。

        Returns:
            同 hourly_watchlist_scan 的回傳結構
        """
        return self._scan_watchlist(
            priority=_PREMARKET_PRIORITY,
            scan_label="盤前掃描",
            market_filter=market_filter or "TW",
        )

    def postmarket_summary(self) -> dict:
        """
        盤後總結（台股收盤後 15:05 執行）。

        流程：
        1. 統計今日報告產生數量（成功 / 失敗）
        2. 統計今日 Gemini 使用量
        3. 若今日有任何報告產生，且 run_backtest 尚未排隊，則入隊回測

        Returns:
            {
                "date": str,
                "reports_generated": int,
                "reports_failed": int,
                "gemini_status": dict,
                "backtest_enqueued": bool,
            }
        """
        from backend.core.audit_log import log_agent_action

        start = time.time()
        today_str = date.today().isoformat()
        result: dict[str, Any] = {
            "date": today_str,
            "reports_generated": 0,
            "reports_failed": 0,
            "gemini_status": {},
            "backtest_enqueued": False,
        }

        # ── 1. 統計今日報告 ────────────────────────────────
        try:
            from backend.data.storage.supabase_client import get_client
            client = get_client()
            if client:
                today_start = f"{today_str}T00:00:00+00:00"
                today_end = f"{today_str}T23:59:59+00:00"

                # 成功的報告：有 final_report 且 created_at 在今日
                success_resp = (
                    client.table("reports")
                    .select("id", count="exact")
                    .gte("created_at", today_start)
                    .lte("created_at", today_end)
                    .execute()
                )
                result["reports_generated"] = success_resp.count or 0

                # 失敗的 agent_logs
                fail_resp = (
                    client.table("agent_logs")
                    .select("id", count="exact")
                    .eq("status", "failed")
                    .eq("action", "generate_report")
                    .gte("created_at", today_start)
                    .lte("created_at", today_end)
                    .execute()
                )
                result["reports_failed"] = fail_resp.count or 0

        except Exception as e:
            logger.warning(f"[{_AGENT_DISPLAY}] 盤後統計查詢失敗: {e}")

        # ── 2. Gemini 使用量 ──────────────────────────────
        result["gemini_status"] = self._budget_guard.get_status()

        # ── 3. 入隊回測 ──────────────────────────────────
        if result["reports_generated"] > 0:
            if not self._has_pending_job("run_backtest"):
                self._task_queue.enqueue(
                    job_type="run_backtest",
                    payload={"triggered_by": "postmarket_summary", "date": today_str},
                    priority=_BACKTEST_PRIORITY,
                )
                result["backtest_enqueued"] = True

        duration_ms = int((time.time() - start) * 1000)

        logger.info(
            f"[{_AGENT_DISPLAY}] 盤後總結: "
            f"報告 {result['reports_generated']} 筆（失敗 {result['reports_failed']}），"
            f"Gemini 用量 {result['gemini_status'].get('usage_pct', '?')}%，"
            f"回測入隊={result['backtest_enqueued']}"
        )

        log_agent_action(
            agent_name="ceo_agent",
            report_id=None,
            status="success",
            action="postmarket_summary",
            duration_ms=duration_ms,
            metadata=result,
        )

        return result

    def weekly_backtest(self) -> dict:
        """
        週度回測（每週一 07:00 執行）。

        入隊一個 run_backtest 工作，由 run_pending_jobs 取出執行。

        Returns:
            {"job_id": str | None, "enqueued": bool}
        """
        from backend.core.audit_log import log_agent_action

        today_str = date.today().isoformat()

        # 避免重複入隊
        if self._has_pending_job("run_backtest"):
            logger.info(f"[{_AGENT_DISPLAY}] 週度回測: 已有 pending 的回測工作，跳過")
            return {"job_id": None, "enqueued": False}

        job_id = self._task_queue.enqueue(
            job_type="run_backtest",
            payload={"triggered_by": "weekly_backtest", "date": today_str},
            priority=_BACKTEST_PRIORITY,
        )

        logger.info(f"[{_AGENT_DISPLAY}] 週度回測: 已入隊 [{job_id[:8] if job_id else '?'}]")

        log_agent_action(
            agent_name="ceo_agent",
            report_id=None,
            status="success",
            action="weekly_backtest",
            metadata={"job_id": job_id, "date": today_str},
        )

        return {"job_id": job_id, "enqueued": True}

    def storage_check(self) -> dict:
        """
        儲存健康檢查（每 6 小時執行）。

        嘗試匯入並執行 StorageCurator，處理 Supabase 空間管理。
        StorageCurator 可能尚未實作，失敗時記錄警告不中斷。

        Returns:
            {"status": "success"|"skipped"|"error", "detail": str}
        """
        from backend.core.audit_log import log_agent_action
        start = time.time()

        try:
            from backend.agents.infra.storage_curator import StorageCurator
            curator = StorageCurator()
            curator_result = curator.run_check()
            duration_ms = int((time.time() - start) * 1000)

            logger.info(
                f"[{_AGENT_DISPLAY}] 儲存檢查完成: {curator_result}"
            )
            log_agent_action(
                agent_name="ceo_agent",
                report_id=None,
                status="success",
                action="storage_check",
                duration_ms=duration_ms,
                metadata={"curator_result": str(curator_result)[:500]},
            )
            return {"status": "success", "detail": str(curator_result)}

        except ImportError:
            logger.info(
                f"[{_AGENT_DISPLAY}] 儲存檢查: StorageCurator 尚未實作，跳過"
            )
            return {"status": "skipped", "detail": "StorageCurator not implemented"}

        except Exception as e:
            duration_ms = int((time.time() - start) * 1000)
            logger.error(f"[{_AGENT_DISPLAY}] 儲存檢查失敗: {e}")
            log_agent_action(
                agent_name="ceo_agent",
                report_id=None,
                status="failed",
                action="storage_check",
                duration_ms=duration_ms,
                error=str(e),
            )
            return {"status": "error", "detail": str(e)}

    # ═════════════════════════════════════════════════════════
    # 工作執行
    # ═════════════════════════════════════════════════════════

    def run_pending_jobs(self, max_jobs: int = _DEFAULT_MAX_JOBS) -> dict:
        """
        從 TaskQueue 取出並執行待處理工作。

        每次最多處理 max_jobs 個工作。每個工作依類型分派到
        對應的執行方法（analyze_stock / run_backtest）。

        Args:
            max_jobs: 單批次最多處理的工作數

        Returns:
            {
                "processed": int,
                "succeeded": int,
                "failed": int,
                "details": list[dict],
            }
        """
        from backend.core.audit_log import log_agent_action
        start = time.time()

        # ── 批次 Grounding 預熱（一次 Gemini 取回多支股票資料）──────────
        # 先 peek 即將執行的 analyze_stock jobs，一次 Gemini 呼叫暖快取，
        # 後續各 _run_analysis 呼叫 BatchGroundingAgent.fetch_all() 時直接命中。
        try:
            upcoming = self._task_queue.peek_pending_jobs(max_jobs)
            analyze_symbols: list[tuple[str, str]] = [
                (
                    j["payload"]["symbol"],
                    j["payload"].get("market", "TW"),
                )
                for j in upcoming
                if j.get("job_type") == "analyze_stock"
                   and isinstance(j.get("payload"), dict)
                   and j["payload"].get("symbol")
            ]
            if len(analyze_symbols) >= 2:
                from backend.gemini.grounding import BatchGroundingAgent
                BatchGroundingAgent().fetch_batch(analyze_symbols)
                logger.info(
                    f"[{_AGENT_DISPLAY}] 批次 grounding 預熱完成: "
                    f"{[s for s, _ in analyze_symbols]}"
                )
        except Exception as _pre_e:
            logger.debug(
                f"[{_AGENT_DISPLAY}] 批次 grounding 預熱失敗（不影響執行）: {_pre_e}"
            )

        processed = 0
        succeeded = 0
        failed = 0
        consecutive_failures = 0
        _CIRCUIT_BREAKER_LIMIT = 3  # 連續失敗 3 次即停止，避免 429 風暴
        details: list[dict] = []

        for _ in range(max_jobs):
            job = self._task_queue.dequeue(agent_name="ceo_agent")
            if job is None:
                break  # 無待處理工作

            job_id = job.get("id", "unknown")
            job_type = job.get("job_type", "unknown")
            processed += 1

            logger.info(
                f"[{_AGENT_DISPLAY}] 開始執行工作 [{job_id[:8]}] "
                f"type={job_type} priority={job.get('priority')}"
            )

            try:
                job_result = self._execute_job(job)
                job_success = job_result.get("status") == "success"
                if job_success:
                    succeeded += 1
                    consecutive_failures = 0
                else:
                    failed += 1
                    consecutive_failures += 1
                details.append({
                    "job_id": job_id,
                    "job_type": job_type,
                    "success": job_success,
                    "summary": _truncate_str(str(job_result), 200),
                })
            except Exception as e:
                failed += 1
                consecutive_failures += 1
                logger.error(
                    f"[{_AGENT_DISPLAY}] 工作 [{job_id[:8]}] 未預期例外: {e}",
                    exc_info=True,
                )
                self._task_queue.fail(job_id, str(e), retry=True)
                details.append({
                    "job_id": job_id,
                    "job_type": job_type,
                    "success": False,
                    "error": str(e)[:200],
                })

            # Circuit breaker：連續失敗超過限制就停止
            if consecutive_failures >= _CIRCUIT_BREAKER_LIMIT:
                logger.warning(
                    f"[{_AGENT_DISPLAY}] 連續 {_CIRCUIT_BREAKER_LIMIT} 個工作失敗，"
                    f"啟動斷路器，暫停處理剩餘工作"
                )
                break

        duration_ms = int((time.time() - start) * 1000)

        if processed > 0:
            logger.info(
                f"[{_AGENT_DISPLAY}] run_pending_jobs 完成: "
                f"處理 {processed}，成功 {succeeded}，失敗 {failed}，"
                f"耗時 {duration_ms}ms"
            )
            log_agent_action(
                agent_name="ceo_agent",
                report_id=None,
                status="success",
                action="run_pending_jobs",
                duration_ms=duration_ms,
                metadata={
                    "processed": processed,
                    "succeeded": succeeded,
                    "failed": failed,
                },
            )

        return {
            "processed": processed,
            "succeeded": succeeded,
            "failed": failed,
            "details": details,
        }

    # ═════════════════════════════════════════════════════════
    # 工作分派與執行
    # ═════════════════════════════════════════════════════════

    def _execute_job(self, job: dict) -> dict:
        """
        依 job_type 分派到對應的執行方法。

        Args:
            job: TaskQueue 中取出的工作 dict，包含 id/job_type/payload 等

        Returns:
            執行結果 dict（至少包含 status 欄位）
        """
        job_type = job.get("job_type", "")
        job_id = job.get("id", "unknown")

        dispatch_map = {
            "analyze_stock": self._run_analysis,
            "run_backtest": self._run_backtest,
        }

        handler = dispatch_map.get(job_type)
        if handler is None:
            error_msg = f"未知的工作類型: {job_type}"
            logger.warning(f"[{_AGENT_DISPLAY}] [{job_id[:8]}] {error_msg}")
            self._task_queue.fail(job_id, error_msg, retry=False)
            return {"status": "failed", "error": error_msg}

        return handler(job)

    def _run_analysis(self, job: dict) -> dict:
        """
        執行完整的股票分析 Pipeline。

        流程：
        1. 從 payload 提取 symbol / market / user_id
        2. 檢查 API 預算（預估 8 次呼叫）
        3. 取得市場資料（價格 / 基本面 / 籌碼）
        4. 並行執行 6 個部門 Agent（每個獨立 try/except）
        5. 執行仲裁官整合結果
        6. 執行首席分析師生成最終報告
        7. 將完整結果寫入 reports 表
        8. 記錄 Gemini 使用量
        9. 標記工作完成或失敗

        Args:
            job: TaskQueue 工作 dict

        Returns:
            執行結果 dict
        """
        from backend.core.audit_log import log_agent_action

        job_id = job.get("id", "unknown")
        payload = job.get("payload", {})
        symbol = payload.get("symbol", "")
        market = payload.get("market", "TW")
        user_id = payload.get("user_id")

        if not symbol:
            error_msg = "payload 缺少 symbol"
            self._task_queue.fail(job_id, error_msg, retry=False)
            return {"status": "failed", "error": error_msg}

        start = time.time()
        report_id = str(uuid.uuid4())

        logger.info(
            f"[{_AGENT_DISPLAY}] 開始分析 {symbol} ({market}) "
            f"report={report_id[:8]} job={job_id[:8]}"
        )

        # ── 1. 預算檢查 ──────────────────────────────────
        can_proceed, reason = self._budget_guard.can_proceed(
            estimated_calls=_ESTIMATED_CALLS_PER_STOCK
        )
        if not can_proceed:
            logger.warning(
                f"[{_AGENT_DISPLAY}] 預算不足，跳過 {symbol}: {reason}"
            )
            self._task_queue.fail(job_id, f"預算不足: {reason}", retry=True)
            return {"status": "budget_exceeded", "reason": reason}

        # ── 2. 取得市場資料 ──────────────────────────────
        price_data = self._fetch_price_data(symbol, market)
        fundamental_data = self._fetch_fundamental_data(symbol, market)
        chips_data = self._fetch_chips_data(symbol, market)

        # ── 3. 執行六部門分析 ─────────────────────────────
        dept_results: dict[str, dict] = {}
        gemini_calls = 0

        # 3a. 技術分析（需要 price_data）
        dept_results["technical"] = self._run_dept_safe(
            "technical", symbol=symbol, market=market,
            price_data=price_data, report_id=report_id,
        )
        gemini_calls += 1

        # 3b. 基本面分析（需要 financial_data）
        dept_results["fundamental"] = self._run_dept_safe(
            "fundamental", symbol=symbol, market=market,
            financial_data=fundamental_data, report_id=report_id,
        )
        gemini_calls += 1

        # 3c. 籌碼分析（需要 chips_data）
        dept_results["chips"] = self._run_dept_safe(
            "chips", symbol=symbol, market=market,
            chips_data=chips_data, report_id=report_id,
        )
        gemini_calls += 1

        # 3d-f. Batch Grounding（一次 Gemini 取三份資料）──────────────
        # 先取 industry（後面 macro 需要，fundamental_data 此時已有）
        _industry_pre = self._get_industry(symbol, market, fundamental_data)

        _event_gr: dict = {}
        _macro_gr: dict = {}
        _sentiment_gr: dict = {}
        try:
            from backend.gemini.grounding import BatchGroundingAgent
            _gr = BatchGroundingAgent().fetch_all(
                symbol=symbol, market=market, report_id=report_id
            )
            _event_gr     = _gr.get("event_data", {}) or {}
            _macro_gr     = _gr.get("macro_data", {}) or {}
            _sentiment_gr = _gr.get("sentiment_data", {}) or {}
            if not _gr.get("_error") and not _gr.get("_from_cache"):
                gemini_calls += 1  # 消耗 1 次 Gemini grounding RPD
        except Exception as _gr_err:
            logger.warning(
                f"[{_AGENT_DISPLAY}] Batch grounding 失敗，使用空資料繼續: {_gr_err}"
            )

        # 3d. 事件驅動（NVIDIA + grounding 資料）
        dept_results["event"] = self._run_dept_safe(
            "event", symbol=symbol, market=market,
            grounding_data=_event_gr, report_id=report_id,
        )
        gemini_calls += 1

        # 3e. 宏觀策略（NVIDIA + grounding 資料）
        dept_results["macro"] = self._run_dept_safe(
            "macro", symbol=symbol, market=market,
            grounding_data=_macro_gr, industry=_industry_pre,
            report_id=report_id,
        )
        gemini_calls += 1

        # 3f. 情緒雷達（NVIDIA + grounding 資料）
        dept_results["sentiment"] = self._run_dept_safe(
            "sentiment", symbol=symbol, market=market,
            grounding_data=_sentiment_gr, report_id=report_id,
        )
        gemini_calls += 1

        # 統計多少部門成功
        successful_depts = sum(
            1 for d in dept_results.values()
            if d.get("status") not in ("failed", "rate_limited", "error")
               or d.get("summary") or d.get("raw")
        )
        logger.info(
            f"[{_AGENT_DISPLAY}] {symbol} 部門分析完成: "
            f"{successful_depts}/6 成功"
        )

        # ── 4. 仲裁 ──────────────────────────────────────
        arb_result = self._run_arbitration(dept_results, report_id)
        gemini_calls += 1

        # ── 5. 首席分析師 ─────────────────────────────────
        # 嘗試取得公司資訊（用於報告，缺少時用預設值）
        company_name = self._get_company_name(symbol, market, fundamental_data)
        industry = self._get_industry(symbol, market, fundamental_data)
        current_price = self._get_current_price(symbol, market, price_data)

        chief_result = self._run_chief_analyst(
            symbol=symbol,
            market=market,
            company_name=company_name,
            industry=industry,
            current_price=current_price,
            dept_results=dept_results,
            arb_result=arb_result,
            report_id=report_id,
        )
        gemini_calls += 1

        # ── 6. 記錄預算使用 ──────────────────────────────
        # 簡化：以主力模型 gemini-2.5-flash 記錄大部分使用量
        self._budget_guard.record_usage("gemini-2.5-flash", calls=6)
        # 仲裁 + 首席分析師使用較強模型
        chief_model = chief_result.get("model_used", "gemini-3-flash-preview")
        self._budget_guard.record_usage(chief_model, calls=2)

        duration_ms = int((time.time() - start) * 1000)

        # ── 6b. 規則式品質審查（零 API 成本）────────────────
        try:
            from backend.agents.infra.report_qa import check_report
            qa_passed, qa_reasons = check_report(chief_result, dept_results)
        except Exception as _qa_err:
            logger.warning(f"[{_AGENT_DISPLAY}] QA 模組例外，跳過審查: {_qa_err}")
            qa_passed, qa_reasons = True, []

        if not qa_passed:
            logger.warning(
                f"[{_AGENT_DISPLAY}] {symbol} 報告品質不合格，放棄 DB 寫入並重試: "
                f"{qa_reasons} [{report_id[:8]}]"
            )
            self._task_queue.fail(
                job_id,
                f"QA 不合格: {'; '.join(qa_reasons)}",
                retry=True,
            )
            log_agent_action(
                agent_name="ceo_agent",
                report_id=report_id,
                status="qa_failed",
                action="run_analysis",
                duration_ms=duration_ms,
                metadata={
                    "symbol": symbol,
                    "market": market,
                    "qa_reasons": qa_reasons,
                    "successful_depts": successful_depts,
                },
            )
            return {
                "status": "qa_failed",
                "report_id": report_id,
                "symbol": symbol,
                "market": market,
                "qa_reasons": qa_reasons,
                "successful_depts": successful_depts,
                "duration_ms": duration_ms,
                "db_saved": False,
            }

        # ── 7. 儲存到 reports 表 ─────────────────────────
        db_saved = self._save_report_to_db(
            report_id=report_id,
            symbol=symbol,
            market=market,
            dept_outputs=dept_results,
            arb_result=arb_result,
            chief_result=chief_result,
            user_id=user_id,
            gemini_calls=gemini_calls,
            duration_ms=duration_ms,
        )

        # ── 7b. 儲存 predictions（必須在 report 寫入後）───
        if db_saved:
            from backend.data.storage.supabase_client import insert_row
            pending_preds = chief_result.get("pending_predictions", [])
            for pred in pending_preds:
                try:
                    insert_row("predictions", pred)
                except Exception as e:
                    logger.warning(
                        f"[{_AGENT_DISPLAY}] prediction 寫入失敗: {e}"
                    )
            if pending_preds:
                logger.info(
                    f"[{_AGENT_DISPLAY}] {symbol} 已寫入 "
                    f"{len(pending_preds)} 筆 predictions"
                )

        # ── 8. 標記工作完成或失敗 ────────────────────────
        analysis_status = chief_result.get("status", "failed")

        if analysis_status == "success":
            self._task_queue.complete(job_id, result={
                "report_id": report_id,
                "symbol": symbol,
                "rating": chief_result.get("rating"),
                "confidence": chief_result.get("confidence_score"),
                "db_saved": db_saved,
            })
        else:
            self._task_queue.fail(
                job_id,
                chief_result.get("error", "Chief analyst failed"),
                retry=True,
            )

        log_agent_action(
            agent_name="ceo_agent",
            report_id=report_id,
            status=analysis_status,
            action="run_analysis",
            duration_ms=duration_ms,
            metadata={
                "symbol": symbol,
                "market": market,
                "successful_depts": successful_depts,
                "gemini_calls": gemini_calls,
                "db_saved": db_saved,
                "rating": chief_result.get("rating"),
            },
        )

        logger.info(
            f"[{_AGENT_DISPLAY}] {symbol} 分析完成: "
            f"status={analysis_status}, "
            f"rating={chief_result.get('rating')}, "
            f"depts={successful_depts}/6, "
            f"耗時 {duration_ms}ms"
        )

        return {
            "status": analysis_status,
            "report_id": report_id,
            "symbol": symbol,
            "market": market,
            "rating": chief_result.get("rating"),
            "target_price_low": chief_result.get("target_price_low"),
            "target_price_high": chief_result.get("target_price_high"),
            "confidence_score": chief_result.get("confidence_score"),
            "prediction_ids": chief_result.get("prediction_ids", []),
            "successful_depts": successful_depts,
            "gemini_calls": gemini_calls,
            "duration_ms": duration_ms,
            "db_saved": db_saved,
        }

    def _run_backtest(self, job: dict) -> dict:
        """
        執行準確率回測。

        嘗試匯入 Backtester 並執行，模組可能尚未實作。

        Args:
            job: TaskQueue 工作 dict

        Returns:
            執行結果 dict
        """
        from backend.core.audit_log import log_agent_action

        job_id = job.get("id", "unknown")
        start = time.time()

        try:
            from backend.agents.evolution.backtester import Backtester
            backtester = Backtester()
            bt_result = backtester.run()
            duration_ms = int((time.time() - start) * 1000)

            self._task_queue.complete(job_id, result=bt_result)

            logger.info(
                f"[{_AGENT_DISPLAY}] 回測完成 [{job_id[:8]}]: {bt_result}"
            )
            log_agent_action(
                agent_name="ceo_agent",
                report_id=None,
                status="success",
                action="run_backtest",
                duration_ms=duration_ms,
                metadata={"backtester_result": str(bt_result)[:500]},
            )
            return {"status": "success", "detail": bt_result}

        except ImportError:
            error_msg = "Backtester 模組尚未實作"
            logger.info(f"[{_AGENT_DISPLAY}] {error_msg}，標記工作完成")
            self._task_queue.complete(job_id, result={"skipped": error_msg})
            return {"status": "success", "detail": error_msg}

        except Exception as e:
            duration_ms = int((time.time() - start) * 1000)
            error_msg = f"回測執行失敗: {e}"
            logger.error(f"[{_AGENT_DISPLAY}] {error_msg}", exc_info=True)
            self._task_queue.fail(job_id, error_msg, retry=True)
            log_agent_action(
                agent_name="ceo_agent",
                report_id=None,
                status="failed",
                action="run_backtest",
                duration_ms=duration_ms,
                error=error_msg,
            )
            return {"status": "failed", "error": error_msg}

    # ═════════════════════════════════════════════════════════
    # 內部掃描邏輯
    # ═════════════════════════════════════════════════════════

    def _scan_watchlist(
        self,
        priority: int,
        scan_label: str,
        market_filter: Optional[str] = None,
    ) -> dict:
        """
        掃描自選股清單的共用邏輯（hourly 和 premarket 共用）。

        Args:
            priority:   入隊工作的優先級
            scan_label: 掃描標籤（用於日誌）

        Returns:
            掃描結果統計 dict
        """
        from backend.core.audit_log import log_agent_action

        start = time.time()
        normalized_market = str(market_filter or "").strip().upper()
        symbols = self._get_watchlist_symbols()
        if normalized_market:
            symbols = [
                item for item in symbols
                if str(item.get("market", "TW")).strip().upper() == normalized_market
            ]

        scanned = len(symbols)
        enqueued = 0
        skipped_fresh = 0
        skipped_budget = 0

        logger.info(
            f"[{_AGENT_DISPLAY}] {scan_label}: 取得 {scanned} 個不重複標的"
        )

        for item in symbols:
            symbol = item.get("symbol", "")
            market = item.get("market", "TW")

            if not symbol:
                continue

            # 檢查是否有近期報告
            if self._has_recent_report(symbol, market, hours=_REPORT_FRESHNESS_HOURS):
                skipped_fresh += 1
                continue

            # 檢查預算
            can_proceed, reason = self._budget_guard.can_proceed(
                estimated_calls=_ESTIMATED_CALLS_PER_STOCK
            )
            if not can_proceed:
                skipped_budget += 1
                logger.debug(
                    f"[{_AGENT_DISPLAY}] {scan_label}: 跳過 {symbol}（預算不足）"
                )
                continue

            # 入隊
            job_id = self._task_queue.enqueue(
                job_type="analyze_stock",
                payload={
                    "symbol": symbol,
                    "market": market,
                    "triggered_by": scan_label,
                },
                priority=priority,
            )
            if job_id:
                enqueued += 1

        duration_ms = int((time.time() - start) * 1000)

        result = {
            "scanned": scanned,
            "enqueued": enqueued,
            "skipped_fresh": skipped_fresh,
            "skipped_budget": skipped_budget,
            "market_filter": normalized_market or None,
        }

        logger.info(
            f"[{_AGENT_DISPLAY}] {scan_label} 完成: "
            f"掃描 {scanned}，入隊 {enqueued}，"
            f"已有報告 {skipped_fresh}，預算不足 {skipped_budget}"
        )

        log_agent_action(
            agent_name="ceo_agent",
            report_id=None,
            status="success",
            action=scan_label.replace(" ", "_"),
            duration_ms=duration_ms,
            metadata=result,
        )

        return result

    # ═════════════════════════════════════════════════════════
    # 部門 Agent 執行（帶異常隔離）
    # ═════════════════════════════════════════════════════════

    def _run_dept_safe(self, dept_name: str, **kwargs) -> dict:
        """
        安全執行單一部門 Agent。

        無論 Agent 內部發生什麼錯誤（ImportError / AttributeError /
        Gemini 失敗 / 解析失敗），都不會向上拋出例外，而是回傳一個
        包含 status="error" 的 dict。

        Args:
            dept_name: 部門名稱（technical / fundamental / chips /
                       event / macro / sentiment）
            **kwargs:  傳給部門 Agent.analyze() 的參數

        Returns:
            部門分析結果 dict，或 {"status": "error", "error": str}
        """
        try:
            agent = self._get_dept_agent(dept_name)
            if agent is None:
                return {"status": "error", "error": f"{dept_name} agent 無法載入"}
            return agent.analyze(**kwargs)
        except Exception as e:
            logger.error(
                f"[{_AGENT_DISPLAY}] {dept_name} 部門分析例外: {e}",
                exc_info=True,
            )
            return {"status": "error", "error": str(e)}

    def _get_dept_agent(self, dept_name: str) -> Optional[Any]:
        """
        延遲載入並快取部門 Agent 實例。

        首次存取時才匯入模組並建立實例，後續直接從快取取得。
        Thread-safe。

        Args:
            dept_name: 部門名稱

        Returns:
            Agent 實例，或 None（匯入失敗時）
        """
        with self._agents_lock:
            if dept_name in self._agents:
                return self._agents[dept_name]

        # 在鎖外做匯入（匯入可能耗時）
        agent = None
        try:
            if dept_name == "technical":
                from backend.agents.departments.technical import TechnicalAgent
                agent = TechnicalAgent()
            elif dept_name == "fundamental":
                from backend.agents.departments.fundamental import FundamentalAgent
                agent = FundamentalAgent()
            elif dept_name == "chips":
                from backend.agents.departments.chips import ChipsAgent
                agent = ChipsAgent()
            elif dept_name == "event":
                from backend.agents.departments.event import EventAgent
                agent = EventAgent()
            elif dept_name == "macro":
                from backend.agents.departments.macro import MacroAgent
                agent = MacroAgent()
            elif dept_name == "sentiment":
                from backend.agents.departments.sentiment import SentimentAgent
                agent = SentimentAgent()
            else:
                logger.error(f"[{_AGENT_DISPLAY}] 未知部門: {dept_name}")
                return None
        except ImportError as e:
            logger.error(
                f"[{_AGENT_DISPLAY}] 無法匯入 {dept_name} Agent: {e}"
            )
            return None

        with self._agents_lock:
            # 雙重檢查：另一個執行緒可能在我們匯入期間已建立
            if dept_name not in self._agents:
                self._agents[dept_name] = agent
            return self._agents[dept_name]

    # ═════════════════════════════════════════════════════════
    # 仲裁 & 首席分析師
    # ═════════════════════════════════════════════════════════

    def _run_arbitration(
        self, dept_results: dict[str, dict], report_id: str
    ) -> dict:
        """
        執行矛盾仲裁。

        Args:
            dept_results: 六部門的分析結果
            report_id:    關聯報告 UUID

        Returns:
            仲裁結果 dict（失敗時回傳含預設值的 skeleton）
        """
        try:
            from backend.agents.arbitrator import ArbitratorAgent
            arbitrator = ArbitratorAgent()
            arb_result = arbitrator.arbitrate(
                technical=dept_results.get("technical", {}),
                fundamental=dept_results.get("fundamental", {}),
                chips=dept_results.get("chips", {}),
                event=dept_results.get("event", {}),
                macro=dept_results.get("macro", {}),
                sentiment=dept_results.get("sentiment", {}),
                report_id=report_id,
            )
            return arb_result
        except Exception as e:
            logger.error(
                f"[{_AGENT_DISPLAY}] 仲裁失敗: {e}", exc_info=True
            )
            return {
                "status": "failed",
                "final_stance": "neutral",
                "stance_confidence": 0.3,
                "arbitration_summary": f"仲裁失敗: {str(e)[:100]}",
                "key_risks": ["仲裁系統異常，報告可信度降低"],
                "key_catalysts": [],
                "conflicts_detected": [],
                "aligned_signals": [],
                "missing_depts": [],
                "model_used": "none",
            }

    def _run_chief_analyst(
        self,
        symbol: str,
        market: str,
        company_name: str,
        industry: str,
        current_price: float,
        dept_results: dict[str, dict],
        arb_result: dict,
        report_id: str,
    ) -> dict:
        """
        執行首席分析師報告生成。

        Args:
            symbol:       股票代號
            market:       市場
            company_name: 公司名稱
            industry:     產業別
            current_price: 目前股價
            dept_results:  六部門分析結果
            arb_result:    仲裁結果
            report_id:     報告 UUID

        Returns:
            首席分析師輸出 dict
        """
        try:
            from backend.agents.chief_analyst import ChiefAnalystAgent
            chief = ChiefAnalystAgent()
            return chief.generate_report(
                symbol=symbol,
                market=market,
                company_name=company_name,
                industry=industry,
                current_price=current_price,
                technical=dept_results.get("technical", {}),
                fundamental=dept_results.get("fundamental", {}),
                chips=dept_results.get("chips", {}),
                event=dept_results.get("event", {}),
                macro=dept_results.get("macro", {}),
                sentiment=dept_results.get("sentiment", {}),
                arbitration=arb_result,
                report_id=report_id,
            )
        except Exception as e:
            logger.error(
                f"[{_AGENT_DISPLAY}] 首席分析師失敗: {e}", exc_info=True
            )
            return {
                "status": "failed",
                "error": str(e),
                "report_id": report_id,
                "final_report": None,
                "rating": None,
                "target_price_low": None,
                "target_price_high": None,
                "confidence_score": 0.3,
                "prediction_ids": [],
                "model_used": "none",
                "duration_ms": 0,
                "total_gemini_calls": 0,
            }

    # ═════════════════════════════════════════════════════════
    # 自選股清單相關
    # ═════════════════════════════════════════════════════════

    def _get_watchlist_symbols(self) -> list[dict]:
        """
        從 user_prefs 表取得所有使用者的自選股，去重後回傳。

        user_prefs.watchlist 是 JSONB 陣列，每個元素格式：
        {"symbol": "2330", "market": "TW"}

        Returns:
            去重後的 [{"symbol": str, "market": str}, ...]
        """
        try:
            from backend.data.storage.supabase_client import get_client
            client = get_client()
            if not client:
                logger.warning(
                    f"[{_AGENT_DISPLAY}] Supabase 不可用，無法取得自選股"
                )
                return []

            result = (
                client.table("user_prefs")
                .select("watchlist")
                .execute()
            )
            rows = result.data or []
        except Exception as e:
            logger.error(f"[{_AGENT_DISPLAY}] 查詢 user_prefs 失敗: {e}")
            return []

        # 去重
        seen: set[str] = set()
        unique_symbols: list[dict] = []

        for row in rows:
            watchlist = row.get("watchlist")
            if not watchlist:
                continue

            # watchlist 可能是 str（JSON）或已解析的 list
            if isinstance(watchlist, str):
                try:
                    watchlist = json.loads(watchlist)
                except (json.JSONDecodeError, TypeError):
                    continue

            if not isinstance(watchlist, list):
                continue

            for item in watchlist:
                if not isinstance(item, dict):
                    continue
                symbol = item.get("symbol", "").strip()
                market = item.get("market", "TW").strip()
                if not symbol:
                    continue

                key = f"{symbol}:{market}"
                if key not in seen:
                    seen.add(key)
                    unique_symbols.append({"symbol": symbol, "market": market})

        return unique_symbols

    def _has_recent_report(
        self, symbol: str, market: str, hours: int = _REPORT_FRESHNESS_HOURS
    ) -> bool:
        """
        檢查指定股票是否有最近 N 小時內的報告。

        Args:
            symbol: 股票代號
            market: 市場
            hours:  新鮮度閾值（小時）

        Returns:
            True = 已有最近報告，不需重新分析
        """
        try:
            from backend.data.storage.supabase_client import get_client
            client = get_client()
            if not client:
                return False

            cutoff = (
                datetime.now(timezone.utc) - timedelta(hours=hours)
            ).isoformat()

            result = (
                client.table("reports")
                .select("id", count="exact")
                .eq("symbol", symbol)
                .eq("market", market)
                .gte("created_at", cutoff)
                .limit(1)
                .execute()
            )
            return (result.count or 0) > 0

        except Exception as e:
            logger.debug(
                f"[{_AGENT_DISPLAY}] _has_recent_report 查詢失敗: {e}"
            )
            # 查詢失敗時保守回傳 False（允許重新分析）
            return False

    def _has_pending_job(self, job_type: str) -> bool:
        """
        檢查 TaskQueue 中是否已有指定類型的 pending 工作。

        Args:
            job_type: 工作類型（如 "run_backtest"）

        Returns:
            True = 已有 pending 工作
        """
        try:
            from backend.data.storage.supabase_client import get_client
            client = get_client()
            if not client:
                return False

            result = (
                client.table("job_queue")
                .select("id", count="exact")
                .eq("job_type", job_type)
                .eq("status", "pending")
                .limit(1)
                .execute()
            )
            return (result.count or 0) > 0

        except Exception as e:
            logger.debug(
                f"[{_AGENT_DISPLAY}] _has_pending_job 查詢失敗: {e}"
            )
            return False

    # ═════════════════════════════════════════════════════════
    # 資料取得（防呆，模組可能不存在）
    # ═════════════════════════════════════════════════════════

    def _fetch_price_data(self, symbol: str, market: str) -> dict:
        """
        取得股票價格資料（OHLCV + 技術指標）。

        台股用 FinMind 為主，Yahoo 為備；美股用 FinMind 嘗試後 fallback Yahoo。

        Args:
            symbol: 股票代號
            market: 市場

        Returns:
            價格資料 dict，取得失敗時回傳空 dict
        """
        # 台股優先 FinMind
        if market in ("TW", "TWO"):
            try:
                from backend.data.sources.finmind import get_price_data as fm_price
                data = fm_price(symbol, days=120)
                if data and data.get("closes") and not data.get("error"):
                    return data
            except Exception as e:
                logger.debug(f"[{_AGENT_DISPLAY}] FinMind 價格失敗: {e}")

        # Fallback Yahoo
        try:
            from backend.data.sources.yahoo import get_price_data
            data = get_price_data(symbol, market)
            if data:
                return data
        except Exception as e:
            logger.warning(
                f"[{_AGENT_DISPLAY}] 取得 {symbol} 價格資料失敗: {e}"
            )
        return {}

    def _fetch_fundamental_data(self, symbol: str, market: str) -> dict:
        """
        取得股票基本面資料（EPS / 營收 / 比率等）。

        台股用 FinMind 為主（PER/PBR/營收），Yahoo 為備。

        Args:
            symbol: 股票代號
            market: 市場

        Returns:
            基本面資料 dict，取得失敗時回傳空 dict
        """
        # 台股優先 FinMind
        if market in ("TW", "TWO"):
            try:
                from backend.data.sources.finmind import get_fundamentals
                data = get_fundamentals(symbol)
                if data and (data.get("per") or data.get("name") != symbol):
                    return data
            except Exception as e:
                logger.debug(f"[{_AGENT_DISPLAY}] FinMind 基本面失敗: {e}")

        # Fallback Yahoo
        try:
            from backend.data.sources.yahoo import get_info
            data = get_info(symbol, market)
            if data:
                return data
        except Exception as e:
            logger.warning(
                f"[{_AGENT_DISPLAY}] 取得 {symbol} 基本面資料失敗: {e}"
            )
        return {}

    def _fetch_chips_data(self, symbol: str, market: str) -> dict:
        """
        取得籌碼資料（三大法人 / 融資融券等）。

        台股使用 FinMind，美股可能暫無籌碼來源。

        Args:
            symbol: 股票代號
            market: 市場

        Returns:
            籌碼資料 dict，取得失敗時回傳空 dict
        """
        # 台股使用 FinMind 籌碼資料
        if market in ("TW", "TWO"):
            try:
                from backend.data.sources.finmind import get_chips_data
                data = get_chips_data(symbol)
                if data:
                    return data
            except ImportError:
                logger.debug(
                    f"[{_AGENT_DISPLAY}] finmind.get_chips_data 尚未實作"
                )
            except Exception as e:
                logger.warning(
                    f"[{_AGENT_DISPLAY}] 取得 {symbol} 籌碼資料失敗: {e}"
                )

        # 美股暫無籌碼來源，回傳空 dict
        return {}

    # ═════════════════════════════════════════════════════════
    # 公司資訊輔助
    # ═════════════════════════════════════════════════════════

    @staticmethod
    def _get_company_name(
        symbol: str, market: str, fundamental_data: dict
    ) -> str:
        """從基本面資料或預設值取得公司名稱。"""
        if fundamental_data:
            for key in ("company_name", "name", "shortName", "longName"):
                name = fundamental_data.get(key)
                if name:
                    return str(name)

        # 預設：代號本身
        suffix = ".TW" if market == "TW" else ""
        return f"{symbol}{suffix}"

    @staticmethod
    def _get_industry(
        symbol: str, market: str, fundamental_data: dict
    ) -> str:
        """從基本面資料或預設值取得產業別。"""
        if fundamental_data:
            for key in ("industry", "sector", "industryCategory"):
                ind = fundamental_data.get(key)
                if ind:
                    return str(ind)
        return "未知產業"

    @staticmethod
    def _get_current_price(
        symbol: str, market: str, price_data: dict
    ) -> float:
        """從價格資料取得最新收盤價。"""
        if price_data:
            # 嘗試多種可能的 key
            for key in ("close", "current_price", "last_close", "price"):
                val = price_data.get(key)
                if isinstance(val, (int, float)) and val > 0:
                    return float(val)

            # 嘗試從 OHLCV 歷史取最後一筆
            history = price_data.get("history") or price_data.get("data")
            if isinstance(history, list) and history:
                last = history[-1]
                if isinstance(last, dict):
                    close = last.get("close") or last.get("Close")
                    if isinstance(close, (int, float)) and close > 0:
                        return float(close)

        return 0.0

    # ═════════════════════════════════════════════════════════
    # 報告寫入 Supabase
    # ═════════════════════════════════════════════════════════

    def _save_report_to_db(
        self,
        report_id: str,
        symbol: str,
        market: str,
        dept_outputs: dict[str, dict],
        arb_result: dict,
        chief_result: dict,
        user_id: Optional[str] = None,
        gemini_calls: int = 0,
        duration_ms: int = 0,
    ) -> bool:
        """
        將完整分析結果寫入 Supabase reports 表。

        各部門的 JSONB 輸出中移除以 _ 開頭的內部 meta 欄位
        （如 _model_used, _duration_ms），避免寫入冗餘資料。

        Args:
            report_id:    報告 UUID
            symbol:       股票代號
            market:       市場
            dept_outputs: 六部門分析結果
            arb_result:   仲裁結果
            chief_result: 首席分析師結果
            user_id:      觸發使用者（排程觸發時為 None）
            gemini_calls: 總 Gemini 呼叫次數
            duration_ms:  Pipeline 總耗時

        Returns:
            True = 寫入成功
        """
        try:
            from backend.data.storage.supabase_client import insert_row

            # final_report 是 NOT NULL 欄位，若為空則跳過 DB 寫入
            final_report_text = chief_result.get("final_report")
            if not final_report_text:
                logger.warning(
                    f"[{_AGENT_DISPLAY}] final_report 為空，跳過 DB 寫入: "
                    f"{symbol} [{report_id[:8]}]"
                )
                return False

            row_data = {
                "id": report_id,
                "symbol": symbol,
                "market": market,
                "report_type": "full_analysis",
                "tier": "standard",
                "technical_output": _clean_dept_output(
                    dept_outputs.get("technical", {})
                ),
                "fundamental_output": _clean_dept_output(
                    dept_outputs.get("fundamental", {})
                ),
                "chips_output": _clean_dept_output(
                    dept_outputs.get("chips", {})
                ),
                "event_output": _clean_dept_output(
                    dept_outputs.get("event", {})
                ),
                "macro_output": _clean_dept_output(
                    dept_outputs.get("macro", {})
                ),
                "sentiment_output": _clean_dept_output(
                    dept_outputs.get("sentiment", {})
                ),
                "arbitration_log": _clean_dept_output(arb_result),
                "final_report": final_report_text,
                "rating": chief_result.get("rating"),
                "target_price_low": chief_result.get("target_price_low"),
                "target_price_high": chief_result.get("target_price_high"),
                "confidence_score": chief_result.get("confidence_score"),
                "total_gemini_calls": gemini_calls,
                "total_tokens": 0,  # token 計數待後續整合
                "generation_time_ms": duration_ms,
                "triggered_by": "ceo_agent",
                "user_id": user_id,
            }

            # 移除 None 值（Supabase 某些欄位不接受 null）
            row_data = {k: v for k, v in row_data.items() if v is not None}

            result = insert_row("reports", row_data)
            if result:
                logger.info(
                    f"[{_AGENT_DISPLAY}] 報告已寫入 DB: "
                    f"{symbol} [{report_id[:8]}]"
                )
                return True
            else:
                logger.warning(
                    f"[{_AGENT_DISPLAY}] 報告寫入 DB 失敗（Supabase 可能不可用）: "
                    f"{symbol} [{report_id[:8]}]"
                )
                return False

        except Exception as e:
            logger.error(
                f"[{_AGENT_DISPLAY}] 報告寫入 DB 例外: {e}", exc_info=True
            )
            return False


# ═════════════════════════════════════════════════════════════
# 模組級單例
# ═════════════════════════════════════════════════════════════

_ceo_instance: Optional[CEOAgent] = None
_ceo_lock = threading.Lock()


def get_ceo_agent() -> CEOAgent:
    """
    取得 CEOAgent 單例。

    Thread-safe 雙重檢查鎖定（Double-Checked Locking）。
    全域只會建立一個 CEOAgent 實例。

    Returns:
        CEOAgent 單例
    """
    global _ceo_instance
    if _ceo_instance is None:
        with _ceo_lock:
            if _ceo_instance is None:
                _ceo_instance = CEOAgent()
    return _ceo_instance


# ═════════════════════════════════════════════════════════════
# 模組級輔助函式
# ═════════════════════════════════════════════════════════════

def _clean_dept_output(output: dict) -> dict:
    """
    清理部門輸出，移除以 _ 開頭的內部 meta 欄位。

    這些欄位（如 _model_used, _duration_ms）是 Agent 內部使用的，
    不應寫入 Supabase JSONB 欄位。

    Args:
        output: 部門輸出 dict

    Returns:
        清理後的 dict
    """
    if not isinstance(output, dict):
        return {}
    return {k: v for k, v in output.items() if not k.startswith("_")}


def _truncate_str(text: str, max_len: int = 200) -> str:
    """截斷字串到指定長度。"""
    if len(text) <= max_len:
        return text
    return text[:max_len - 3] + "..."
