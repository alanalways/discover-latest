"""
同步排程器 — 管理 SQLite 持久化與 Supabase 備份
- 啟動時：從 HF Dataset Repo 下載 SQLite → /tmp，若無則從 Supabase 拉取
- 每小時：SQLite → HF Dataset Repo 上傳備份
- 每日凌晨 3 點：SQLite → Supabase 備份
- 每月 1 號：清理 Supabase 90 天前的舊資料
- 即時偵測：Supabase 容量不足 10% 時自動整理
"""
import logging
import os
import shutil
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

_TZ = "Asia/Taipei"
_DAILY_HOUR = 3  # 每日 Supabase 備份時間（凌晨 3 點）
_CLEANUP_RETAIN_DAYS = 90
_CHECK_INTERVAL_SEC = 3600  # 每小時檢查一次

# HF Dataset Repo 設定
_HF_REPO_ID = os.environ.get("HF_DATASET_REPO", "")  # 如 "alanalways/discover-latest-data"
_HF_DB_FILENAME = "discover.db"
_SQLITE_PATH = "/tmp/discover.db"

# Supabase 容量上限
_SUPABASE_FREE_LIMIT_MB = 500
_CAPACITY_THRESHOLD = 0.10


class SyncScheduler:

    def __init__(self):
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._last_backup_supabase: Optional[str] = None
        self._last_backup_hf: Optional[float] = None
        self._last_cleanup: Optional[str] = None

    def start(self):
        if self._running:
            return
        self._running = True
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="SyncScheduler")
        self._thread.start()
        logger.info("[SyncScheduler] 排程啟動")

    def stop(self):
        self._running = False
        self._stop_event.set()
        thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout=2.0)

    # ────────────────────── 首次同步：還原 SQLite ──────────────────────

    def initial_sync(self):
        """啟動時還原 SQLite：HF Dataset Repo → Supabase fallback"""
        from adapters.local_store import local_store

        # 1. 嘗試從 HF Dataset Repo 下載
        if self._download_from_hf():
            # 重新初始化 local_store（因為 db 檔案被替換了）
            local_store._init_db()
            if not local_store.is_empty():
                stats = local_store.get_stats()
                logger.info("[SyncScheduler] 從 HF Dataset Repo 還原成功: %s", stats)
                return

        # 2. HF 無資料 → 從 Supabase 拉取
        if not local_store.is_empty():
            stats = local_store.get_stats()
            logger.info("[SyncScheduler] SQLite 已有資料: %s", stats)
            return

        logger.info("[SyncScheduler] SQLite 為空，從 Supabase 拉取...")
        self._sync_from_supabase(local_store)

    def _sync_from_supabase(self, local_store):
        """從 Supabase 拉取完整資料到 SQLite"""
        try:
            from adapters.supabase_adapter import supabase_adapter

            # 拉 auth.users
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
            logger.info("[SyncScheduler] Supabase 同步完成: %s", stats)
        except Exception as e:
            logger.warning("[SyncScheduler] Supabase 同步失敗: %s", e)

    # ────────────────────── HF Dataset Repo 操作 ──────────────────────

    def _get_hf_api(self):
        """取得 HfApi 實例（需要 HF_TOKEN 環境變數）"""
        try:
            from huggingface_hub import HfApi
            token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_TOKEN")
            if not token:
                logger.debug("[SyncScheduler] 未設定 HF_TOKEN，HF 備份停用")
                return None
            return HfApi(token=token)
        except ImportError:
            logger.debug("[SyncScheduler] huggingface_hub 未安裝")
            return None

    def _get_repo_id(self) -> str:
        """取得 Dataset Repo ID"""
        if _HF_REPO_ID:
            return _HF_REPO_ID
        # 自動從 SPACE_ID 推算（如 alanalways/discover-latest-v2 → alanalways/discover-latest-data）
        space_id = os.environ.get("SPACE_ID", "")
        if "/" in space_id:
            owner = space_id.split("/")[0]
            return f"{owner}/discover-latest-data"
        return ""

    def _download_from_hf(self) -> bool:
        """從 HF Dataset Repo 下載 SQLite"""
        api = self._get_hf_api()
        repo_id = self._get_repo_id()
        if not api or not repo_id:
            return False

        try:
            from huggingface_hub import hf_hub_download
            token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_TOKEN")
            local_path = hf_hub_download(
                repo_id=repo_id,
                filename=_HF_DB_FILENAME,
                repo_type="dataset",
                token=token,
                local_dir="/tmp",
                local_dir_use_symlinks=False,
            )
            # hf_hub_download 可能下載到不同位置，確保在 /tmp/discover.db
            if local_path and os.path.isfile(local_path) and local_path != _SQLITE_PATH:
                shutil.copy2(local_path, _SQLITE_PATH)
            logger.info("[SyncScheduler] HF Dataset Repo 下載成功: %s", repo_id)
            return True
        except Exception as e:
            logger.info("[SyncScheduler] HF Dataset Repo 下載失敗（可能是首次）: %s", e)
            return False

    def _upload_to_hf(self) -> bool:
        """上傳 SQLite 到 HF Dataset Repo"""
        api = self._get_hf_api()
        repo_id = self._get_repo_id()
        if not api or not repo_id:
            return False

        if not os.path.isfile(_SQLITE_PATH):
            return False

        try:
            # 確保 repo 存在
            try:
                api.create_repo(repo_id=repo_id, repo_type="dataset", exist_ok=True, private=True)
            except Exception:
                pass

            api.upload_file(
                path_or_fileobj=_SQLITE_PATH,
                path_in_repo=_HF_DB_FILENAME,
                repo_id=repo_id,
                repo_type="dataset",
                commit_message=f"Auto backup {self._now().strftime('%Y-%m-%d %H:%M')}",
            )
            logger.info("[SyncScheduler] HF Dataset Repo 上傳成功: %s", repo_id)
            return True
        except Exception as e:
            logger.warning("[SyncScheduler] HF Dataset Repo 上傳失敗: %s", e)
            return False

    # ────────────────────── 主循環 ──────────────────────

    def _loop(self):
        while self._running:
            try:
                now = self._now()

                # 每小時：上傳到 HF Dataset Repo
                if self._last_backup_hf is None or (time.time() - self._last_backup_hf) > 3600:
                    if self._upload_to_hf():
                        self._last_backup_hf = time.time()

                # 每日備份到 Supabase
                today_key = now.strftime("%Y-%m-%d")
                if now.hour >= _DAILY_HOUR and self._last_backup_supabase != today_key:
                    self._do_supabase_backup()
                    self._last_backup_supabase = today_key

                # 每月清理（每月 1 號）
                month_key = now.strftime("%Y-%m")
                if now.day == 1 and self._last_cleanup != month_key:
                    self._do_cleanup()
                    self._last_cleanup = month_key

                # 容量檢測
                self._check_capacity()

            except Exception as e:
                logger.warning("[SyncScheduler] 排程循環異常: %s", e)

            if self._stop_event.wait(_CHECK_INTERVAL_SEC):
                break

    # ────────────────────── Supabase 每日備份 ──────────────────────

    def _do_supabase_backup(self):
        logger.info("[SyncScheduler] 開始每日 Supabase 備份...")
        try:
            from adapters.local_store import local_store
            from adapters.supabase_adapter import supabase_adapter

            data = local_store.export_all()

            for u in data.get("users", []):
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

            for r in data.get("ai_usage", []):
                supabase_adapter._request(
                    "POST", "ai_usage",
                    params={"on_conflict": "user_id,date"},
                    json={"user_id": r.get("user_id"), "date": r.get("date"),
                          "count": r.get("count", 0)},
                    use_service_key=True, silent=True,
                )

            for s in data.get("user_subscriptions", []):
                supabase_adapter._request(
                    "POST", "user_subscriptions",
                    params={"on_conflict": "user_id"},
                    json={"user_id": s.get("user_id"), "tier": s.get("tier", "free"),
                          "expires_at": s.get("expires_at")},
                    use_service_key=True, silent=True,
                )

            logger.info("[SyncScheduler] Supabase 備份完成")
        except Exception as e:
            logger.warning("[SyncScheduler] Supabase 備份失敗: %s", e)

    # ────────────────────── 每月清理 ──────────────────────

    def _do_cleanup(self):
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
        try:
            from adapters.supabase_adapter import supabase_adapter
            size_mb = self._estimate_supabase_size_mb(supabase_adapter)
            if size_mb is None:
                return

            remaining_pct = max(0, (_SUPABASE_FREE_LIMIT_MB - size_mb) / _SUPABASE_FREE_LIMIT_MB)

            if remaining_pct < _CAPACITY_THRESHOLD:
                logger.warning(
                    "[SyncScheduler] ⚠️ Supabase 容量不足! %.1fMB/%dMB（剩餘 %.1f%%），啟動緊急清理",
                    size_mb, _SUPABASE_FREE_LIMIT_MB, remaining_pct * 100,
                )
                self._emergency_cleanup(supabase_adapter)
            else:
                logger.debug("[SyncScheduler] Supabase 容量: %.1fMB/%dMB", size_mb, _SUPABASE_FREE_LIMIT_MB)
        except Exception as e:
            logger.debug("[SyncScheduler] 容量檢測略過: %s", e)

    def _estimate_supabase_size_mb(self, adapter) -> Optional[float]:
        try:
            result = adapter._rpc("get_db_size_mb", {})
            if isinstance(result, (int, float)):
                return float(result)
            if isinstance(result, list) and result:
                row = result[0] if isinstance(result[0], dict) else {}
                size = row.get("size_mb") or row.get("size") or row.get("result")
                if size is not None:
                    return float(size)
            return None
        except Exception:
            return None

    def _emergency_cleanup(self, adapter):
        try:
            cutoff = (self._now() - timedelta(days=30)).strftime("%Y-%m-%d")
            adapter._request(
                "DELETE", "ai_usage",
                params={"date": f"lt.{cutoff}"},
                use_service_key=True, silent=True,
            )
            logger.info("[SyncScheduler] 緊急清理完成（ai_usage %s 以前）", cutoff)
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
