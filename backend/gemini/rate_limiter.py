"""
backend/gemini/rate_limiter.py

Gemini rate limiter。

- RPM 與 RPD 都會依照實際 key / project 數量放大
- 目前每把 key 都對應獨立 project，所以 pool 額度應乘上 key 數
- 真正的 key 輪替仍由 backend.gemini.client 負責
"""

from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict, deque
from datetime import date

from backend.config import GEMINI_API_KEYS_LIST, GEMINI_RATE_LIMITS

logger = logging.getLogger(__name__)


class RateLimiter:
    """Thread-safe Gemini RPM / RPD limiter。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._rpm_window: dict[str, deque[float]] = defaultdict(deque)
        self._rpd_count: dict[tuple[str, date], int] = defaultdict(int)

    def can_call(self, model_name: str) -> bool:
        limits = GEMINI_RATE_LIMITS.get(model_name)
        if not limits:
            logger.warning("[RateLimiter] 未知模型 %s，略過限制檢查", model_name)
            return True

        with self._lock:
            now = time.time()
            today = date.today()
            pool_size = max(1, len(GEMINI_API_KEYS_LIST))

            window = self._rpm_window[model_name]
            while window and now - window[0] > 60:
                window.popleft()

            current_rpm = len(window)
            max_rpm = int(limits["rpm"]) * pool_size
            if current_rpm >= max_rpm:
                logger.warning(
                    "[RateLimiter] %s RPM 達上限 (%s/%s, %s projects)",
                    model_name,
                    current_rpm,
                    max_rpm,
                    pool_size,
                )
                return False

            current_rpd = self._rpd_count[(model_name, today)]
            max_rpd = int(limits["rpd"]) * pool_size
            if current_rpd >= max_rpd:
                logger.warning(
                    "[RateLimiter] %s RPD 達上限 (%s/%s, %s projects)",
                    model_name,
                    current_rpd,
                    max_rpd,
                    pool_size,
                )
                return False

            return True

    def record_call(self, model_name: str) -> None:
        with self._lock:
            self._rpm_window[model_name].append(time.time())
            self._rpd_count[(model_name, date.today())] += 1

    def get_status(self) -> dict:
        with self._lock:
            now = time.time()
            today = date.today()
            pool_size = max(1, len(GEMINI_API_KEYS_LIST))
            status: dict[str, dict[str, int]] = {}

            for model_name, limits in GEMINI_RATE_LIMITS.items():
                window = self._rpm_window[model_name]
                while window and now - window[0] > 60:
                    window.popleft()

                status[model_name] = {
                    "rpm_used": len(window),
                    "rpm_limit": int(limits["rpm"]) * pool_size,
                    "rpd_used": self._rpd_count[(model_name, today)],
                    "rpd_limit": int(limits["rpd"]) * pool_size,
                }

            return status
