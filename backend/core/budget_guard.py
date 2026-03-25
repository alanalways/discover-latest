"""
backend/core/budget_guard.py

Gemini 每日預算守門。

這裡的 budget 單位是「Gemini 呼叫次數」，不是單指 grounding。
目前主要用來保護：
- batch grounding
- arbitrator
- chief analyst
"""

from __future__ import annotations

import logging
import threading
from datetime import date

from backend.config import DAILY_GROUNDING_RPD_BUDGET, GEMINI_RATE_LIMITS

logger = logging.getLogger(__name__)

_WARN_THRESHOLD = 0.80
_BLOCK_THRESHOLD = 0.95


class BudgetGuard:
    """Thread-safe Gemini daily budget guard。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._today = date.today()
        self._used: dict[str, int] = {model: 0 for model in GEMINI_RATE_LIMITS}
        self._total_used = 0

    def can_proceed(self, estimated_calls: int = 1) -> tuple[bool, str]:
        self._maybe_reset()

        with self._lock:
            projected = self._total_used + max(0, estimated_calls)
            usage_pct = projected / DAILY_GROUNDING_RPD_BUDGET

            if usage_pct >= _BLOCK_THRESHOLD:
                msg = (
                    f"Gemini 日預算已達 {self._total_used}/{DAILY_GROUNDING_RPD_BUDGET}，"
                    f"拒絕新工作（{usage_pct:.0%}）"
                )
                logger.error("[BudgetGuard] %s", msg)
                return False, msg

            if usage_pct >= _WARN_THRESHOLD:
                logger.warning(
                    "[BudgetGuard] Gemini 日預算使用 %s/%s（%.0f%%），接近上限",
                    self._total_used,
                    DAILY_GROUNDING_RPD_BUDGET,
                    usage_pct * 100,
                )

            return True, "OK"

    def record_usage(self, model_name: str = "gemini-2.5-flash", calls: int = 1) -> None:
        self._maybe_reset()
        calls = max(0, int(calls))
        if calls == 0:
            return

        with self._lock:
            if model_name in self._used:
                self._used[model_name] += calls
            self._total_used += calls

    def get_status(self) -> dict:
        self._maybe_reset()
        with self._lock:
            pct = self._total_used / DAILY_GROUNDING_RPD_BUDGET
            return {
                "date": self._today.isoformat(),
                "total_used": self._total_used,
                "total_budget": DAILY_GROUNDING_RPD_BUDGET,
                "usage_pct": round(pct * 100, 1),
                "remaining": DAILY_GROUNDING_RPD_BUDGET - self._total_used,
                "status": (
                    "critical"
                    if pct >= _BLOCK_THRESHOLD
                    else "warning"
                    if pct >= _WARN_THRESHOLD
                    else "healthy"
                ),
                "by_model": dict(self._used),
            }

    def reset(self) -> None:
        with self._lock:
            self._today = date.today()
            self._used = {model: 0 for model in GEMINI_RATE_LIMITS}
            self._total_used = 0
        logger.info("[BudgetGuard] Gemini 每日預算已重置")

    def _maybe_reset(self) -> None:
        if date.today() != self._today:
            self.reset()


_guard_instance: BudgetGuard | None = None
_guard_lock = threading.Lock()


def get_budget_guard() -> BudgetGuard:
    global _guard_instance
    if _guard_instance is None:
        with _guard_lock:
            if _guard_instance is None:
                _guard_instance = BudgetGuard()
    return _guard_instance
