"""
backend/data/storage/cold_storage.py
HuggingFace Dataset 冷層存取介面（Sonnet 撰寫）

提供：
- upload_parquet(data, path) → archive_path
- verify_readable(archive_path) → bool
- download_parquet(archive_path) → bytes | None

與 storage_curator.py 解耦，所有 HF API 操作集中於此。
"""

import io
import logging
from typing import Optional

from backend.config import HF_TOKEN, HF_DATASET_REPO

logger = logging.getLogger(__name__)

_AGENT_DISPLAY = "ColdStorage"


def upload_parquet(data: bytes, path: str) -> Optional[str]:
    """
    上傳 Parquet 位元組到 HuggingFace Dataset Repo。

    Args:
        data: Parquet 檔案的原始 bytes
        path: 在 repo 中的相對路徑，例如 "2024/reports_20240301.parquet"

    Returns:
        archive_path（與 path 相同）表示成功；None 表示失敗。
    """
    if not HF_TOKEN or not HF_DATASET_REPO:
        logger.warning(f"[{_AGENT_DISPLAY}] HF_TOKEN 或 HF_DATASET_REPO 未設定，跳過上傳")
        return None

    try:
        from huggingface_hub import HfApi

        api = HfApi(token=HF_TOKEN)
        api.upload_file(
            path_or_fileobj=io.BytesIO(data),
            path_in_repo=path,
            repo_id=HF_DATASET_REPO,
            repo_type="dataset",
            commit_message=f"[cold_storage] archive {path}",
        )
        logger.info(f"[{_AGENT_DISPLAY}] 上傳成功: {path} ({len(data):,} bytes)")
        return path

    except Exception as e:
        logger.error(f"[{_AGENT_DISPLAY}] 上傳失敗 {path}: {e}")
        return None


def verify_readable(archive_path: str) -> bool:
    """
    驗證已上傳的 Parquet 檔案可讀取（至少能讀回第一筆資料）。

    核心防呆：storage_curator 在刪除 Supabase 資料前必須呼叫此函式確認。

    Args:
        archive_path: 在 repo 中的相對路徑

    Returns:
        True 表示可讀取；False 表示驗證失敗（不可刪除來源資料）。
    """
    if not HF_TOKEN or not HF_DATASET_REPO:
        logger.warning(f"[{_AGENT_DISPLAY}] HF 設定不完整，驗證失敗")
        return False

    try:
        data = download_parquet(archive_path)
        if data is None:
            return False

        import pyarrow.parquet as pq
        table = pq.read_table(io.BytesIO(data))

        if len(table) == 0:
            logger.warning(f"[{_AGENT_DISPLAY}] 驗證失敗：{archive_path} 內容為空")
            return False

        logger.info(
            f"[{_AGENT_DISPLAY}] 驗證通過: {archive_path} "
            f"（{len(table):,} 筆資料）"
        )
        return True

    except Exception as e:
        logger.error(f"[{_AGENT_DISPLAY}] 驗證失敗 {archive_path}: {e}")
        return False


def download_parquet(archive_path: str) -> Optional[bytes]:
    """
    從 HuggingFace Dataset Repo 下載 Parquet 檔案。

    Args:
        archive_path: 在 repo 中的相對路徑

    Returns:
        bytes 內容；None 表示失敗。
    """
    if not HF_TOKEN or not HF_DATASET_REPO:
        logger.warning(f"[{_AGENT_DISPLAY}] HF 設定不完整，跳過下載")
        return None

    try:
        from huggingface_hub import HfApi

        api  = HfApi(token=HF_TOKEN)
        resp = api.hf_hub_download(
            repo_id=HF_DATASET_REPO,
            filename=archive_path,
            repo_type="dataset",
        )
        # hf_hub_download 回傳本地快取路徑
        with open(resp, "rb") as f:
            data = f.read()

        logger.info(f"[{_AGENT_DISPLAY}] 下載成功: {archive_path} ({len(data):,} bytes)")
        return data

    except Exception as e:
        logger.error(f"[{_AGENT_DISPLAY}] 下載失敗 {archive_path}: {e}")
        return None


def list_archives(prefix: str = "") -> list[str]:
    """
    列出 HuggingFace Dataset Repo 中的封存檔案清單。

    Args:
        prefix: 路徑前綴篩選，例如 "2024/"

    Returns:
        list of archive paths
    """
    if not HF_TOKEN or not HF_DATASET_REPO:
        return []

    try:
        from huggingface_hub import HfApi

        api   = HfApi(token=HF_TOKEN)
        files = api.list_repo_files(
            repo_id=HF_DATASET_REPO,
            repo_type="dataset",
        )
        return [f for f in files if f.startswith(prefix) and f.endswith(".parquet")]

    except Exception as e:
        logger.error(f"[{_AGENT_DISPLAY}] 列出封存失敗: {e}")
        return []
