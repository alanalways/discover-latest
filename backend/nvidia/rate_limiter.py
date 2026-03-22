"""
backend/nvidia/rate_limiter.py
NVIDIA NIM Rate Limit 管理器

限制：40 RPM，無 RPD / TPD 限制
策略：超過 40 RPM 時 blocking wait，不降級（無其他模型可降）

實作：Thread-safe sliding window（60 秒），超限時計算需等待時間後 sleep。
"""
import threading
import time
import logging
from collections import deque

from backend.config import NVIDIA_RATE_LIMITS, NVIDIA_MODEL

logger = logging.getLogger(__name__)

_RPM_LIMIT: int = NVIDIA_RATE_LIMITS.get(NVIDIA_MODEL, {}).get("rpm", 40)


class NvidiaRateLimiter:
    """
    Thread-safe NVIDIA NIM rate limiter。
    只追蹤 RPM（每分鐘請求數），無 RPD 限制。
    超過 40 RPM 時 blocking wait，直到視窗滑動後有空位。
    """

    def __init__(self, rpm_limit: int = _RPM_LIMIT):
        self._rpm_limit = rpm_limit
        self._lock = threading.Lock()
        # 記錄最近 60 秒內的呼叫時間戳
        self._window: deque[float] = deque()

    def _clean_window(self, now: float) -> None:
        """移除 60 秒前的舊時間戳（必須在 lock 內呼叫）。"""
        while self._window and now - self._window[0] > 60:
            self._window.popleft()

    def can_call(self) -> bool:
        """
        檢查目前是否可以發出新請求（不 blocking）。
        """
        with self._lock:
            now = time.time()
            self._clean_window(now)
            return len(self._window) < self._rpm_limit

    def wait_if_needed(self) -> None:
        """
        若目前 RPM 已達上限，blocking wait 直到視窗滑動出空位。
        確保呼叫後一定可以立即發出請求。
        """
        while True:
            with self._lock:
                now = time.time()
                self._clean_window(now)
                if len(self._window) < self._rpm_limit:
                    return  # 有空位，可以發請求

                # 計算需等待的秒數：等到最舊的時間戳超過 60 秒
                oldest = self._window[0]
                wait_sec = (oldest + 60) - now + 0.1  # +0.1s buffer

            if wait_sec > 0:
                logger.warning(
                    f"[NvidiaRateLimiter] RPM 達上限 ({self._rpm_limit})，"
                    f"等待 {wait_sec:.1f}s..."
                )
                time.sleep(wait_sec)

    def record_call(self) -> None:
        """
        記錄一次成功的 API 呼叫（在呼叫成功後調用）。
        """
        with self._lock:
            self._window.append(time.time())

    def get_status(self) -> dict:
        """回傳目前使用狀況（供 cost_monitor 使用）。"""
        with self._lock:
            now = time.time()
            self._clean_window(now)
            return {
                "rpm_used": len(self._window),
                "rpm_limit": self._rpm_limit,
                "model": NVIDIA_MODEL,
            }


# ── 單例 ────────────────────────────────────────────────
_limiter: NvidiaRateLimiter | None = None
_limiter_lock = threading.Lock()


def get_nvidia_rate_limiter() -> NvidiaRateLimiter:
    """取得全局 NvidiaRateLimiter 單例。"""
    global _limiter
    if _limiter is None:
        with _limiter_lock:
            if _limiter is None:
                _limiter = NvidiaRateLimiter()
    return _limiter
