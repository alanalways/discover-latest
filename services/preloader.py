"""Background preloader for frequently requested data."""

from __future__ import annotations

import logging
import threading

logger = logging.getLogger(__name__)

_started = False
_lock = threading.Lock()


def start_preload() -> None:
    global _started
    with _lock:
        if _started:
            return
        _started = True
    threading.Thread(target=_preload_task, daemon=True).start()


def _preload_task() -> None:
    """並行暖快取 — 所有資料源同時開始載入。"""
    import asyncio
    from concurrent.futures import ThreadPoolExecutor

    def _preload_top20():
        try:
            from services.market_service import refresh_top20_background as _refresh_top20_background
            _refresh_top20_background()
            logger.info("Top20 background preload completed")
        except Exception as e:
            logger.debug("Top20 preload skipped: %s", e)

    def _preload_scanner():
        try:
            from services.market_scanner import scan_market
            scan_market(limit=20)
            logger.info("Scanner cache preload completed")
        except Exception as e:
            logger.debug("Scanner preload skipped: %s", e)

    def _preload_indices():
        try:
            from routes.market import market_overview
            loop = asyncio.new_event_loop()
            loop.run_until_complete(market_overview())
            loop.close()
            logger.info("Market indices preload completed")
        except Exception as e:
            logger.debug("Market indices preload skipped: %s", e)

    def _preload_news():
        try:
            from routes.news import get_news_brief
            loop = asyncio.new_event_loop()
            loop.run_until_complete(get_news_brief())
            loop.close()
            logger.info("News brief preload completed")
        except Exception as e:
            logger.debug("News preload skipped: %s", e)

    # 全部並行執行
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [
            pool.submit(_preload_top20),
            pool.submit(_preload_scanner),
            pool.submit(_preload_indices),
            pool.submit(_preload_news),
        ]
        for f in futures:
            try:
                f.result(timeout=30)
            except Exception:
                pass
    logger.info("All preload tasks completed")

