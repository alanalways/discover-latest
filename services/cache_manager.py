"""Unified in-memory cache manager with TTL, maxsize, and thread safety."""
from __future__ import annotations

import threading
import time
import logging
from typing import Any, Optional
from collections import OrderedDict

logger = logging.getLogger(__name__)


class CacheStore:
    """Thread-safe in-memory cache with TTL and LRU eviction."""

    def __init__(self, name: str, ttl_sec: int = 300, max_size: int = 256):
        self.name = name
        self.ttl_sec = ttl_sec
        self.max_size = max_size
        self._data: OrderedDict[str, dict] = OrderedDict()  # key -> {"value": Any, "ts": float}
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> Optional[Any]:
        """Get value by key. Returns None if expired or missing."""
        with self._lock:
            entry = self._data.get(key)
            if entry is None:
                self._misses += 1
                return None
            if time.time() - entry["ts"] > self.ttl_sec:
                self._data.pop(key, None)
                self._misses += 1
                return None
            self._data.move_to_end(key)
            self._hits += 1
            return entry["value"]

    def set(self, key: str, value: Any) -> None:
        """Set value with current timestamp."""
        with self._lock:
            if key in self._data:
                self._data.move_to_end(key)
                self._data[key] = {"value": value, "ts": time.time()}
            else:
                if len(self._data) >= self.max_size:
                    # Evict oldest 25%
                    evict_count = max(1, self.max_size // 4)
                    for _ in range(evict_count):
                        if self._data:
                            self._data.popitem(last=False)
                self._data[key] = {"value": value, "ts": time.time()}

    def delete(self, key: str) -> None:
        """Remove a single key from the cache."""
        with self._lock:
            self._data.pop(key, None)

    def clear(self) -> None:
        """Clear all entries and reset hit/miss counters."""
        with self._lock:
            self._data.clear()
            self._hits = 0
            self._misses = 0

    def stats(self) -> dict:
        """Return cache statistics snapshot."""
        with self._lock:
            total = self._hits + self._misses
            return {
                "name": self.name,
                "size": len(self._data),
                "max_size": self.max_size,
                "ttl_sec": self.ttl_sec,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": round(self._hits / total * 100, 1) if total > 0 else 0,
            }


class CacheRegistry:
    """Global registry of all cache stores for monitoring."""

    def __init__(self):
        self._stores: dict[str, CacheStore] = {}
        self._lock = threading.Lock()

    def create(self, name: str, ttl_sec: int = 300, max_size: int = 256) -> CacheStore:
        """Create a new CacheStore and register it for monitoring."""
        store = CacheStore(name=name, ttl_sec=ttl_sec, max_size=max_size)
        with self._lock:
            self._stores[name] = store
        return store

    def get_all_stats(self) -> list[dict]:
        """Return stats for every registered cache store."""
        with self._lock:
            return [s.stats() for s in self._stores.values()]


# Global registry singleton
cache_registry = CacheRegistry()
