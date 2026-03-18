"""
backend/core/budget_guard.py
API 預算守門員（Sonnet 撰寫）

職責：
1. 追蹤每日 Gemini RPD 總用量
2. 超出預算時拒絕新工作入隊
3. 提供預算使用狀況查詢
4. 每日零時自動重置計數器
"""
import logging
import threading
from datetime import date, datetime, timezone

from backend.config import DAILY_GEMINI_RPD_BUDGET, RATE_LIMITS

logger = logging.getLogger(__name__)

# 預算警戒門檻
_WARN_THRESHOLD  = 0.80   # 80% 時發出 WARNING
_BLOCK_THRESHOLD = 0.95   # 95% 時拒絕新工作


class BudgetGuard:
    """
    Gemini API 每日預算守門員。
    Thread-safe，支援多 agent 並發更新。
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._today = date.today()
        # 每個模型的已用 RPD
        self._used: dict[str, int] = {m: 0 for m in RATE_LIMITS}
        self._total_used: int = 0

    # ─── 公開介面 ────────────────────────────────────────────

    def can_proceed(self, estimated_calls: int = 1) -> tuple[bool, str]:
        """
        判斷是否可以繼續使用 Gemini（不超出日預算）。

        Args:
            estimated_calls: 預計呼叫次數

        Returns:
            (allowed: bool, reason: str)
        """
        self._maybe_reset()

        with self._lock:
            projected = self._total_used + estimated_calls
            usage_pct = projected / DAILY_GEMINI_RPD_BUDGET

            if usage_pct >= _BLOCK_THRESHOLD:
                msg = (
                    f"Gemini 日預算已達 {self._total_used}/{DAILY_GEMINI_RPD_BUDGET}，"
                    f"拒絕新工作（{usage_pct:.0%}）"
                )
                logger.error(f"[BudgetGuard] {msg}")
                return False, msg

            if usage_pct >= _WARN_THRESHOLD:
                logger.warning(
                    f"[BudgetGuard] Gemini 日預算使用 {self._total_used}/"
                    f"{DAILY_GEMINI_RPD_BUDGET}（{usage_pct:.0%}），接近上限"
                )

            return True, "OK"

    def record_usage(self, model_name: str, calls: int = 1) -> None:
        """記錄一次 Gemini 呼叫消耗。"""
        self._maybe_reset()
        with self._lock:
            if model_name in self._used:
                self._used[model_name] += calls
            self._total_used += calls

    def get_status(self) -> dict:
        """回傳目前預算使用狀況。"""
        self._maybe_reset()
        with self._lock:
            pct = self._total_used / DAILY_GEMINI_RPD_BUDGET
            return {
                "date": self._today.isoformat(),
                "total_used": self._total_used,
                "total_budget": DAILY_GEMINI_RPD_BUDGET,
                "usage_pct": round(pct * 100, 1),
                "remaining": DAILY_GEMINI_RPD_BUDGET - self._total_used,
                "status": (
                    "critical" if pct >= _BLOCK_THRESHOLD
                    else "warning" if pct >= _WARN_THRESHOLD
                    else "healthy"
                ),
                "by_model": dict(self._used),
            }

    def reset(self) -> None:
        """手動重置計數器（每日凌晨由 heartbeat 呼叫）。"""
        with self._lock:
            self._today = date.today()
            self._used = {m: 0 for m in RATE_LIMITS}
            self._total_used = 0
        logger.info("[BudgetGuard] 每日預算計數器已重置")

    # ─── 內部方法 ────────────────────────────────────────────

    def _maybe_reset(self) -> None:
        """若已跨日，自動重置計數器。"""
        if date.today() != self._today:
            self.reset()


# ─── 模組級單例 ──────────────────────────────────────────────────
_guard_instance = None
_guard_lock = threading.Lock()


def get_budget_guard() -> BudgetGuard:
    """取得 BudgetGuard 單例。"""
    global _guard_instance
    if _guard_instance is None:
        with _guard_lock:
            if _guard_instance is None:
                _guard_instance = BudgetGuard()
    return _guard_instance
