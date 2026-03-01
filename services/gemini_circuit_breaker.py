"""
Gemini API Circuit Breaker — 斷路器模式

當 Gemini API 連續失敗時自動切換至降級模式，避免每次請求都等待 timeout。

狀態機：
  CLOSED  → 正常模式，API 請求正常發出
  OPEN    → 斷路模式，直接走降級路徑（不呼叫 API）
  HALF_OPEN → 試探模式，允許 1 個請求測試 API 是否恢復

觸發條件：
  - 連續 N 次失敗（timeout / error）→ CLOSED → OPEN
  - OPEN 持續 cooldown 秒後 → OPEN → HALF_OPEN
  - HALF_OPEN 成功 → HALF_OPEN → CLOSED
  - HALF_OPEN 失敗 → HALF_OPEN → OPEN
"""

from __future__ import annotations

import logging
import threading
import time
from enum import Enum
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    CLOSED = "closed"          # 正常
    OPEN = "open"              # 斷路（跳過 API）
    HALF_OPEN = "half_open"    # 試探


class GeminiCircuitBreaker:
    """Thread-safe circuit breaker for Gemini API calls."""

    def __init__(
        self,
        failure_threshold: int = 3,
        cooldown_sec: float = 120.0,
        success_threshold: int = 1,
    ):
        self._lock = threading.Lock()
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time = 0.0
        self._last_state_change = time.time()

        # 配置
        self.failure_threshold = failure_threshold   # 連續 N 次失敗 → OPEN
        self.cooldown_sec = cooldown_sec             # OPEN 後等 N 秒才試探
        self.success_threshold = success_threshold   # HALF_OPEN 需連續成功 N 次才 CLOSE

        # 統計
        self._total_failures = 0
        self._total_successes = 0
        self._total_short_circuits = 0
        self._open_since: Optional[float] = None

    @property
    def state(self) -> CircuitState:
        with self._lock:
            self._maybe_transition_to_half_open()
            return self._state

    @property
    def is_available(self) -> bool:
        """API 是否可用（CLOSED 或 HALF_OPEN 允許嘗試）"""
        s = self.state
        return s in (CircuitState.CLOSED, CircuitState.HALF_OPEN)

    def record_success(self) -> None:
        """記錄一次 API 成功"""
        with self._lock:
            self._total_successes += 1
            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.success_threshold:
                    self._transition_to(CircuitState.CLOSED)
                    logger.info("Circuit breaker CLOSED — Gemini API 已恢復")
            elif self._state == CircuitState.CLOSED:
                self._failure_count = 0  # 重置連續失敗計數

    def record_failure(self, error_type: str = "unknown") -> None:
        """記錄一次 API 失敗"""
        with self._lock:
            self._total_failures += 1
            self._last_failure_time = time.time()

            if self._state == CircuitState.HALF_OPEN:
                self._transition_to(CircuitState.OPEN)
                logger.warning("Circuit breaker OPEN — HALF_OPEN 試探失敗 (%s)", error_type)
            elif self._state == CircuitState.CLOSED:
                self._failure_count += 1
                if self._failure_count >= self.failure_threshold:
                    self._transition_to(CircuitState.OPEN)
                    logger.warning(
                        "Circuit breaker OPEN — 連續 %d 次失敗 (%s)",
                        self._failure_count, error_type,
                    )

    def record_short_circuit(self) -> None:
        """記錄一次被斷路器跳過的請求"""
        with self._lock:
            self._total_short_circuits += 1

    def get_status(self) -> Dict[str, Any]:
        """取得當前狀態（供 admin dashboard 使用）"""
        with self._lock:
            self._maybe_transition_to_half_open()
            now = time.time()
            result = {
                "state": self._state.value,
                "failure_count": self._failure_count,
                "total_failures": self._total_failures,
                "total_successes": self._total_successes,
                "total_short_circuits": self._total_short_circuits,
                "failure_threshold": self.failure_threshold,
                "cooldown_sec": self.cooldown_sec,
                "state_duration_sec": round(now - self._last_state_change, 1),
            }
            if self._open_since is not None:
                remaining = max(0, self.cooldown_sec - (now - self._open_since))
                result["cooldown_remaining_sec"] = round(remaining, 1)
            if self._last_failure_time > 0:
                result["last_failure_ago_sec"] = round(now - self._last_failure_time, 1)
            return result

    def force_close(self) -> None:
        """手動強制關閉斷路器（恢復正常）"""
        with self._lock:
            self._transition_to(CircuitState.CLOSED)
            logger.info("Circuit breaker force CLOSED by admin")

    def force_open(self) -> None:
        """手動強制開啟斷路器（進入降級）"""
        with self._lock:
            self._transition_to(CircuitState.OPEN)
            logger.info("Circuit breaker force OPEN by admin")

    # ── 內部方法 ──

    def _maybe_transition_to_half_open(self) -> None:
        """檢查 OPEN 狀態是否已過 cooldown，自動切換到 HALF_OPEN"""
        if self._state == CircuitState.OPEN and self._open_since is not None:
            elapsed = time.time() - self._open_since
            if elapsed >= self.cooldown_sec:
                self._transition_to(CircuitState.HALF_OPEN)
                logger.info(
                    "Circuit breaker HALF_OPEN — 開始試探 Gemini API (%.0f 秒後)",
                    elapsed,
                )

    def _transition_to(self, new_state: CircuitState) -> None:
        """狀態轉換（必須在 lock 內呼叫）"""
        old = self._state
        self._state = new_state
        self._last_state_change = time.time()

        if new_state == CircuitState.CLOSED:
            self._failure_count = 0
            self._success_count = 0
            self._open_since = None
        elif new_state == CircuitState.OPEN:
            self._success_count = 0
            self._open_since = time.time()
        elif new_state == CircuitState.HALF_OPEN:
            self._success_count = 0

        if old != new_state:
            logger.info("Circuit breaker: %s → %s", old.value, new_state.value)


# ── 全域單例 ──
gemini_breaker = GeminiCircuitBreaker(
    failure_threshold=3,   # 連續 3 次失敗觸發
    cooldown_sec=120.0,    # 2 分鐘後試探
    success_threshold=1,   # 1 次成功即恢復
)
