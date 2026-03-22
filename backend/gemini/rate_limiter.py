"""
backend/gemini/rate_limiter.py
Gemini API Rate Limit 管理器
- 追蹤每分鐘(RPM)和每日(RPD)使用量
- 超出限制時回傳 False，由 client.py 觸發自動降級
"""
import threading
import time
import logging
from collections import defaultdict, deque
from datetime import date

from backend.config import GEMINI_RATE_LIMITS

logger = logging.getLogger(__name__)


class RateLimiter:
    """
    Thread-safe Gemini API rate limiter。
    追蹤 RPM（每分鐘請求數）和 RPD（每日請求數）。
    """

    def __init__(self):
        self._lock = threading.Lock()
        # RPM 追蹤：model_name -> deque of timestamps（最近 60 秒）
        self._rpm_window: dict[str, deque] = defaultdict(deque)
        # RPD 追蹤：(model_name, date) -> count
        self._rpd_count: dict[tuple, int] = defaultdict(int)

    def can_call(self, model_name: str) -> bool:
        """
        檢查指定模型是否可以發出新請求。
        同時檢查 RPM 和 RPD 限制。
        """
        limits = GEMINI_RATE_LIMITS.get(model_name)
        if not limits:
            # 未知模型，允許通過（保守策略）
            logger.warning(f"[RateLimiter] 未知模型 {model_name}，允許通過")
            return True

        with self._lock:
            now = time.time()
            today = date.today()

            # ── 清理 RPM 視窗（超過 60 秒的紀錄）──────────────
            window = self._rpm_window[model_name]
            while window and now - window[0] > 60:
                window.popleft()

            # ── 檢查 RPM ────────────────────────────────────────
            current_rpm = len(window)
            max_rpm = limits["rpm"]
            if current_rpm >= max_rpm:
                logger.warning(
                    f"[RateLimiter] {model_name} RPM 已達上限 "
                    f"({current_rpm}/{max_rpm})"
                )
                return False

            # ── 檢查 RPD ────────────────────────────────────────
            rpd_key = (model_name, today)
            current_rpd = self._rpd_count[rpd_key]
            max_rpd = limits["rpd"]
            if current_rpd >= max_rpd:
                logger.warning(
                    f"[RateLimiter] {model_name} RPD 已達上限 "
                    f"({current_rpd}/{max_rpd})"
                )
                return False

            return True

    def record_call(self, model_name: str) -> None:
        """
        記錄一次成功的 API 呼叫（在呼叫成功後調用）。
        """
        with self._lock:
            now = time.time()
            today = date.today()

            self._rpm_window[model_name].append(now)
            self._rpd_count[(model_name, today)] += 1

    def get_status(self) -> dict:
        """
        回傳所有模型的目前使用狀況（供 cost_monitor 使用）。
        """
        with self._lock:
            now = time.time()
            today = date.today()
            status = {}

            for model_name, limits in GEMINI_RATE_LIMITS.items():
                # 清理 RPM 視窗
                window = self._rpm_window[model_name]
                while window and now - window[0] > 60:
                    window.popleft()

                rpd_key = (model_name, today)
                status[model_name] = {
                    "rpm_used": len(window),
                    "rpm_limit": limits["rpm"],
                    "rpd_used": self._rpd_count[rpd_key],
                    "rpd_limit": limits["rpd"],
                }

            return status
