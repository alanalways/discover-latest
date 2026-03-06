"""Tests for services/cache_manager.py"""

import time
import threading
from services.cache_manager import CacheStore, CacheRegistry, cache_registry


def test_cache_store_basic_get_set():
    store = CacheStore(name="test", ttl_sec=10, max_size=100)
    assert store.get("foo") is None
    store.set("foo", "bar")
    assert store.get("foo") == "bar"


def test_cache_store_ttl_expiry():
    store = CacheStore(name="test_ttl", ttl_sec=1, max_size=100)
    store.set("key", "value")
    assert store.get("key") == "value"
    time.sleep(1.1)
    assert store.get("key") is None


def test_cache_store_max_size_eviction():
    store = CacheStore(name="test_evict", ttl_sec=300, max_size=4)
    for i in range(6):
        store.set(f"k{i}", f"v{i}")
    # Should have evicted some entries
    stats = store.stats()
    assert stats["size"] <= 4


def test_cache_store_delete():
    store = CacheStore(name="test_del", ttl_sec=300, max_size=100)
    store.set("a", 1)
    store.delete("a")
    assert store.get("a") is None


def test_cache_store_clear():
    store = CacheStore(name="test_clear", ttl_sec=300, max_size=100)
    store.set("x", 1)
    store.set("y", 2)
    store.clear()
    assert store.get("x") is None
    assert store.get("y") is None


def test_cache_store_stats():
    store = CacheStore(name="test_stats", ttl_sec=300, max_size=100)
    store.set("a", 1)
    store.get("a")  # hit
    store.get("b")  # miss
    stats = store.stats()
    assert stats["hits"] == 1
    assert stats["misses"] == 1
    assert stats["hit_rate"] == 50.0


def test_cache_registry():
    reg = CacheRegistry()
    s1 = reg.create("cache_a", ttl_sec=60, max_size=50)
    s2 = reg.create("cache_b", ttl_sec=120, max_size=100)
    s1.set("k", "v")
    all_stats = reg.get_all_stats()
    assert len(all_stats) == 2
    names = {s["name"] for s in all_stats}
    assert "cache_a" in names
    assert "cache_b" in names


def test_cache_store_thread_safety():
    store = CacheStore(name="test_threads", ttl_sec=300, max_size=1000)
    errors = []

    def writer(start):
        try:
            for i in range(100):
                store.set(f"w{start}_{i}", i)
        except Exception as e:
            errors.append(e)

    def reader(start):
        try:
            for i in range(100):
                store.get(f"w{start}_{i}")
        except Exception as e:
            errors.append(e)

    threads = []
    for t in range(4):
        threads.append(threading.Thread(target=writer, args=(t,)))
        threads.append(threading.Thread(target=reader, args=(t,)))
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(errors) == 0
