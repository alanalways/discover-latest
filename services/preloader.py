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
    # ── 1. Top20 排行榜 ──
    try:
        from pages.market_overview import _refresh_top20_background

        _refresh_top20_background()
        logger.info("Top20 background preload triggered")
    except Exception as e:
        logger.debug("Top20 preload skipped: %s", e)

    # ── 2. 市場掃描器 ──
    try:
        from services.market_scanner import scan_market

        scan_market(limit=20)
        logger.info("Scanner cache preload completed")
    except Exception as e:
        logger.debug("Scanner preload skipped: %s", e)

    # ── 3. 指數行情（market overview）──
    try:
        from routes.market import market_overview

        import asyncio
        loop = asyncio.new_event_loop()
        loop.run_until_complete(market_overview())
        loop.close()
        logger.info("Market indices preload completed")
    except Exception as e:
        logger.debug("Market indices preload skipped: %s", e)

    # ── 4. 新聞摘要 ──
    try:
        from routes.news import get_news_brief

        import asyncio
        loop = asyncio.new_event_loop()
        loop.run_until_complete(get_news_brief())
        loop.close()
        logger.info("News brief preload completed")
    except Exception as e:
        logger.debug("News preload skipped: %s", e)

