"""
backend/core/heartbeat.py
APScheduler 排程心跳

排程表（交易日 = 週一至週五，時區 Asia/Taipei）：
  08:00          → 盤前掃描 — TOP 500 + 全體使用者自選股（最高優先級）
  12:00          → 盤中掃描 — TOP 500 + 全體使用者自選股
  13:40          → 盤後掃描 — TOP 500 + 全體使用者自選股 + 盤後總結
  21:00          → 美股盤前 — 美股藍籌 + 使用者自選股中的美股

持續補充（24/7，不限交易日）：
  每 10 分鐘     → 持續補充 — round-robin 循環 TOP 500，補充沒有近期報告的股票

週期維護：
  週一 07:00      → ceo.weekly_backtest
  每6小時         → ceo.storage_check
  每日 00:01      → 重置 BudgetGuard 計數器

持續處理：
  每 5 分鐘      → 處理排隊工作（max 5 jobs/run）

特殊：
  伺服器啟動      → 啟動掃描（TOP 500 中沒有近期報告的股票）

設計：
- 使用 BackgroundScheduler，不阻斷主執行緒
- timezone 固定為 Asia/Taipei
- 所有 job 失敗時只 log，不讓 scheduler 崩潰
- start_heartbeat() 回傳 scheduler 實例，供 main.py lifespan 管理
- TOP 500 動態取得：從 FinMind 抓取台股完整清單，取前 500 檔
- 24/7 持續補充：靠 BudgetGuard 控制每日 Gemini RPD（預設 130/天）
"""
import logging
import threading
import time
import re
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger

logger = logging.getLogger(__name__)

_TZ = "Asia/Taipei"

# 快取 TOP 500 清單（每日更新一次）
_top500_cache: list[tuple[str, str]] = []
_top500_cache_ts: float = 0
_TOP500_CACHE_TTL = 86400  # 24 小時

# 持續補充 round-robin cursor（跨次呼叫保持位置）
_fill_cursor: int = 0

# 佇列處理器鎖（確保同時只有一個處理執行緒在跑）
_queue_processor_lock = threading.Lock()

# 美股藍籌（固定清單）
_US_BLUE_CHIPS = [
    ("AAPL",  "US"),  # Apple
    ("NVDA",  "US"),  # NVIDIA
    ("MSFT",  "US"),  # Microsoft
    ("GOOG",  "US"),  # Google
    ("AMZN",  "US"),  # Amazon
    ("META",  "US"),  # Meta
    ("TSLA",  "US"),  # Tesla
    ("TSM",   "US"),  # 台積電 ADR
    ("AVGO",  "US"),  # Broadcom
    ("AMD",   "US"),  # AMD
]

# Fallback 台股權值股（FinMind 無法連線時使用）
_TW_FALLBACK = [
    "2330", "2317", "2454", "2308", "2881", "2882", "2891", "2303",
    "2412", "3711", "2886", "1301", "2002", "1303", "2884", "3008",
    "2892", "2382", "6505", "2880", "2603", "3037", "2345", "2379",
    "3034", "2301", "1216", "2327", "2357", "5880", "2885", "2883",
    "3045", "2912", "1326", "2395", "5871", "6669", "4904", "2207",
    "2409", "3231", "2801", "9910", "2615", "1101", "2408", "3443",
]


# ─── TOP 500 動態取得 ─────────────────────────────────────────────

