"""
backend/core/heartbeat.py
APScheduler 排程心跳（Sonnet 撰寫）

排程表：
  每小時整點      → ceo.hourly_watchlist_scan + ceo.run_pending_jobs
  08:25（台北）   → ceo.premarket_scan
  15:05（台北）   → ceo.postmarket_summary
  週一 07:00      → ceo.weekly_backtest
  每6小時         → ceo.storage_check
  每日 00:01      → 重置 BudgetGuard 計數器（冗余保護）

設計：
- 使用 BackgroundScheduler，不阻斷主執行緒
- timezone 固定為 Asia/Taipei
- 所有 job 失敗時只 log，不讓 scheduler 崩潰
- start_heartbeat() 回傳 scheduler 實例，供 main.py lifespan 管理
"""
import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)

_TZ = "Asia/Taipei"


# ─── Job 包裝函式（捕捉例外，確保 scheduler 不崩潰）──────────────

def _job_hourly_scan() -> None:
    try:
        from backend.agents.ceo_agent import get_ceo_agent
        ceo = get_ceo_agent()
        ceo.hourly_watchlist_scan()
        ceo.run_pending_jobs(max_jobs=5)
    except Exception as e:
        logger.error(f"[Heartbeat] hourly_scan 失敗: {e}", exc_info=True)


def _job_premarket() -> None:
    try:
        from backend.agents.ceo_agent import get_ceo_agent
        ceo = get_ceo_agent()
        ceo.premarket_scan()
        ceo.run_pending_jobs(max_jobs=10)
    except Exception as e:
        logger.error(f"[Heartbeat] premarket_scan 失敗: {e}", exc_info=True)


def _job_postmarket() -> None:
    try:
        from backend.agents.ceo_agent import get_ceo_agent
        ceo = get_ceo_agent()
        ceo.postmarket_summary()
    except Exception as e:
        logger.error(f"[Heartbeat] postmarket_summary 失敗: {e}", exc_info=True)


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


# ─── 啟動函式 ─────────────────────────────────────────────────────

def start_heartbeat() -> BackgroundScheduler:
    """
    建立並啟動 APScheduler 排程器。

    Returns:
        BackgroundScheduler 實例（供 lifespan 在關機時呼叫 shutdown()）
    """
    scheduler = BackgroundScheduler(timezone=_TZ)

    # 每小時整點：自選股掃描 + 工作佇列處理
    scheduler.add_job(
        _job_hourly_scan,
        CronTrigger(minute=0, timezone=_TZ),
        id="hourly_scan",
        replace_existing=True,
        misfire_grace_time=300,   # 最多延誤 5 分鐘仍執行
    )

    # 台股盤前 08:25
    scheduler.add_job(
        _job_premarket,
        CronTrigger(hour=8, minute=25, timezone=_TZ),
        id="premarket",
        replace_existing=True,
        misfire_grace_time=600,
    )

    # 台股收盤後 15:05
    scheduler.add_job(
        _job_postmarket,
        CronTrigger(hour=15, minute=5, timezone=_TZ),
        id="postmarket",
        replace_existing=True,
        misfire_grace_time=600,
    )

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

    # 每日 00:01：預算計數器重置（冗余保護，BudgetGuard 本身也會自動重置）
    scheduler.add_job(
        _job_reset_budget,
        CronTrigger(hour=0, minute=1, timezone=_TZ),
        id="budget_reset",
        replace_existing=True,
        misfire_grace_time=600,
    )

    scheduler.start()
    logger.info(
        "[Heartbeat] 排程器啟動完成，共 %d 個 job",
        len(scheduler.get_jobs()),
    )

    return scheduler
