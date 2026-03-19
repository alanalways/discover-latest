"""
backend/core/cache_manager.py
統一記憶體快取管理器（繼承舊版 services/cache_manager.py）

功能：
- Thread-safe LRU 快取，支援 TTL
- 自動驅逐超過 max_size 25% 的最舊項目
- 全域 registry 供監控統計
"""
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
        self._data: OrderedDict[str, dict] = OrderedDict()
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> Optional[Any]:
        """取值，過期或不存在回傳 None。"""
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
        """設值（觸發 LRU 驅逐）。"""
        with self._lock:
            if key in self._data:
                self._data.move_to_end(key)
                self._data[key] = {"value": value, "ts": time.time()}
            else:
                if len(self._data) >= self.max_size:
                    evict_count = max(1, self.max_size // 4)
                    for _ in range(evict_count):
                        if self._data:
                            self._data.popitem(last=False)
                self._data[key] = {"value": value, "ts": time.time()}

    def delete(self, key: str) -> None:
        """刪除單一 key。"""
        with self._lock:
            self._data.pop(key, None)

    def clear(self) -> None:
        """清空所有項目。"""
        with self._lock:
            self._data.clear()
            self._hits = 0
            self._misses = 0

    def stats(self) -> dict:
        """快取統計。"""
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
    """全域快取 registry，供監控查詢。"""

    def __init__(self):
        self._stores: dict[str, CacheStore] = {}
        self._lock = threading.Lock()

    def create(self, name: str, ttl_sec: int = 300, max_size: int = 256) -> CacheStore:
        """建立並註冊新的 CacheStore。"""
        store = CacheStore(name=name, ttl_sec=ttl_sec, max_size=max_size)
        with self._lock:
            self._stores[name] = store
        return store

    def get_all_stats(self) -> list[dict]:
        """回傳所有快取統計。"""
        with self._lock:
            return [s.stats() for s in self._stores.values()]


# 全域 singleton
cache_registry = CacheRegistry()
