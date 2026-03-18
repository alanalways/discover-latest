"""
DiskCache — 磁碟持久化快取（Redis 替代方案）
適用於 HuggingFace Spaces 環境，利用本地檔案系統做跨重啟快取
"""

from __future__ import annotations

import json
import os
import time
import threading
import logging
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# 快取目錄
_CACHE_DIR = Path(os.environ.get("DISK_CACHE_DIR", "/tmp/dl_cache"))
_CACHE_DIR.mkdir(parents=True, exist_ok=True)

_lock = threading.Lock()


def _safe_filename(key: str) -> str:
    """將 cache key 轉成安全的檔名"""
    import hashlib
    safe = key.replace("/", "_").replace("\\", "_").replace(":", "_")
    if len(safe) > 80:
        h = hashlib.md5(key.encode()).hexdigest()[:12]
        safe = safe[:60] + "_" + h
    return safe + ".json"


def get(key: str) -> Optional[Any]:
    """讀取快取，過期則回傳 None"""
    filepath = _CACHE_DIR / _safe_filename(key)
    if not filepath.exists():
        return None

    try:
        with _lock:
            data = json.loads(filepath.read_text(encoding="utf-8"))

        expires_at = data.get("expires_at", 0)
        if expires_at > 0 and time.time() > expires_at:
            # 過期，刪除
            try:
                filepath.unlink(missing_ok=True)
            except Exception:
                pass
            return None

        return data.get("value")
    except Exception as e:
        logger.debug("DiskCache read error for %s: %s", key, e)
        return None


def set(key: str, value: Any, ttl: int = 300) -> None:
    """寫入快取，ttl 為秒數（0 = 永不過期）"""
    filepath = _CACHE_DIR / _safe_filename(key)
    data = {
        "key": key,
        "value": value,
        "created_at": time.time(),
        "expires_at": time.time() + ttl if ttl > 0 else 0,
    }

    try:
        with _lock:
            filepath.write_text(json.dumps(data, ensure_ascii=False, default=str), encoding="utf-8")
    except Exception as e:
        logger.debug("DiskCache write error for %s: %s", key, e)


def delete(key: str) -> None:
    """刪除快取"""
    filepath = _CACHE_DIR / _safe_filename(key)
    try:
        filepath.unlink(missing_ok=True)
    except Exception:
        pass


def clear() -> None:
    """清除所有快取"""
    try:
        for f in _CACHE_DIR.glob("*.json"):
            f.unlink(missing_ok=True)
        logger.info("DiskCache cleared")
    except Exception as e:
        logger.debug("DiskCache clear error: %s", e)


def cleanup_expired() -> int:
    """清理所有過期的快取檔案，回傳清理數量"""
    count = 0
    now = time.time()
    try:
        for f in _CACHE_DIR.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                expires_at = data.get("expires_at", 0)
                if expires_at > 0 and now > expires_at:
                    f.unlink(missing_ok=True)
                    count += 1
            except Exception:
                pass
    except Exception:
        pass
    return count


def get_stats() -> dict:
    """取得快取統計"""
    total = 0
    expired = 0
    total_size = 0
    now = time.time()
    try:
        for f in _CACHE_DIR.glob("*.json"):
            total += 1
            total_size += f.stat().st_size
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                if data.get("expires_at", 0) > 0 and now > data["expires_at"]:
                    expired += 1
            except Exception:
                pass
    except Exception:
        pass

    return {
        "total_entries": total,
        "expired_entries": expired,
        "active_entries": total - expired,
        "total_size_kb": round(total_size / 1024, 1),
        "cache_dir": str(_CACHE_DIR),
    }
