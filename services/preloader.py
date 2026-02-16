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
    try:
        from pages.market_overview import _refresh_top20_background

        _refresh_top20_background()
        logger.info("Top20 background preload triggered")
    except Exception as e:
        logger.debug("Top20 preload skipped: %s", e)

    try:
        from services.market_scanner import scan_market

        scan_market(limit=20)
        logger.info("Scanner cache preload completed")
    except Exception as e:
        logger.debug("Scanner preload skipped: %s", e)
