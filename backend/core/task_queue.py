"""
backend/core/task_queue.py
工作佇列管理器（Opus 邏輯設計）

職責：
1. 將工作寫入 Supabase job_queue 表
2. 取得下一個待執行工作（依 priority + scheduled_for）
3. 更新工作狀態（started / completed / failed）
4. 重試機制（指數退避，最多 max_retries 次）
5. 內存快取：Supabase 不可用時暫存，30s 後重試

設計決策：
- priority 數字越小優先級越高（1=最高，10=最低，預設5）
- status 狀態機：pending → running → completed | failed
- 並發安全：用 UPDATE ... WHERE status='pending' 原子操作認領
- Supabase 失敗時記憶體佇列暫代（最多 500 筆）
"""

import logging
import threading
import time
import uuid
from collections import deque
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ─── 常量 ────────────────────────────────────────────────────────
_STATUS_PENDING   = "pending"
_STATUS_RUNNING   = "running"
_STATUS_COMPLETED = "completed"
_STATUS_FAILED    = "failed"

_MAX_IN_MEMORY    = 500        # 記憶體佇列上限
_SUPABASE_RETRY   = 30.0       # Supabase 不可用時重試間隔（秒）


# ─── TaskQueue ───────────────────────────────────────────────────

class TaskQueue:
    """
    工作佇列管理器。

    主要方法：
    - enqueue(job_type, payload, priority, scheduled_for)
    - dequeue(agent_name) -> job dict | None
    - complete(job_id, result)
    - fail(job_id, error, retry)
    - get_pending_count() -> int
    """

    def __init__(self):
        self._lock = threading.Lock()
        # 記憶體降級佇列：deque of job dicts，按 priority 排序
        self._mem_queue: deque[dict] = deque()
        self._last_db_fail: float = 0.0

    # ─── 公開介面 ────────────────────────────────────────────

    def enqueue(
        self,
        job_type: str,
        payload: dict,
        priority: int = 5,
        scheduled_for: Optional[datetime] = None,
        max_retries: int = 3,
    ) -> Optional[str]:
        """
        新增一個工作到佇列。

        Args:
            job_type:      工作類型（如 "analyze_stock", "scan_watchlist"）
            payload:       工作參數 dict
            priority:      優先級 1~10（1最高）
            scheduled_for: 最早執行時間（None=立即）
            max_retries:   最多重試次數

        Returns:
            job_id (UUID str) 或 None（完全失敗時）
        """
        job_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        job = {
            "id": job_id,
            "job_type": job_type,
            "priority": max(1, min(10, priority)),
            "status": _STATUS_PENDING,
            "payload": payload,
            "result": None,
            "error_message": None,
            "assigned_agent": None,
            "started_at": None,
            "completed_at": None,
            "retry_count": 0,
            "max_retries": max_retries,
            "scheduled_for": (scheduled_for or now).isoformat(),
            "created_at": now.isoformat(),
        }

        # 嘗試寫入 Supabase
        if self._db_available():
            db_job = self._db_insert(job)
            if db_job:
                logger.debug(f"[TaskQueue] 工作入隊（DB）: {job_type} [{job_id[:8]}]")
                return job_id

        # 降級：寫入記憶體佇列
        self._mem_enqueue(job)
        logger.warning(
            f"[TaskQueue] Supabase 不可用，工作暫存記憶體: "
            f"{job_type} [{job_id[:8]}]"
        )
        return job_id

    def dequeue(self, agent_name: str) -> Optional[dict]:
        """
        取得一個可執行的工作並標記為 running。

        使用原子性 UPDATE 確保同一工作不被重複認領。

        Args:
            agent_name: 認領工作的 agent 名稱

        Returns:
            job dict 或 None（無可執行工作）
        """
        # 嘗試從 DB 取工作
        if self._db_available():
            job = self._db_dequeue(agent_name)
            if job:
                return job

        # 降級：從記憶體佇列取
        return self._mem_dequeue(agent_name)

    def complete(self, job_id: str, result: Any = None) -> bool:
        """將工作標記為 completed，寫入執行結果。"""
        update = {
            "status": _STATUS_COMPLETED,
            "result": result,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }
        return self._update_job(job_id, update)

    def fail(
        self,
        job_id: str,
        error: str,
        retry: bool = True,
    ) -> bool:
        """
        將工作標記為失敗。

        若 retry=True 且 retry_count < max_retries：
        - 重設為 pending，retry_count+1，指數退避 scheduled_for
        否則：
        - 永久標記為 failed
        """
        # 先取得目前 retry 狀態
        job = self._get_job(job_id)
        if not job:
            logger.warning(f"[TaskQueue] fail: 找不到 job {job_id[:8]}")
            return False

        retry_count = job.get("retry_count", 0)
        max_retries = job.get("max_retries", 3)

        if retry and retry_count < max_retries:
            # 指數退避：2^retry_count 秒（2s, 4s, 8s）
            backoff = 2 ** (retry_count + 1)
            next_try = datetime.now(timezone.utc).timestamp() + backoff
            next_dt  = datetime.fromtimestamp(next_try, tz=timezone.utc)

            update = {
                "status": _STATUS_PENDING,
                "retry_count": retry_count + 1,
                "error_message": f"重試 {retry_count + 1}/{max_retries}: {error}",
                "assigned_agent": None,
                "started_at": None,
                "scheduled_for": next_dt.isoformat(),
            }
            logger.info(
                f"[TaskQueue] job {job_id[:8]} 排入重試 "
                f"#{retry_count + 1}，{backoff}s 後執行"
            )
        else:
            update = {
                "status": _STATUS_FAILED,
                "error_message": error,
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }
            logger.error(
                f"[TaskQueue] job {job_id[:8]} 永久失敗（已重試 {retry_count} 次）: "
                f"{error[:100]}"
            )

        return self._update_job(job_id, update)

    def get_pending_count(self) -> int:
        """取得目前待執行工作數量。"""
        if self._db_available():
            try:
                from backend.data.storage.supabase_client import get_client
                client = get_client()
                if client:
                    result = (
                        client.table("job_queue")
                        .select("id", count="exact")
                        .eq("status", _STATUS_PENDING)
                        .execute()
                    )
                    return result.count or 0
            except Exception as e:
                logger.debug(f"[TaskQueue] get_pending_count DB error: {e}")

        return len(self._mem_queue)

    def peek_pending_jobs(self, max_jobs: int = 8) -> list[dict]:
        """
        查看（不認領）即將執行的待處理工作。

        用於批次 grounding 預熱：讓 run_pending_jobs 在正式執行前
        先知道哪些股票即將被分析，一次 Gemini 呼叫取回所有 grounding。

        Args:
            max_jobs: 最多回傳幾筆

        Returns:
            list of job dict（含 id / job_type / payload）
        """
        if self._db_available():
            try:
                from backend.data.storage.supabase_client import get_client
                client = get_client()
                if client:
                    now_iso = datetime.now(timezone.utc).isoformat()
                    result = (
                        client.table("job_queue")
                        .select("id, job_type, payload")
                        .eq("status", _STATUS_PENDING)
                        .lte("scheduled_for", now_iso)
                        .order("priority", desc=True)
                        .order("scheduled_for")
                        .limit(max_jobs)
                        .execute()
                    )
                    return result.data or []
            except Exception as e:
                logger.debug(f"[TaskQueue] peek_pending_jobs DB error: {e}")

        # 記憶體佇列 fallback
        pending = [
            j for j in self._mem_queue
            if j.get("status") == _STATUS_PENDING
        ]
        return pending[:max_jobs]

    def get_recent_jobs(self, limit: int = 20) -> list[dict]:
        """取得最近的工作記錄（供 cost_monitor 使用）。"""
        if self._db_available():
            try:
                from backend.data.storage.supabase_client import get_client
                client = get_client()
                if client:
                    result = (
                        client.table("job_queue")
                        .select("*")
                        .order("created_at", desc=True)
                        .limit(limit)
                        .execute()
                    )
                    return result.data or []
            except Exception as e:
                logger.debug(f"[TaskQueue] get_recent_jobs DB error: {e}")

        return list(self._mem_queue)[:limit]

    # ─── Supabase 操作 ───────────────────────────────────────

    def _db_available(self) -> bool:
        """判斷 Supabase 目前是否可用（含冷卻保護）。"""
        if time.time() - self._last_db_fail < _SUPABASE_RETRY:
            return False
        try:
            from backend.data.storage.supabase_client import get_client
            return get_client() is not None
        except Exception:
            return False

    def _db_insert(self, job: dict) -> Optional[dict]:
        """插入工作到 DB，失敗回傳 None。"""
        try:
            from backend.data.storage.supabase_client import get_client
            client = get_client()
            if not client:
                return None
            # Supabase 不接受 None values in some fields，清理一下
            clean = {k: v for k, v in job.items() if v is not None}
            result = client.table("job_queue").insert(clean).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            self._last_db_fail = time.time()
            logger.warning(f"[TaskQueue] DB insert 失敗: {e}")
            return None

    def _db_dequeue(self, agent_name: str) -> Optional[dict]:
        """
        從 DB 原子性認領一個工作。
        策略：取 pending 中 scheduled_for <= now 的最高優先工作，
        用 UPDATE 一次設為 running（防止競爭）。
        """
        try:
            from backend.data.storage.supabase_client import get_client
            client = get_client()
            if not client:
                return None

            now_iso = datetime.now(timezone.utc).isoformat()

            # 取優先級最高的 pending 工作
            result = (
                client.table("job_queue")
                .select("*")
                .eq("status", _STATUS_PENDING)
                .lte("scheduled_for", now_iso)
                .order("priority", desc=False)
                .order("scheduled_for", desc=False)
                .limit(1)
                .execute()
            )

            if not result.data:
                return None

            job = result.data[0]
            job_id = job["id"]

            # 原子性設為 running
            update_result = (
                client.table("job_queue")
                .update({
                    "status": _STATUS_RUNNING,
                    "assigned_agent": agent_name,
                    "started_at": now_iso,
                })
                .eq("id", job_id)
                .eq("status", _STATUS_PENDING)   # 確保還是 pending（防競爭）
                .execute()
            )

            if not update_result.data:
                # 已被其他 agent 認領
                return None

            return update_result.data[0]

        except Exception as e:
            self._last_db_fail = time.time()
            logger.warning(f"[TaskQueue] DB dequeue 失敗: {e}")
            return None

    def _get_job(self, job_id: str) -> Optional[dict]:
        """從 DB 取得單一工作。"""
        try:
            from backend.data.storage.supabase_client import get_client
            client = get_client()
            if not client:
                return self._mem_get(job_id)
            result = (
                client.table("job_queue")
                .select("*")
                .eq("id", job_id)
                .limit(1)
                .execute()
            )
            return result.data[0] if result.data else None
        except Exception as e:
            logger.debug(f"[TaskQueue] _get_job DB error: {e}")
            return self._mem_get(job_id)

    def _update_job(self, job_id: str, update: dict) -> bool:
        """更新 DB 中的工作狀態。"""
        try:
            from backend.data.storage.supabase_client import get_client
            client = get_client()
            if not client:
                return self._mem_update(job_id, update)
            result = (
                client.table("job_queue")
                .update(update)
                .eq("id", job_id)
                .execute()
            )
            return bool(result.data)
        except Exception as e:
            self._last_db_fail = time.time()
            logger.warning(f"[TaskQueue] _update_job DB error: {e}")
            return self._mem_update(job_id, update)

    # ─── 記憶體佇列降級操作 ──────────────────────────────────

    def _mem_enqueue(self, job: dict) -> None:
        """加入記憶體佇列（按 priority 插入排序）。"""
        with self._lock:
            if len(self._mem_queue) >= _MAX_IN_MEMORY:
                logger.warning(
                    f"[TaskQueue] 記憶體佇列已滿（{_MAX_IN_MEMORY}），丟棄最舊工作"
                )
                self._mem_queue.popleft()
            # 簡單追加（dequeue 時排序取）
            self._mem_queue.append(job)

    def _mem_dequeue(self, agent_name: str) -> Optional[dict]:
        """從記憶體佇列取最高優先級的 pending 工作。"""
        with self._lock:
            now_ts = time.time()
            best_idx = None
            best_priority = 999

            for idx, job in enumerate(self._mem_queue):
                if job.get("status") != _STATUS_PENDING:
                    continue
                # 檢查 scheduled_for
                sched = job.get("scheduled_for", "")
                if sched:
                    try:
                        sched_ts = datetime.fromisoformat(
                            sched.replace("Z", "+00:00")
                        ).timestamp()
                        if sched_ts > now_ts:
                            continue
                    except ValueError:
                        pass

                p = job.get("priority", 5)
                if p < best_priority:
                    best_priority = p
                    best_idx = idx

            if best_idx is None:
                return None

            job = self._mem_queue[best_idx]
            now_iso = datetime.now(timezone.utc).isoformat()
            job["status"] = _STATUS_RUNNING
            job["assigned_agent"] = agent_name
            job["started_at"] = now_iso
            return dict(job)

    def _mem_get(self, job_id: str) -> Optional[dict]:
        """從記憶體佇列取得單一工作。"""
        for job in self._mem_queue:
            if job.get("id") == job_id:
                return dict(job)
        return None

    def _mem_update(self, job_id: str, update: dict) -> bool:
        """更新記憶體佇列中的工作。"""
        with self._lock:
            for job in self._mem_queue:
                if job.get("id") == job_id:
                    job.update(update)
                    return True
        return False


# ─── 模組級單例 ──────────────────────────────────────────────────

_queue_instance: Optional[TaskQueue] = None
_queue_lock = threading.Lock()


def get_task_queue() -> TaskQueue:
    """取得 TaskQueue 單例。"""
    global _queue_instance
    if _queue_instance is None:
        with _queue_lock:
            if _queue_instance is None:
                _queue_instance = TaskQueue()
    return _queue_instance