def _get_top500() -> list[tuple[str, str]]:
    """
    從 FinMind 取得台股完整清單，篩選出 TOP 500 檔。

    篩選邏輯：
    1. 從 FinMind TaiwanStockInfo 取全量股票
    2. 只保留 4 位數字代號（過濾 ETF、權證、特殊代碼）
    3. 依代號排序（較小代號 ≈ 較大市值，合理近似）
    4. 取前 500 檔

    快取 24 小時，避免頻繁呼叫 FinMind。
    """
    global _top500_cache, _top500_cache_ts

    now = time.time()
    if _top500_cache and (now - _top500_cache_ts) < _TOP500_CACHE_TTL:
        return _top500_cache

    try:
        from backend.data.sources.finmind import get_stock_info
        all_stocks = get_stock_info()

        if not all_stocks:
            raise ValueError("FinMind 回傳空清單")

        # 篩選：只要 4 位數字代號（一般上市股票）
        tw_stocks = []
        for s in all_stocks:
            symbol = s.get("symbol", "")
            if re.match(r"^\d{4}$", symbol):
                tw_stocks.append(symbol)

        # 排序（較小代號 ≈ 較大市值）
        tw_stocks.sort(key=lambda x: int(x))

        # 取前 500
        top500 = [(sym, "TW") for sym in tw_stocks[:500]]

        logger.info(
            "[Heartbeat] TOP 500 清單更新: 篩選出 %d 檔（全量 %d 檔）",
            len(top500), len(all_stocks),
        )

        _top500_cache = top500
        _top500_cache_ts = now
        return top500

    except Exception as e:
        logger.warning(f"[Heartbeat] FinMind 取 TOP 500 失敗，使用 fallback: {e}")
        fallback = [(sym, "TW") for sym in _TW_FALLBACK]
        _top500_cache = fallback
        _top500_cache_ts = now
        return fallback


def _get_full_scan_list() -> list[tuple[str, str]]:
    """取得完整掃描清單：TOP 500 台股 + 美股藍籌 + 使用者自選股。"""
    symbols: dict[str, str] = {}  # key: "SYMBOL:MARKET", value: market

    # 1. TOP 500 台股
    for sym, mkt in _get_top500():
        symbols[f"{sym}:{mkt}"] = mkt

    # 2. 美股藍籌
    for sym, mkt in _US_BLUE_CHIPS:
        symbols[f"{sym}:{mkt}"] = mkt

    # 3. 所有使用者自選股（可能包含不在 TOP 500 的股票）
    try:
        from backend.agents.ceo_agent import get_ceo_agent
        ceo = get_ceo_agent()
        watchlist = ceo._get_watchlist_symbols()
        for item in watchlist:
            sym = item.get("symbol", "")
            mkt = item.get("market", "TW")
            if sym:
                symbols[f"{sym}:{mkt}"] = mkt
    except Exception as e:
        logger.warning(f"[Heartbeat] 取得使用者自選股失敗: {e}")

    # 轉回 list[tuple]
    result = [(key.split(":")[0], key.split(":")[1]) for key in symbols]
    return result


# ─── Job 包裝函式（捕捉例外，確保 scheduler 不崩潰）──────────────

