"""
backend/nvidia/rate_limiter.py
NVIDIA NIM Rate Limit 管理器

限制：40 RPM，無 RPD / TPD 限制
策略：超過 40 RPM 時 blocking wait，不降級（無其他模型可降）

實作：Thread-safe sliding window（60 秒）+ 預佔位（pre-allocation）

⚠️ TOCTOU 修正說明：
  舊版：wait_if_needed() 只檢查，不預佔位
  → 6 個 thread 同時 check → 全通過 → 同時發送 → API 429

  新版：wait_if_needed() 在持有 lock 的情況下「預佔位」（append 時間戳），
  確保 6 個 thread 依序取得位置，超額 thread 會 blocking wait。
  record_call() 改為 no-op（槽位已在 wait_if_needed 預佔）。

配額計算（kimi-k2.5，40 RPM）：
  每次完整分析 = 8 NVIDIA calls（6 Agent + Arbitrator + Chief Analyst）
  最快每分鐘 = 40 ÷ 8 = 5 次完整分析
  Scanner 掃描 N 支股票 = N × 1 call，需留 buffer
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

    ⚠️ 預佔位設計：wait_if_needed() 在取得 lock 後直接 append 時間戳，
    防止多 thread 同時通過 rate check 導致突發超限（TOCTOU race condition）。
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
        檢查目前是否可以發出新請求（不 blocking，不預佔位）。
        僅供狀態查詢，實際呼叫前請用 wait_if_needed()。
        """
        with self._lock:
            now = time.time()
            self._clean_window(now)
            return len(self._window) < self._rpm_limit

    def wait_if_needed(self) -> None:
        """
        若目前 RPM 已達上限，blocking wait 直到視窗滑動出空位。

        ⚠️ 預佔位（pre-allocation）：
        取得空位後立即 append 時間戳（在 lock 內），
        防止多個 thread 同時認為有空位而全部通過（TOCTOU）。
        呼叫此方法後，呼叫者的「槽位」已被預佔，無需再呼叫 record_call()。
        """
        while True:
            with self._lock:
                now = time.time()
                self._clean_window(now)
                if len(self._window) < self._rpm_limit:
                    # ✅ 有空位：預佔位（立即記錄，防止其他 thread 同時通過）
                    self._window.append(now)
                    return

                # 計算需等待的秒數：等到最舊的時間戳超過 60 秒
                oldest = self._window[0]
                wait_sec = (oldest + 60) - now + 0.1  # +0.1s buffer

            if wait_sec > 0:
                logger.warning(
                    f"[NvidiaRateLimiter] RPM 達上限 ({self._rpm_limit})，"
                    f"等待 {wait_sec:.1f}s... "
                    f"（目前 {len(self._window)}/{self._rpm_limit}）"
                )
                time.sleep(wait_sec)

    def record_call(self) -> None:
        """
        No-op：槽位已在 wait_if_needed() 內預佔，無需重複記錄。
        保留此方法供舊呼叫相容。
        """
        pass  # Pre-allocation in wait_if_needed() already handles this

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
