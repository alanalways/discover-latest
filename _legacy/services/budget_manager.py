"""
Budget Manager — 全 API 統一控額

記憶體 dict 管理 finmind / tavily / gemini 每日預算，
每 5 分鐘批次寫回 Supabase `api_usage_daily` 表。
"""

from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

logger = logging.getLogger(__name__)

_TZ_OFFSET_HOURS = int(os.environ.get("BUDGET_TZ_OFFSET_HOURS", "8"))  # Asia/Taipei


def _today_str() -> str:
    tz = timezone(timedelta(hours=_TZ_OFFSET_HOURS))
    return datetime.now(tz).strftime("%Y-%m-%d")


# Default daily budgets (configurable via env)
_DEFAULT_BUDGETS: Dict[str, int] = {
    "finmind": int(os.environ.get("BUDGET_FINMIND_DAILY", "1100")),
    "tavily": int(os.environ.get("BUDGET_TAVILY_DAILY", "110")),
    "gemini": int(os.environ.get("BUDGET_GEMINI_DAILY", "500")),
}

# Emergency reserves — stop consuming when remaining <= reserve
_RESERVES: Dict[str, int] = {
    "finmind": int(os.environ.get("BUDGET_FINMIND_RESERVE", "50")),
    "tavily": int(os.environ.get("BUDGET_TAVILY_RESERVE", "20")),
    "gemini": int(os.environ.get("BUDGET_GEMINI_RESERVE", "10")),
}

_FLUSH_INTERVAL_SEC = int(os.environ.get("BUDGET_FLUSH_INTERVAL_SEC", "300"))


class BudgetManager:
    """Thread-safe daily budget tracker for all external API providers."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # {date_str: {provider: count}}
        self._usage: Dict[str, Dict[str, int]] = {}
        self._last_flush: float = 0.0
        self._dirty = False

    def _ensure_today(self) -> str:
        today = _today_str()
        with self._lock:
            if today not in self._usage:
                self._usage[today] = {}
                # Prune old dates (keep 3 days max)
                cutoff = (datetime.now(timezone(timedelta(hours=_TZ_OFFSET_HOURS)))
                          - timedelta(days=3)).strftime("%Y-%m-%d")
                for k in list(self._usage.keys()):
                    if k < cutoff:
                        self._usage.pop(k, None)
        return today

    def check_budget(self, provider: str) -> bool:
        """Return True if provider still has budget remaining (above reserve)."""
        provider = provider.lower()
        budget = _DEFAULT_BUDGETS.get(provider, 0)
        reserve = _RESERVES.get(provider, 0)
        if budget <= 0:
            return True  # No budget configured = unlimited

        today = self._ensure_today()
        with self._lock:
            used = self._usage.get(today, {}).get(provider, 0)
        return used < (budget - reserve)

    def consume(self, provider: str, count: int = 1) -> bool:
        """Record usage. Returns True if within budget, False if over."""
        provider = provider.lower()
        today = self._ensure_today()
        budget = _DEFAULT_BUDGETS.get(provider, 0)
        reserve = _RESERVES.get(provider, 0)

        with self._lock:
            day_usage = self._usage.setdefault(today, {})
            current = day_usage.get(provider, 0)
            if budget > 0 and current >= (budget - reserve):
                return False
            day_usage[provider] = current + count
            self._dirty = True

        self._maybe_flush()
        return True

    def get_status(self) -> Dict[str, Any]:
        """Return current budget status for all providers."""
        today = self._ensure_today()
        with self._lock:
            day_usage = dict(self._usage.get(today, {}))

        result: Dict[str, Any] = {}
        for provider, budget in _DEFAULT_BUDGETS.items():
            used = day_usage.get(provider, 0)
            reserve = _RESERVES.get(provider, 0)
            effective_budget = max(0, budget - reserve)
            result[provider] = {
                "budget": budget,
                "reserve": reserve,
                "used": used,
                "remaining": max(0, effective_budget - used),
                "exhausted": used >= effective_budget if budget > 0 else False,
            }
        result["date"] = today
        return result

    def get_remaining(self, provider: str) -> int:
        """Return remaining calls for a provider today."""
        provider = provider.lower()
        budget = _DEFAULT_BUDGETS.get(provider, 0)
        reserve = _RESERVES.get(provider, 0)
        if budget <= 0:
            return 999999

        today = self._ensure_today()
        with self._lock:
            used = self._usage.get(today, {}).get(provider, 0)
        return max(0, budget - reserve - used)

    def _maybe_flush(self) -> None:
        """Flush to Supabase if interval elapsed."""
        now = time.monotonic()
        if now - self._last_flush < _FLUSH_INTERVAL_SEC:
            return
        if not self._dirty:
            return
        self._last_flush = now
        self._dirty = False
        threading.Thread(target=self._flush_to_supabase, daemon=True).start()

    def _flush_to_supabase(self) -> None:
        """Write current usage to Supabase api_usage_daily table."""
        flush_failed = False
        try:
            from adapters.supabase_adapter import supabase_adapter

            today = _today_str()
            with self._lock:
                snapshot = dict(self._usage.get(today, {}))

            if not snapshot:
                return

            for provider, count in snapshot.items():
                try:
                    supabase_adapter._request(
                        "POST",
                        "api_usage_daily",
                        params={"on_conflict": "date,provider"},
                        json={
                            "date": today,
                            "provider": provider,
                            "count": count,
                        },
                        use_service_key=True,
                        silent=True,
                    )
                except Exception as e:
                    flush_failed = True
                    logger.debug("[BudgetManager] flush %s failed: %s", provider, e)
        except Exception as e:
            flush_failed = True
            logger.debug("[BudgetManager] flush error: %s", e)
        finally:
            if flush_failed:
                with self._lock:
                    self._dirty = True


# Singleton
budget_manager = BudgetManager()