def _job_full_scan(scan_label: str, priority: int = 5, max_jobs: int = 20) -> None:
    """
    全市場兩階段掃描：TOP 500 → 本地過濾 → NVIDIA 評分 → 入隊 Top 20。

    階段 A（0 API）：本地規則過濾（RSI/量/漲跌幅/均線/籌碼）
                    ~500 支 → 50-150 支候選
    階段 B（NVIDIA）：每支候選用 1 次 NVIDIA 快速評分（score 1-10）
                    取評分最高的 20 支
    階段 C：將 Top 20 入隊進行完整分析（1 Gemini + 8 NVIDIA per 支）

    注意：不再直接對所有 500 支執行完整分析管線。
    """
    try:
        from backend.agents.ceo_agent import get_ceo_agent
        from backend.core.market_filter import filter_candidates, score_candidates_with_nvidia

        ceo = get_ceo_agent()
        scan_list = _get_full_scan_list()

        logger.info(
            "[Heartbeat] %s（兩階段）: 開始掃描 %d 檔股票...",
            scan_label, len(scan_list),
        )

        # ── 階段 A: 批次取得價格資料 ──────────────────────
        price_map: dict[str, dict] = {}
        chips_map: dict[str, dict] = {}

        try:
            from backend.data.sources.finmind import (
                get_price_data as fm_price,
                get_chips_data as fm_chips,
            )
            tw_symbols = [s for s, m in scan_list if m in ("TW", "TWO")]

            for symbol in tw_symbols[:200]:  # 分批取，避免過載
                try:
                    price_map[symbol] = fm_price(symbol, days=65)
                    chips_map[symbol] = fm_chips(symbol, days=10)
                except Exception:
                    pass  # 單支失敗不影響整體

        except Exception as e:
            logger.warning(f"[Heartbeat] {scan_label} 批次取價格資料失敗: {e}")

        # ── 階段 A: 本地規則過濾（0 API）─────────────────
        if price_map:
            candidates = filter_candidates(
                stocks=scan_list,
                price_map=price_map,
                chips_map=chips_map if chips_map else None,
                max_candidates=150,
            )
        else:
            # 無價格資料時降級：直接用全部清單（舊邏輯）
            logger.warning(
                f"[Heartbeat] {scan_label} 無價格資料，降級為直接掃描前 {max_jobs} 支"
            )
            candidates = [
                {"symbol": s, "market": m, "signals": [], "signal_count": 0}
                for s, m in scan_list[:50]
            ]

        logger.info(
            "[Heartbeat] %s 階段A完成: %d 支候選",
            scan_label, len(candidates),
        )

        # ── 階段 B: NVIDIA 快速評分 ───────────────────────
        # 過濾掉已有近期報告的
        fresh_filtered = [
            c for c in candidates
            if not ceo._has_recent_report(c["symbol"], c["market"], hours=4)
        ]

        if fresh_filtered:
            top_stocks = score_candidates_with_nvidia(
                fresh_filtered, max_top=max_jobs
            )
            logger.info(
                "[Heartbeat] %s 階段B完成: NVIDIA 評分 %d 支，取 Top %d",
                scan_label, len(fresh_filtered), len(top_stocks),
            )
        else:
            top_stocks = []
            logger.info(f"[Heartbeat] {scan_label} 所有候選都有近期報告，跳過")

        # ── 階段 C: 入隊完整分析 ──────────────────────────
        enqueued = 0
        for stock in top_stocks:
            from backend.core.budget_guard import get_budget_guard
            can_proceed, _ = get_budget_guard().can_proceed(estimated_calls=1)
            if not can_proceed:
                logger.warning(f"[Heartbeat] {scan_label} 預算不足，停止入隊")
                break

            job_id = ceo._task_queue.enqueue(
                job_type="analyze_stock",
                payload={
                    "symbol":       stock["symbol"],
                    "market":       stock["market"],
                    "triggered_by": scan_label,
                    "scanner_score": stock.get("score"),
                    "scanner_signals": stock.get("signals", []),
                },
                priority=priority,
            )
            if job_id:
                enqueued += 1

        logger.info(
            "[Heartbeat] %s 入隊完成: %d 支已入隊，由佇列處理器執行",
            scan_label, enqueued,
        )

    except Exception as e:
        logger.error(f"[Heartbeat] {scan_label} 失敗: {e}", exc_info=True)


def _job_premarket() -> None:
    """盤前掃描（08:00）— 最高優先級"""
    _job_full_scan("盤前掃描", priority=1, max_jobs=20)


def _job_midday() -> None:
    """盤中掃描（12:00）— 一般優先級"""
    _job_full_scan("盤中掃描", priority=5, max_jobs=20)


def _job_postmarket() -> None:
    """盤後掃描（13:40）— 一般優先級 + 盤後總結"""
    _job_full_scan("盤後掃描", priority=5, max_jobs=20)
    try:
        from backend.agents.ceo_agent import get_ceo_agent
        get_ceo_agent().postmarket_summary()
    except Exception as e:
        logger.error(f"[Heartbeat] 盤後總結失敗: {e}", exc_info=True)


