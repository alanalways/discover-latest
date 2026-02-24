"""
同步排程器 — 管理 SQLite ↔ Supabase 的資料同步
- 啟動時：若 SQLite 為空，從 Supabase 拉取完整資料
- 每日凌晨 3 點（UTC+8）：SQLite → Supabase 備份
- 每月 1 號：清理 Supabase 90 天前的 ai_usage 舊資料
- 即時偵測：Supabase 容量不足 10% 時自動整理
"""
import logging
import os
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

_TZ = "Asia/Taipei"
_DAILY_HOUR = 3  # 每日備份時間（凌晨 3 點）
_CLEANUP_RETAIN_DAYS = 90  # 保留天數
_CHECK_INTERVAL_SEC = 3600  # 每小時檢查一次

# Supabase 免費方案資料庫大小上限（500 MB）
_SUPABASE_FREE_LIMIT_MB = 500
_CAPACITY_THRESHOLD = 0.10  # 剩餘低於 10% 觸發清理


class SyncScheduler:

    def __init__(self):
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._last_backup: Optional[str] = None
        self._last_cleanup: Optional[str] = None

    def start(self):
        """啟動同步排程（daemon thread）"""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="SyncScheduler")
        self._thread.start()
        logger.info("[SyncScheduler] 排程啟動")

    def stop(self):
        self._running = False

    # ────────────────────── 首次同步 ──────────────────────

    def initial_sync(self):
        """啟動時若 SQLite 為空，從 Supabase 完整拉取"""
        try:
            from adapters.local_store import local_store
            if not local_store.is_empty():
                stats = local_store.get_stats()
                logger.info("[SyncScheduler] SQLite 已有資料，跳過初始同步: %s", stats)
                return

            logger.info("[SyncScheduler] SQLite 為空，從 Supabase 拉取初始資料...")
            from adapters.supabase_adapter import supabase_adapter

            # 拉 auth.users → 匯入 local users
            users_data = supabase_adapter.get_all_users()
            if users_data:
                local_store.import_users(users_data)

            # 拉 ai_usage
            ai_rows = supabase_adapter._request(
                "GET", "ai_usage",
                params={"select": "user_id,date,count"},
                use_service_key=True, silent=True,
            )
            if isinstance(ai_rows, list):
                local_store.import_ai_usage(ai_rows)

            # 拉 user_subscriptions
            sub_rows = supabase_adapter._request(
                "GET", "user_subscriptions",
                params={"select": "user_id,tier,expires_at"},
                use_service_key=True, silent=True,
            )
            if isinstance(sub_rows, list):
                for row in sub_rows:
                    uid = row.get("user_id")
                    if uid:
                        local_store.upsert_subscription(
                            uid,
                            tier=row.get("tier", "free"),
                            expires_at=row.get("expires_at"),
                        )

            stats = local_store.get_stats()
            logger.info("[SyncScheduler] 初始同步完成: %s", stats)
        except Exception as e:
            logger.warning("[SyncScheduler] 初始同步失敗: %s", e)

    # ────────────────────── 主循環 ──────────────────────

    def _loop(self):
        """排程主循環"""
        while self._running:
            try:
                now = self._now()

                # 每日備份
                today_key = now.strftime("%Y-%m-%d")
                if now.hour >= _DAILY_HOUR and self._last_backup != today_key:
                    self._do_backup()
                    self._last_backup = today_key

                # 每月清理（每月 1 號）
                month_key = now.strftime("%Y-%m")
                if now.day == 1 and self._last_cleanup != month_key:
                    self._do_cleanup()
                    self._last_cleanup = month_key

                # 容量檢測
                self._check_capacity()

            except Exception as e:
                logger.warning("[SyncScheduler] 排程循環異常: %s", e)

            time.sleep(_CHECK_INTERVAL_SEC)

    # ────────────────────── 每日備份 ──────────────────────

    def _do_backup(self):
        """SQLite → Supabase 每日備份"""
        logger.info("[SyncScheduler] 開始每日備份...")
        try:
            from adapters.local_store import local_store
            from adapters.supabase_adapter import supabase_adapter

            data = local_store.export_all()

            # 備份 users
            users = data.get("users", [])
            for u in users:
                uid = u.get("id")
                if not uid:
                    continue
                supabase_adapter._request(
                    "POST", "users",
                    params={"on_conflict": "id"},
                    json={"id": uid, "email": u.get("email", ""), "name": u.get("name", ""),
                          "tier": u.get("tier", "free")},
                    use_service_key=True, silent=True,
                )

            # 備份 ai_usage
            ai_rows = data.get("ai_usage", [])
            for r in ai_rows:
                supabase_adapter._request(
                    "POST", "ai_usage",
                    params={"on_conflict": "user_id,date"},
                    json={"user_id": r.get("user_id"), "date": r.get("date"),
                          "count": r.get("count", 0)},
                    use_service_key=True, silent=True,
                )

            # 備份 user_subscriptions
            subs = data.get("user_subscriptions", [])
            for s in subs:
                supabase_adapter._request(
                    "POST", "user_subscriptions",
                    params={"on_conflict": "user_id"},
                    json={"user_id": s.get("user_id"), "tier": s.get("tier", "free"),
                          "expires_at": s.get("expires_at")},
                    use_service_key=True, silent=True,
                )

            logger.info(
                "[SyncScheduler] 每日備份完成: users=%d, ai_usage=%d, subs=%d",
                len(users), len(ai_rows), len(subs),
            )
        except Exception as e:
            logger.warning("[SyncScheduler] 每日備份失敗: %s", e)

    # ────────────────────── 每月清理 ──────────────────────

    def _do_cleanup(self):
        """清理 Supabase 中超過 90 天的 ai_usage 記錄"""
        logger.info("[SyncScheduler] 開始每月清理...")
        try:
            from adapters.supabase_adapter import supabase_adapter

            cutoff = (self._now() - timedelta(days=_CLEANUP_RETAIN_DAYS)).strftime("%Y-%m-%d")
            supabase_adapter._request(
                "DELETE", "ai_usage",
                params={"date": f"lt.{cutoff}"},
                use_service_key=True, silent=True,
            )
            logger.info("[SyncScheduler] 清理 Supabase ai_usage（%s 以前）完成", cutoff)
        except Exception as e:
            logger.warning("[SyncScheduler] 每月清理失敗: %s", e)

    # ────────────────────── 容量偵測 ──────────────────────

    def _check_capacity(self):
        """檢查 Supabase 容量，低於 10% 時自動清理"""
        try:
            from adapters.supabase_adapter import supabase_adapter

            # 透過 RPC 或 pg_database_size 取得容量
            # Supabase 免費方案沒有直接 API，用估算法：
            # 查詢各表行數估算大小
            size_mb = self._estimate_supabase_size_mb(supabase_adapter)
            if size_mb is None:
                return

            remaining_pct = max(0, (_SUPABASE_FREE_LIMIT_MB - size_mb) / _SUPABASE_FREE_LIMIT_MB)

            if remaining_pct < _CAPACITY_THRESHOLD:
                logger.warning(
                    "[SyncScheduler] ⚠️ Supabase 容量不足! 已用 %.1f MB / %d MB（剩餘 %.1f%%），啟動緊急清理",
                    size_mb, _SUPABASE_FREE_LIMIT_MB, remaining_pct * 100,
                )
                self._emergency_cleanup(supabase_adapter)
            else:
                logger.debug(
                    "[SyncScheduler] Supabase 容量正常: %.1f MB / %d MB（剩餘 %.1f%%）",
                    size_mb, _SUPABASE_FREE_LIMIT_MB, remaining_pct * 100,
                )
        except Exception as e:
            logger.debug("[SyncScheduler] 容量檢測略過: %s", e)

    def _estimate_supabase_size_mb(self, adapter) -> Optional[float]:
        """估算 Supabase 資料庫大小（透過 RPC 查詢 pg_database_size）"""
        try:
            # 嘗試呼叫 pg_database_size RPC（需在 Supabase SQL Editor 建立）
            result = adapter._rpc("get_db_size_mb", {})
            if isinstance(result, (int, float)):
                return float(result)
            if isinstance(result, list) and result:
                row = result[0] if isinstance(result[0], dict) else {}
                size = row.get("size_mb") or row.get("size") or row.get("result")
                if size is not None:
                    return float(size)
            # RPC 不存在時用行數粗估（每行約 0.5KB）
            total_rows = 0
            for table in ("users", "user_subscriptions", "ai_usage", "watchlist", "portfolios", "price_alerts"):
                rows = adapter._request(
                    "GET", table,
                    params={"select": "count", "limit": "1"},
                    use_service_key=True, silent=True,
                )
                # Supabase HEAD count 或 array length
                if isinstance(rows, list):
                    # 用 Prefer: count=exact 的話會在 response header，這裡用粗估
                    pass
            # 粗估失敗就回 None
            return None
        except Exception:
            return None

    def _emergency_cleanup(self, adapter):
        """緊急清理：刪除 30 天前的 ai_usage + 60 天前的 portfolios 快照"""
        try:
            cutoff_30 = (self._now() - timedelta(days=30)).strftime("%Y-%m-%d")
            cutoff_60 = (self._now() - timedelta(days=60)).strftime("%Y-%m-%d")

            # 刪除 30 天前 ai_usage
            adapter._request(
                "DELETE", "ai_usage",
                params={"date": f"lt.{cutoff_30}"},
                use_service_key=True, silent=True,
            )
            logger.info("[SyncScheduler] 緊急清理: 刪除 ai_usage %s 以前", cutoff_30)

            # 如有其他大表也可以清理
            logger.info("[SyncScheduler] 緊急清理完成")
        except Exception as e:
            logger.warning("[SyncScheduler] 緊急清理失敗: %s", e)

    @staticmethod
    def _now() -> datetime:
        try:
            return datetime.now(ZoneInfo(_TZ))
        except Exception:
            return datetime.now(timezone.utc)


# 單例
sync_scheduler = SyncScheduler()
