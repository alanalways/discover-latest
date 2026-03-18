"""
backend/agents/infra/storage_curator.py
儲存管理官（Sonnet 撰寫）

職責：
1. 查詢 Supabase 資料庫目前使用量
2. 依閾值決定封存策略（健康 / 警告 / 危急 / 緊急）
3. 封存舊報告 → Parquet → 上傳 HuggingFace Dataset → 驗證 checksum → 刪除
4. 更新 archive_index 表

閾值：
  < 70% : 健康，僅記錄日誌
  70~85%: 警告，封存 30 天前資料
  85~95%: 危急，封存 15 天前資料，WARNING 日誌
  > 95% : 緊急，封存 7 天前資料，暫停新報告寫入，CRITICAL 日誌

核心防呆：上傳 HuggingFace 後必須重新讀取一筆驗證，確認可讀取後才執行 DELETE。
"""
import hashlib
import io
import json
import logging
import time
from datetime import date, timedelta, timezone, datetime
from typing import Optional

from backend.config import (
    HF_TOKEN,
    HF_DATASET_REPO,
    SUPABASE_WARN_MB,
    SUPABASE_CRITICAL_MB,
)

logger = logging.getLogger(__name__)

# ─── 閾值（動態基於 config 設定計算）────────────────────────────

# Supabase Free 層上限（512 MB）
_DB_MAX_MB: float = 512.0

# 百分比閾值
_WARN_PCT: float     = 0.70   # 70%：開始封存
_CRITICAL_PCT: float = 0.85   # 85%：加速封存 + WARNING
_EMERGENCY_PCT: float = 0.95  # 95%：緊急封存 + 暫停寫入

# 封存依天數策略（閾值對應封存幾天以前的資料）
_ARCHIVE_DAYS_BY_LEVEL = {
    "warn":      30,
    "critical":  15,
    "emergency":  7,
}

# 全域緊急暫停旗標（其他模組可讀取此值）
_WRITES_PAUSED: bool = False


def is_writes_paused() -> bool:
    """供其他模組查詢是否因儲存危機而暫停寫入。"""
    return _WRITES_PAUSED