def _job_us_premarket() -> None:
    """美股盤前掃描（21:00）— 只掃美股"""
    try:
        from backend.agents.ceo_agent import get_ceo_agent
        ceo = get_ceo_agent()

        enqueued = 0
        for symbol, market in _US_BLUE_CHIPS:
            if not ceo._has_recent_report(symbol, market, hours=8):
                job_id = ceo._task_queue.enqueue(
                    job_type="analyze_stock",
                    payload={"symbol": symbol, "market": market, "triggered_by": "美股盤前"},
                    priority=3,
                )
                if job_id:
                    enqueued += 1

        # 加上使用者自選的美股
        watchlist = ceo._get_watchlist_symbols()
        for item in watchlist:
            if item.get("market") == "US":
                sym = item.get("symbol", "")
                if sym and not ceo._has_recent_report(sym, "US", hours=8):
                    job_id = ceo._task_queue.enqueue(
                        job_type="analyze_stock",
                        payload={"symbol": sym, "market": "US", "triggered_by": "美股盤前"},
                        priority=3,
                    )
                    if job_id:
                        enqueued += 1

        logger.info("[Heartbeat] 美股盤前掃描: 入隊 %d 檔", enqueued)

    except Exception as e:
        logger.error(f"[Heartbeat] 美股盤前掃描失敗: {e}", exc_info=True)


def _job_weekly_backtest() -> None:
    try:
        from backend.agents.ceo_agent import get_ceo_agent
        get_ceo_agent().weekly_backtest()
    except Exception as e:
        logger.error(f"[Heartbeat] weekly_backtest 失敗: {e}", exc_info=True)


def _job_storage_check() -> None:
    try:
        from backend.agents.ceo_agent import get_ceo_agent
        get_ceo_agent().storage_check()
    except Exception as e:
        logger.error(f"[Heartbeat] storage_check 失敗: {e}", exc_info=True)


def _job_reset_budget() -> None:
    """每日凌晨重置 BudgetGuard。"""
    try:
        from backend.core.budget_guard import get_budget_guard
        get_budget_guard().reset()
        logger.info("[Heartbeat] BudgetGuard 每日計數器已重置")
    except Exception as e:
        logger.error(f"[Heartbeat] budget_reset 失敗: {e}", exc_info=True)


def _job_startup_scan() -> None:
    """
    伺服器啟動掃描：從 TOP 500 中挑出沒有近期報告的股票掃描。
    最多處理 20 檔，避免啟動時卡太久。
    """
    try:
        from backend.data.storage.supabase_client import get_client
        client = get_client()
        if not client:
            logger.warning("[Heartbeat] 啟動掃描: DB 不可用，跳過")
            return

        from backend.agents.ceo_agent import get_ceo_agent
        ceo = get_ceo_agent()

        scan_list = _get_full_scan_list()
        enqueued = 0

        for symbol, market in scan_list:
            if enqueued >= 30:  # 啟動掃描上限
                break
            if not ceo._has_recent_report(symbol, market, hours=8):
                job_id = ceo._task_queue.enqueue(
                    job_type="analyze_stock",
                    payload={"symbol": symbol, "market": market, "triggered_by": "啟動掃描"},
                    priority=1,
                )
                if job_id:
                    enqueued += 1

        if enqueued > 0:
            logger.info("[Heartbeat] 啟動掃描: 入隊 %d 檔（TOP 500 + 自選股），由佇列處理器執行", enqueued)
        else:
            logger.info("[Heartbeat] 所有股票都有近期報告，跳過啟動掃描")

    except Exception as e:
        logger.error(f"[Heartbeat] 啟動掃描失敗: {e}", exc_info=True)


# 持續處理排隊工作（每 5 分鐘檢查一次）
def _job_process_queue() -> None:
    """
    持續處理排隊中的分析工作（非阻塞）。

    立即返回，在 daemon thread 裡執行實際工作。
    _queue_processor_lock 確保同時只有一個處理執行緒在跑，
    避免 APScheduler max_instances=1 造成後續排程被 skip。
    """
    if not _queue_processor_lock.acquire(blocking=False):
        logger.debug("[Heartbeat] 佇列處理器已在執行中，跳過本次排程")
        return

    def _process() -> None:
        try:
            from backend.agents.ceo_agent import get_ceo_agent
            ceo = get_ceo_agent()
            result = ceo.run_pending_jobs(max_jobs=2)
            processed = result.get("processed", 0)
            if processed > 0:
                logger.info(
                    "[Heartbeat] 佇列處理: 成功 %d / 失敗 %d",
                    result.get("succeeded", 0), result.get("failed", 0),
                )
        except Exception as e:
            logger.error(f"[Heartbeat] 佇列處理失敗: {e}", exc_info=True)
        finally:
            _queue_processor_lock.release()

    t = threading.Thread(target=_process, daemon=True, name="queue-processor")
    t.start()


