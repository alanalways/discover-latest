"""
backend/core/heartbeat.py
APScheduler 排程心跳（Sonnet 撰寫）

排程表（交易日 = 週一至週五，時區 Asia/Taipei）：
  09:10          → 台股開盤後首次掃描 + run_pending_jobs
  12:00          → 午盤掃描 + run_pending_jobs
  13:35          → 台股收盤後掃描 + postmarket_summary
  週一 07:00      → ceo.weekly_backtest
  每6小時         → ceo.storage_check
  每日 00:01      → 重置 BudgetGuard 計數器

特殊：
  伺服器啟動      → 檢查 DB 是否為空，空則掃描熱門台股

設計：
- 使用 BackgroundScheduler，不阻斷主執行緒
- timezone 固定為 Asia/Taipei
- 所有 job 失敗時只 log，不讓 scheduler 崩潰
- start_heartbeat() 回傳 scheduler 實例，供 main.py lifespan 管理
"""
import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger

logger = logging.getLogger(__name__)

_TZ = "Asia/Taipei"

# 啟動掃描用的熱門股票（DB 為空時使用 + 每日定時擴大掃描）
_DEFAULT_STOCKS = [
    # 台股權值股 Top 20
    ("2330", "TW"),   # 台積電
    ("2317", "TW"),   # 鴻海
    ("2454", "TW"),   # 聯發科
    ("2308", "TW"),   # 台達電
    ("2881", "TW"),   # 富邦金
    ("2882", "TW"),   # 國泰金
    ("2891", "TW"),   # 中信金
    ("2303", "TW"),   # 聯電
    ("2412", "TW"),   # 中華電
    ("3711", "TW"),   # 日月光
    ("2886", "TW"),   # 兆豐金
    ("1301", "TW"),   # 台塑
    ("2002", "TW"),   # 中鋼
    ("1303", "TW"),   # 南亞
    ("2884", "TW"),   # 玉山金
    ("3008", "TW"),   # 大立光
    ("2892", "TW"),   # 第一金
    ("2382", "TW"),   # 廣達
    ("6505", "TW"),   # 台塑化
    ("2880", "TW"),   # 華南金
    # 台股人氣股
    ("2603", "TW"),   # 長榮
    ("3037", "TW"),   # 欣興
    ("2345", "TW"),   # 智邦
    ("2379", "TW"),   # 瑞昱
    ("3034", "TW"),   # 聯詠
    # 美股藍籌
    ("AAPL", "US"),   # Apple
    ("NVDA", "US"),   # NVIDIA
    ("MSFT", "US"),   # Microsoft
    ("TSLA", "US"),   # Tesla
    ("GOOG", "US"),   # Google
]


# ─── Job 包裝函式（捕捉例外，確保 scheduler 不崩潰）──────────────

def _job_market_scan() -> None:
    """交易日定時掃描：自選股 + 工作佇列處理。"""
    try:
        from backend.agents.ceo_agent import get_ceo_agent
        ceo = get_ceo_agent()
        ceo.hourly_watchlist_scan()
        ceo.run_pending_jobs(max_jobs=10)
    except Exception as e:
        logger.error(f"[Heartbeat] market_scan 失敗: {e}", exc_info=True)


def _job_postmarket() -> None:
    """台股收盤後：最後一次掃描 + 盤後總結。"""
    try:
        from backend.agents.ceo_agent import get_ceo_agent
        ceo = get_ceo_agent()
        ceo.hourly_watchlist_scan()
        ceo.run_pending_jobs(max_jobs=10)
        ceo.postmarket_summary()
    except Exception as e:
        logger.error(f"[Heartbeat] postmarket 失敗: {e}", exc_info=True)


def _job_weekly_backtest() -> None:
    try:
        from backend.agents.ceo_agent import get_ceo_agent
        ceo = get_ceo_agent()
        ceo.weekly_backtest()
    except Exception as e:
        logger.error(f"[Heartbeat] weekly_backtest 失敗: {e}", exc_info=True)


def _job_storage_check() -> None:
    try:
        from backend.agents.ceo_agent import get_ceo_agent
        ceo = get_ceo_agent()
        ceo.storage_check()
    except Exception as e:
        logger.error(f"[Heartbeat] storage_check 失敗: {e}", exc_info=True)


def _job_reset_budget() -> None:
    """每日凌晨重置 BudgetGuard（APScheduler 觸發的冗余保護）。"""
    try:
        from backend.core.budget_guard import get_budget_guard
        get_budget_guard().reset()
        logger.info("[Heartbeat] BudgetGuard 每日計數器已重置")
    except Exception as e:
        logger.error(f"[Heartbeat] budget_reset 失敗: {e}", exc_info=True)


