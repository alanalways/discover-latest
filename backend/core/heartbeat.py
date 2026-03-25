"""
backend/core/heartbeat.py

以免費額度友善為前提的排程器：
- 每小時整點掃描自選股
- 08:25 台股盤前掃描
- 15:05 收盤後總結
- 週一 07:00 回測
- 每 6 小時 storage check
- 每 5 分鐘處理佇列
"""

import logging
import threading
from datetime import datetime, timedelta

import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger

from backend.config import HEARTBEAT_QUEUE_MAX_JOBS

logger = logging.getLogger(__name__)

_TZ = "Asia/Taipei"
_queue_processor_lock = threading.Lock()


def _job_hourly_watchlist() -> None:
    from backend.agents.ceo_agent import get_ceo_agent

    get_ceo_agent().hourly_watchlist_scan()


def _job_premarket() -> None:
    from backend.agents.ceo_agent import get_ceo_agent

    get_ceo_agent().premarket_scan(market_filter="TW")


def _job_postmarket_summary() -> None:
    from backend.agents.ceo_agent import get_ceo_agent

    get_ceo_agent().postmarket_summary()


def _job_weekly_backtest() -> None:
    from backend.agents.ceo_agent import get_ceo_agent

    get_ceo_agent().weekly_backtest()


def _job_storage_check() -> None:
    from backend.agents.ceo_agent import get_ceo_agent

    get_ceo_agent().storage_check()


def _job_reset_budget() -> None:
    from backend.core.budget_guard import get_budget_guard

    get_budget_guard().reset()
    logger.info("[Heartbeat] budget guard reset")


def _job_process_queue() -> None:
    if not _queue_processor_lock.acquire(blocking=False):
        return

    def _process() -> None:
        try:
            from backend.agents.ceo_agent import get_ceo_agent

            result = get_ceo_agent().run_pending_jobs(max_jobs=HEARTBEAT_QUEUE_MAX_JOBS)
            if result.get("processed", 0) > 0:
                logger.info("[Heartbeat] queue processed: %s", result)
        except Exception as exc:
            logger.error("[Heartbeat] queue processing failed: %s", exc, exc_info=True)
        finally:
            _queue_processor_lock.release()

    thread = threading.Thread(target=_process, daemon=True, name="queue-processor")
    thread.start()


def _job_startup_warmup() -> None:
    """
    啟動後先跑一次 queue processor。

    不直接大規模掃描，避免剛開機就額外燒掉免費額度。
    """
    _job_process_queue()


def start_heartbeat() -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone=_TZ)

    scheduler.add_job(
        _job_hourly_watchlist,
        CronTrigger(minute=0, timezone=_TZ),
        id="hourly_watchlist",
        replace_existing=True,
        misfire_grace_time=1800,
    )

    scheduler.add_job(
        _job_premarket,
        CronTrigger(day_of_week="mon-fri", hour=8, minute=25, timezone=_TZ),
        id="premarket_scan",
        replace_existing=True,
        misfire_grace_time=1800,
    )

    scheduler.add_job(
        _job_postmarket_summary,
        CronTrigger(day_of_week="mon-fri", hour=15, minute=5, timezone=_TZ),
        id="postmarket_summary",
        replace_existing=True,
        misfire_grace_time=1800,
    )

    scheduler.add_job(
        _job_weekly_backtest,
        CronTrigger(day_of_week="mon", hour=7, minute=0, timezone=_TZ),
        id="weekly_backtest",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    scheduler.add_job(
        _job_storage_check,
        CronTrigger(hour="0,6,12,18", minute=0, timezone=_TZ),
        id="storage_check",
        replace_existing=True,
        misfire_grace_time=1800,
    )

    scheduler.add_job(
        _job_process_queue,
        CronTrigger(minute="*/5", timezone=_TZ),
        id="process_queue",
        replace_existing=True,
        misfire_grace_time=300,
    )

    scheduler.add_job(
        _job_reset_budget,
        CronTrigger(hour=0, minute=1, timezone=_TZ),
        id="budget_reset",
        replace_existing=True,
        misfire_grace_time=600,
    )

    tz = pytz.timezone(_TZ)
    scheduler.add_job(
        _job_startup_warmup,
        DateTrigger(run_date=datetime.now(tz) + timedelta(seconds=15), timezone=_TZ),
        id="startup_warmup",
        replace_existing=True,
        misfire_grace_time=120,
    )

    scheduler.start()
    logger.info(
        "[Heartbeat] scheduler started with %s jobs",
        len(scheduler.get_jobs()),
    )
    return scheduler