def _job_continuous_fill() -> None:
    """
    持續補充分析隊列（每 10 分鐘，24/7，不限交易日）。

    策略：
    - Round-robin 循環 TOP 500 + 自選股清單
    - 挑選最近 6 小時內沒有報告的股票
    - 每次最多入隊 2 支（由 BudgetGuard 控制總量）
    - 優先級設為 8（低於交易時段掃描，不搶佔資源）

    預算計算：
      130 RPD/天 ÷ 24 小時 ≈ 5.4 支/小時
      每 10 分鐘 × 2 支 = 12 支/小時（BudgetGuard 超限時自動停止）
    """
    global _fill_cursor
    try:
        from backend.core.budget_guard import get_budget_guard
        guard = get_budget_guard()

        # 先確認今日預算還有餘額
        can_proceed, reason = guard.can_proceed(estimated_calls=1)
        if not can_proceed:
            logger.debug(f"[Heartbeat] 持續補充: 預算不足，跳過（{reason}）")
            return

        from backend.agents.ceo_agent import get_ceo_agent
        ceo = get_ceo_agent()

        stock_list = _get_full_scan_list()
        if not stock_list:
            logger.warning("[Heartbeat] 持續補充: 股票清單為空，跳過")
            return

        total = len(stock_list)
        enqueued = 0
        checked = 0

        # 從 cursor 位置開始，最多掃描完整一輪（找到 2 個或掃完全部為止）
        while enqueued < 2 and checked < total:
            idx = _fill_cursor % total
            symbol, market = stock_list[idx]
            _fill_cursor = (idx + 1) % total
            checked += 1

            # 跳過最近 6 小時內已有報告的
            if ceo._has_recent_report(symbol, market, hours=6):
                continue

            # 每支入隊前再確認預算（多 agent 並行時避免超額）
            can_proceed, _ = guard.can_proceed(estimated_calls=1)
            if not can_proceed:
                break

            job_id = ceo._task_queue.enqueue(
                job_type="analyze_stock",
                payload={
                    "symbol":       symbol,
                    "market":       market,
                    "triggered_by": "持續補充",
                },
                priority=8,  # 低優先級，讓交易時段掃描優先
            )
            if job_id:
                enqueued += 1

        if enqueued > 0:
            logger.info(
                "[Heartbeat] 持續補充: 入隊 %d 支（cursor=%d/%d）",
                enqueued, _fill_cursor, total,
            )

    except Exception as e:
        logger.error(f"[Heartbeat] 持續補充失敗: {e}", exc_info=True)


# ─── 啟動函式 ─────────────────────────────────────────────────────