def _job_startup_scan() -> None:
    """
    伺服器啟動時掃描熱門股票。
    - DB 為空：掃描全部 _DEFAULT_STOCKS（30 檔）
    - DB 已有資料：檢查哪些預設股票還沒有近期報告，補掃
    """
    try:
        from backend.data.storage.supabase_client import get_client
        client = get_client()
        if not client:
            logger.warning("[Heartbeat] 啟動掃描: DB 不可用，跳過")
            return

        from backend.agents.ceo_agent import get_ceo_agent
        ceo = get_ceo_agent()

        # 決定需要掃描的股票
        stocks_to_scan = []
        for symbol, market in _DEFAULT_STOCKS:
            if not ceo._has_recent_report(symbol, market, hours=8):
                stocks_to_scan.append((symbol, market))

        if not stocks_to_scan:
            logger.info("[Heartbeat] 所有預設股票都有近期報告，跳過啟動掃描")
            return

        logger.info(
            "[Heartbeat] 啟動掃描 %d 檔股票（共 %d 檔預設，%d 已有報告）",
            len(stocks_to_scan), len(_DEFAULT_STOCKS),
            len(_DEFAULT_STOCKS) - len(stocks_to_scan),
        )

        for symbol, market in stocks_to_scan:
            try:
                ceo._task_queue.enqueue(
                    job_type="analyze_stock",
                    payload={"symbol": symbol, "market": market},
                    priority=1,
                )
            except Exception as e:
                logger.warning(f"[Heartbeat] 入隊 {symbol} 失敗: {e}")

        # 每次最多處理 10 檔，避免一次把 API 配額用完
        ceo.run_pending_jobs(max_jobs=10)

    except Exception as e:
        logger.error(f"[Heartbeat] 啟動掃描失敗: {e}", exc_info=True)


def _job_broad_market_scan() -> None:
    """
    每日全市場掃描：掃描所有預設股票 + 所有使用者自選股。
    在非繁忙時段執行，確保涵蓋面更廣。
    """
    try:
        from backend.agents.ceo_agent import get_ceo_agent
        ceo = get_ceo_agent()

        # 先掃預設股票（全市場熱門股）
        enqueued = 0
        for symbol, market in _DEFAULT_STOCKS:
            if not ceo._has_recent_report(symbol, market, hours=8):
                job_id = ceo._task_queue.enqueue(
                    job_type="analyze_stock",
                    payload={"symbol": symbol, "market": market, "triggered_by": "每日全市場掃描"},
                    priority=3,
                )
                if job_id:
                    enqueued += 1

        logger.info("[Heartbeat] 每日全市場掃描: 預設股票入隊 %d 檔", enqueued)

        # 再掃自選股（CEO agent 自己會處理）
        ceo.hourly_watchlist_scan()

        # 處理排隊工作
        ceo.run_pending_jobs(max_jobs=15)

    except Exception as e:
        logger.error(f"[Heartbeat] 每日全市場掃描失敗: {e}", exc_info=True)


# ─── 啟動函式 ─────────────────────────────────────────────────────

def start_heartbeat() -> BackgroundScheduler:
    """
    建立並啟動 APScheduler 排程器。

    Returns:
        BackgroundScheduler 實例（供 lifespan 在關機時呼叫 shutdown()）
    """
    scheduler = BackgroundScheduler(timezone=_TZ)

    # ── 交易日三段掃描（週一至週五）─────────────────────

    # 09:10 — 台股開盤後首次掃描
    scheduler.add_job(
        _job_market_scan,
        CronTrigger(day_of_week="mon-fri", hour=9, minute=10, timezone=_TZ),
        id="morning_scan",
        replace_existing=True,
        misfire_grace_time=600,
    )

    # 12:00 — 午盤掃描
    scheduler.add_job(
        _job_market_scan,
        CronTrigger(day_of_week="mon-fri", hour=12, minute=0, timezone=_TZ),
        id="midday_scan",
        replace_existing=True,
        misfire_grace_time=600,
    )

    # 13:35 — 台股收盤後掃描 + 盤後總結
    scheduler.add_job(
        _job_postmarket,
        CronTrigger(day_of_week="mon-fri", hour=13, minute=35, timezone=_TZ),
        id="postmarket",
        replace_existing=True,
        misfire_grace_time=600,
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

    # 每 6 小時：儲存管理檢查（00:00 / 06:00 / 12:00 / 18:00）
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

    # 每日 08:00 + 21:00：全市場掃描（台股盤前 + 美股盤前）
    scheduler.add_job(
        _job_broad_market_scan,
        CronTrigger(day_of_week="mon-fri", hour=8, minute=0, timezone=_TZ),
        id="broad_scan_morning",
        replace_existing=True,
        misfire_grace_time=1800,
    )
    scheduler.add_job(
        _job_broad_market_scan,
        CronTrigger(day_of_week="mon-fri", hour=21, minute=0, timezone=_TZ),
        id="broad_scan_evening",
        replace_existing=True,
        misfire_grace_time=1800,
    )

    # ── 伺服器啟動掃描（延遲 10 秒，等待應用完全就緒）────
    from datetime import datetime, timedelta
    import pytz
    tz = pytz.timezone(_TZ)
    run_at = datetime.now(tz) + timedelta(seconds=10)
    scheduler.add_job(
        _job_startup_scan,
        DateTrigger(run_date=run_at, timezone=_TZ),
        id="startup_scan",
        replace_existing=True,
        misfire_grace_time=120,
    )

    scheduler.start()
    logger.info(
        "[Heartbeat] 排程器啟動完成，共 %d 個 job（含啟動掃描）",
        len(scheduler.get_jobs()),
    )

    return scheduler