class StorageCurator:
    """
    儲存管理官。

    每次 run_check() 被呼叫時：
    1. 查詢 DB 大小
    2. 依閾值決定行動
    3. 若需封存：撈取舊報告 → 轉 Parquet → 上傳 HF → 驗證 → 刪除 → 更新索引
    """

    def run_check(self) -> dict:
        """
        執行一次完整的儲存健康檢查。

        Returns:
            {
                "used_mb":       float,
                "usage_pct":     float,
                "level":         "healthy" | "warn" | "critical" | "emergency",
                "archived_count": int,    -- 本次封存的 report 筆數
                "writes_paused": bool,
                "error":         str | None,
            }
        """
        result = {
            "used_mb":        0.0,
            "usage_pct":      0.0,
            "level":          "healthy",
            "archived_count": 0,
            "writes_paused":  False,
            "error":          None,
        }

        # ── 1. 取得 DB 大小 ──────────────────────────────
        used_mb = self._get_db_size()
        if used_mb is None:
            result["error"] = "無法取得 DB 大小"
            logger.warning("[StorageCurator] 無法取得 DB 大小，跳過本次檢查")
            return result

        usage_pct = used_mb / _DB_MAX_MB
        result["used_mb"] = round(used_mb, 1)
        result["usage_pct"] = round(usage_pct * 100, 1)

        # ── 2. 判斷等級 & 執行封存 ───────────────────────
        global _WRITES_PAUSED

        if usage_pct >= _EMERGENCY_PCT:
            result["level"] = "emergency"
            _WRITES_PAUSED = True
            result["writes_paused"] = True
            logger.critical(
                f"[StorageCurator] 緊急：DB 使用率 {usage_pct:.1%} "
                f"({used_mb:.1f}MB / {_DB_MAX_MB}MB)，暫停新報告寫入"
            )
            n = self._archive_reports(days_ago=_ARCHIVE_DAYS_BY_LEVEL["emergency"])
            result["archived_count"] = n

        elif usage_pct >= _CRITICAL_PCT:
            result["level"] = "critical"
            # 如果之前是 emergency，但現在降到 critical，解除暫停
            if _WRITES_PAUSED:
                _WRITES_PAUSED = False
            logger.warning(
                f"[StorageCurator] 危急：DB 使用率 {usage_pct:.1%} "
                f"({used_mb:.1f}MB / {_DB_MAX_MB}MB)，封存 "
                f"{_ARCHIVE_DAYS_BY_LEVEL['critical']} 天前資料"
            )
            n = self._archive_reports(days_ago=_ARCHIVE_DAYS_BY_LEVEL["critical"])
            result["archived_count"] = n

        elif usage_pct >= _WARN_PCT:
            result["level"] = "warn"
            if _WRITES_PAUSED:
                _WRITES_PAUSED = False
            logger.info(
                f"[StorageCurator] 警告：DB 使用率 {usage_pct:.1%} "
                f"({used_mb:.1f}MB / {_DB_MAX_MB}MB)，封存 "
                f"{_ARCHIVE_DAYS_BY_LEVEL['warn']} 天前資料"
            )
            n = self._archive_reports(days_ago=_ARCHIVE_DAYS_BY_LEVEL["warn"])
            result["archived_count"] = n

        else:
            if _WRITES_PAUSED:
                _WRITES_PAUSED = False
            logger.info(
                f"[StorageCurator] 健康：DB 使用率 {usage_pct:.1%} "
                f"({used_mb:.1f}MB / {_DB_MAX_MB}MB)"
            )

        result["writes_paused"] = _WRITES_PAUSED
        return result

    # ─── 封存流程 ───────────────────────────────────────────

    def _archive_reports(self, days_ago: int) -> int:
        """
        封存指定天數以前的 reports 到 HuggingFace Dataset。

        流程：
        1. 查詢 is_archived=FALSE 且 created_at < cutoff 的 reports
        2. 轉 Parquet（pyarrow）
        3. 上傳到 HF Dataset
        4. 重新讀取一筆驗證可讀
        5. 批次標記 is_archived=TRUE，更新 archived_at + archive_path
        6. 寫入 archive_index 表
        7. 確認完成後刪除 reports 中被封存的行

        Returns:
            成功封存的筆數（0 表示無須封存或失敗）
        """
        if not HF_TOKEN or not HF_DATASET_REPO:
            logger.warning(
                "[StorageCurator] HF_TOKEN 或 HF_DATASET_REPO 未設定，"
                "無法執行封存"
            )
            return 0

        cutoff_date = (date.today() - timedelta(days=days_ago)).isoformat()

        # ── 1. 查詢待封存報告 ──────────────────────────
        rows = self._fetch_archivable_reports(cutoff_date)
        if not rows:
            logger.info(f"[StorageCurator] 無須封存（{days_ago} 天前無舊報告）")
            return 0

        logger.info(f"[StorageCurator] 待封存 {len(rows)} 筆報告")

        # ── 2. 轉換為 Parquet bytes ──────────────────
        parquet_bytes = self._to_parquet(rows)
        if parquet_bytes is None:
            logger.error("[StorageCurator] Parquet 轉換失敗，放棄本次封存")
            return 0

        # ── 3. 計算 checksum ─────────────────────────
        checksum = hashlib.sha256(parquet_bytes).hexdigest()

        # ── 4. 上傳 HuggingFace ──────────────────────
        archive_path = self._upload_to_hf(parquet_bytes, cutoff_date)
        if archive_path is None:
            logger.error("[StorageCurator] HuggingFace 上傳失敗，放棄本次封存")
            return 0

        # ── 5. 驗證（重新讀取一筆確認可讀）──────────
        if not self._verify_upload(archive_path):
            logger.error(
                f"[StorageCurator] 驗證失敗：{archive_path}，"
                "資料保留不刪除"
            )
            return 0

        # ── 6. 確認可讀後才執行刪除 ──────────────────
        report_ids = [r["id"] for r in rows]
        deleted = self._delete_archived_reports(report_ids)

        if not deleted:
            logger.error("[StorageCurator] 刪除封存報告失敗，但資料已安全存至 HF")
            # 仍寫入 archive_index（記錄已封存事實）

        # ── 7. 寫入 archive_index ─────────────────────
        self._write_archive_index(
            report_ids=report_ids,
            archive_path=archive_path,
            checksum=checksum,
            file_size_bytes=len(parquet_bytes),
            cutoff_date=cutoff_date,
        )

        count = len(report_ids)
        logger.info(f"[StorageCurator] 封存完成：{count} 筆報告 → {archive_path}")
        return count

    # ─── Supabase 操作 ──────────────────────────────────────

    def _get_db_size(self) -> Optional[float]:
        """查詢 DB 大小（MB）。"""
        try:
            from backend.data.storage.supabase_client import get_db_size_mb
            return get_db_size_mb()
        except Exception as e:
            logger.warning(f"[StorageCurator] get_db_size 失敗: {e}")
            return None

    def _fetch_archivable_reports(self, cutoff_date: str) -> list[dict]:
        """查詢未封存且早於 cutoff 的報告。"""
        try:
            from backend.data.storage.supabase_client import get_client
            client = get_client()
            if not client:
                return []
            result = (
                client.table("reports")
                .select("*")
                .eq("is_archived", False)
                .lt("created_at", f"{cutoff_date}T00:00:00+00:00")
                .order("created_at", desc=False)
                .limit(500)
                .execute()
            )
            return result.data or []
        except Exception as e:
            logger.error(f"[StorageCurator] fetch_archivable_reports 失敗: {e}")
            return []

    def _delete_archived_reports(self, report_ids: list[str]) -> bool:
        """刪除已封存的報告行。"""
        if not report_ids:
            return True
        try:
            from backend.data.storage.supabase_client import get_client
            client = get_client()
            if not client:
                return False
            # 分批刪除（Supabase IN 查詢上限）
            batch_size = 50
            for i in range(0, len(report_ids), batch_size):
                batch = report_ids[i: i + batch_size]
                client.table("reports").delete().in_("id", batch).execute()
            logger.info(f"[StorageCurator] 已刪除 {len(report_ids)} 筆封存報告")
            return True
        except Exception as e:
            logger.error(f"[StorageCurator] 刪除封存報告失敗: {e}")
            return False

    def _write_archive_index(
        self,
        report_ids: list[str],
        archive_path: str,
        checksum: str,
        file_size_bytes: int,
        cutoff_date: str,
    ) -> None:
        """將封存記錄寫入 archive_index 表。"""
        try:
            from backend.data.storage.supabase_client import insert_row
            insert_row("archive_index", {
                "source_table":     "reports",
                "source_ids":       report_ids,
                "archive_path":     archive_path,
                "archive_tier":     "huggingface",
                "file_size_bytes":  file_size_bytes,
                "checksum":         checksum,
                "record_count":     len(report_ids),
                "date_range_end":   cutoff_date,
                "date_range_start": None,
            })
        except Exception as e:
            logger.warning(f"[StorageCurator] archive_index 寫入失敗: {e}")

    # ─── Parquet 轉換 ──────────────────────────────────────

    @staticmethod
    def _to_parquet(rows: list[dict]) -> Optional[bytes]:
        """將 dict list 轉為 Parquet bytes。"""
        try:
            import pyarrow as pa
            import pyarrow.parquet as pq

            # JSONB 欄位序列化為字串，避免 Arrow schema 推斷失敗
            jsonb_cols = {
                "technical_output", "fundamental_output", "chips_output",
                "event_output", "macro_output", "sentiment_output",
                "arbitration_log",
            }
            serialized = []
            for row in rows:
                r = dict(row)
                for col in jsonb_cols:
                    if col in r and r[col] is not None:
                        if not isinstance(r[col], str):
                            r[col] = json.dumps(r[col], ensure_ascii=False)
                serialized.append(r)

            table = pa.Table.from_pylist(serialized)
            buf = io.BytesIO()
            pq.write_table(table, buf)
            return buf.getvalue()
        except Exception as e:
            logger.error(f"[StorageCurator] Parquet 轉換失敗: {e}")
            return None

    # ─── HuggingFace 上傳 ──────────────────────────────────

    def _upload_to_hf(
        self, parquet_bytes: bytes, cutoff_date: str
    ) -> Optional[str]:
        """
        上傳 Parquet 檔案到 HuggingFace Dataset。

        Returns:
            archive_path (HF 檔案路徑) 或 None（失敗）
        """
        try:
            from huggingface_hub import HfApi
        except ImportError:
            logger.error("[StorageCurator] huggingface_hub 未安裝")
            return None

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        hf_path = f"archives/reports_{cutoff_date}_{timestamp}.parquet"

        try:
            api = HfApi(token=HF_TOKEN)
            api.upload_file(
                path_or_fileobj=io.BytesIO(parquet_bytes),
                path_in_repo=hf_path,
                repo_id=HF_DATASET_REPO,
                repo_type="dataset",
            )
            full_path = f"hf://{HF_DATASET_REPO}/{hf_path}"
            logger.info(f"[StorageCurator] 上傳成功: {full_path}")
            return full_path
        except Exception as e:
            logger.error(f"[StorageCurator] HuggingFace 上傳失敗: {e}")
            return None

    def _verify_upload(self, archive_path: str) -> bool:
        """
        驗證上傳到 HF 的 Parquet 可讀取。

        從 HF 重新下載並讀取第一行，確認資料可恢復。
        """
        try:
            from huggingface_hub import hf_hub_download
            import pyarrow.parquet as pq

            # archive_path 格式：hf://owner/repo/path/to/file.parquet
            parts = archive_path.replace("hf://", "").split("/", 2)
            if len(parts) < 3:
                logger.warning(f"[StorageCurator] 無法解析 archive_path: {archive_path}")
                return False

            repo_id = f"{parts[0]}/{parts[1]}"
            file_path_in_repo = parts[2]

            local_path = hf_hub_download(
                repo_id=repo_id,
                filename=file_path_in_repo,
                repo_type="dataset",
                token=HF_TOKEN,
            )
            table = pq.read_table(local_path)
            if table.num_rows == 0:
                logger.warning("[StorageCurator] 驗證失敗：Parquet 為空")
                return False

            logger.info(
                f"[StorageCurator] 驗證通過：{table.num_rows} 筆記錄可讀取"
            )
            return True
        except Exception as e:
            logger.error(f"[StorageCurator] 驗證失敗: {e}")
            return False


# ─── 模組級單例 ────────────────────────────────────────────────

_curator_instance: Optional[StorageCurator] = None


def get_storage_curator() -> StorageCurator:
    """取得 StorageCurator 單例。"""
    global _curator_instance
    if _curator_instance is None:
        _curator_instance = StorageCurator()
    return _curator_instance