def start_heartbeat() -> BackgroundScheduler:
    """
    建立並啟動 APScheduler 排程器。

    排程表：
    ── 交易時段（週一至週五）────────────────────────────────
    - 08:00  盤前掃描（TOP 500 + 自選股，最高優先級 1）
    - 12:00  盤中掃描（TOP 500 + 自選股，優先級 5）
    - 13:40  盤後掃描 + 盤後總結（優先級 5）
    - 21:00  美股盤前掃描（優先級 3）

    ── 持續補充（24/7）────────────────────────────────────
    - 每 10 分鐘  持續補充（round-robin TOP 500，每次 2 支，優先級 8）
                 靠 BudgetGuard 控制 Gemini RPD（預設 130/天）

    ── 佇列處理（24/7）────────────────────────────────────
    - 每 5 分鐘  處理排隊工作（max 5 jobs/run）

    ── 週期維護 ───────────────────────────────────────────
    - 週一 07:00  準確率回測
    - 每 6 小時   儲存管理
    - 每日 00:01  預算重置

    Returns:
        BackgroundScheduler 實例
    """
    scheduler = BackgroundScheduler(timezone=_TZ)

    # ── 交易日三段掃描（週一至週五）─────────────────────

    # 08:00 — 盤前全市場掃描（最高優先級）
    scheduler.add_job(
        _job_premarket,
        CronTrigger(day_of_week="mon-fri", hour=8, minute=0, timezone=_TZ),
        id="premarket_scan",
        replace_existing=True,
        misfire_grace_time=1800,
    )

    # 12:00 — 盤中掃描
    scheduler.add_job(
        _job_midday,
        CronTrigger(day_of_week="mon-fri", hour=12, minute=0, timezone=_TZ),
        id="midday_scan",
        replace_existing=True,
        misfire_grace_time=1800,
    )

    # 13:40 — 盤後掃描 + 盤後總結
    scheduler.add_job(
        _job_postmarket,
        CronTrigger(day_of_week="mon-fri", hour=13, minute=40, timezone=_TZ),
        id="postmarket_scan",
        replace_existing=True,
        misfire_grace_time=1800,
    )

    # 21:00 — 美股盤前掃描
    scheduler.add_job(
        _job_us_premarket,
        CronTrigger(day_of_week="mon-fri", hour=21, minute=0, timezone=_TZ),
        id="us_premarket_scan",
        replace_existing=True,
        misfire_grace_time=1800,
    )

    # ── 持續補充（每 10 分鐘，24/7）────────────────────
    # Round-robin 循環 TOP 500，補充沒有近期報告的股票
    # 靠 BudgetGuard 自動限制 Gemini RPD（預設 130/天）

    scheduler.add_job(
        _job_continuous_fill,
        CronTrigger(minute="*/10", timezone=_TZ),
        id="continuous_fill",
        replace_existing=True,
        misfire_grace_time=600,
    )

    # ── 持續處理排隊工作（每 5 分鐘）────────────────────

    scheduler.add_job(
        _job_process_queue,
        CronTrigger(minute="*/5", timezone=_TZ),
        id="process_queue",
        replace_existing=True,
        misfire_grace_time=300,
    )

    # ── 週期性維護 ──────────────────────────────────────

    # 每週一 07:00：準確率回測
    scheduler.add_job(
        _job_weekly_backtest,
        CronTrigger(day_of_week="mon", hour=7, minute=0, timezone=_TZ),
        id="weekly_backtest",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    # 每 6 小時：儲存管理檢查
    scheduler.add_job(
        _job_storage_check,
        CronTrigger(hour="0,6,12,18", minute=0, timezone=_TZ),
        id="storage_check",
        replace_existing=True,
        misfire_grace_time=1800,
    )

    # 每日 00:01：預算計數器重置
    scheduler.add_job(
        _job_reset_budget,
        CronTrigger(hour=0, minute=1, timezone=_TZ),
        id="budget_reset",
        replace_existing=True,
        misfire_grace_time=600,
    )

    # ── 伺服器啟動掃描（延遲 15 秒）───────────────────
    from datetime import datetime, timedelta
    import pytz
    tz = pytz.timezone(_TZ)
    run_at = datetime.now(tz) + timedelta(seconds=15)
    scheduler.add_job(
        _job_startup_scan,
        DateTrigger(run_date=run_at, timezone=_TZ),
        id="startup_scan",
        replace_existing=True,
        misfire_grace_time=120,
    )

    scheduler.start()
    logger.info(
        "[Heartbeat] 排程器啟動完成，共 %d 個 job（含啟動掃描）\n"
        "  交易日掃描: 08:00 盤前 | 12:00 盤中 | 13:40 盤後 | 21:00 美股\n"
        "  持續補充(24/7): 每 10 分鐘 round-robin TOP 500（BudgetGuard 控制）\n"
        "  佇列處理: 每 5 分鐘 | 掃描範圍: TOP 500 + 自選股",
        len(scheduler.get_jobs()),
    )

    return scheduler
