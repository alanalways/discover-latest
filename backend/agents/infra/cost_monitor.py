"""
backend/agents/infra/cost_monitor.py
成本監控官（Sonnet 撰寫）

職責：
1. 查詢 BudgetGuard 取得每日 Gemini API 使用量
2. 從 agent_logs 統計各模型的呼叫次數和平均延遲
3. 從 job_queue 統計工作成功/失敗率
4. 提供 get_report() 回傳完整成本報告（供 admin API 或日誌用）
5. 發出預算警告（當日用量超過 80%）

設計：
- 無副作用：只讀資料，不修改任何狀態
- 所有 Supabase 查詢均有 try/except，DB 不可用時回傳部分資料
- 適合被 cost_monitor.get_report() 呼叫後直接序列化為 JSON
"""
import logging
from datetime import date, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# 預算警告門檻（與 BudgetGuard 一致）
_WARN_PCT = 80.0


class CostMonitor:
    """
    成本監控官。

    get_report() 是主要入口，回傳含以下資訊的 dict：
    - budget:   今日 Gemini API 預算使用狀況
    - models:   各模型呼叫統計（從 agent_logs）
    - jobs:     今日工作佇列成功/失敗統計
    - alerts:   當前預算警告列表
    """

    def get_report(self) -> dict:
        """
        取得完整成本報告。

        Returns:
            {
                "date":    str (YYYY-MM-DD),
                "budget":  {total_used, total_budget, usage_pct, remaining, status, by_model},
                "models":  [{"model": str, "calls": int, "avg_duration_ms": float}],
                "jobs":    {"pending": int, "completed": int, "failed": int, "total_today": int},
                "alerts":  [str],  -- 預算警告訊息列表
            }
        """
        today = date.today().isoformat()

        budget_status = self._get_budget_status()
        model_stats   = self._get_model_stats(today)
        job_stats     = self._get_job_stats(today)
        alerts        = self._build_alerts(budget_status)

        return {
            "date":   today,
            "budget": budget_status,
            "models": model_stats,
            "jobs":   job_stats,
            "alerts": alerts,
        }

    # ─── 預算狀況 ──────────────────────────────────────────

    def _get_budget_status(self) -> dict:
        """從 BudgetGuard 取得今日 API 使用量。"""
        try:
            from backend.core.budget_guard import get_budget_guard
            return get_budget_guard().get_status()
        except Exception as e:
            logger.warning(f"[CostMonitor] BudgetGuard 查詢失敗: {e}")
            return {
                "date":         date.today().isoformat(),
                "total_used":   0,
                "total_budget": 0,
                "usage_pct":    0.0,
                "remaining":    0,
                "status":       "unknown",
                "by_model":     {},
            }

    # ─── 模型呼叫統計 ──────────────────────────────────────

    def _get_model_stats(self, today: str) -> list[dict]:
        """
        從 agent_logs 統計今日各 Gemini 模型的呼叫次數與平均延遲。

        Returns:
            按呼叫次數降序排列的模型統計列表
        """
        try:
            from backend.data.storage.supabase_client import get_client
            client = get_client()
            if not client:
                return []

            today_start = f"{today}T00:00:00+00:00"
            today_end   = f"{today}T23:59:59+00:00"

            result = (
                client.table("agent_logs")
                .select("gemini_model_used,duration_ms,status")
                .eq("action", "gemini_call")
                .gte("created_at", today_start)
                .lte("created_at", today_end)
                .execute()
            )

            rows = result.data or []
            if not rows:
                return []

            # 彙整各模型統計
            stats: dict[str, dict] = {}
            for row in rows:
                model = row.get("gemini_model_used") or "unknown"
                if model not in stats:
                    stats[model] = {"calls": 0, "total_duration_ms": 0, "errors": 0}
                stats[model]["calls"] += 1
                duration = row.get("duration_ms") or 0
                stats[model]["total_duration_ms"] += duration
                if row.get("status") != "success":
                    stats[model]["errors"] += 1

            # 格式化輸出
            output = []
            for model, s in stats.items():
                avg_duration = (
                    round(s["total_duration_ms"] / s["calls"], 1)
                    if s["calls"] > 0 else 0.0
                )
                output.append({
                    "model":           model,
                    "calls":           s["calls"],
                    "errors":          s["errors"],
                    "avg_duration_ms": avg_duration,
                })

            output.sort(key=lambda x: x["calls"], reverse=True)
            return output

        except Exception as e:
            logger.warning(f"[CostMonitor] model_stats 查詢失敗: {e}")
            return []

    # ─── 工作佇列統計 ──────────────────────────────────────

    def _get_job_stats(self, today: str) -> dict:
        """
        統計今日 job_queue 的工作狀態分佈。

        Returns:
            {"pending": int, "completed": int, "failed": int, "total_today": int}
        """
        stats = {"pending": 0, "completed": 0, "failed": 0, "total_today": 0}

        # pending 從 TaskQueue 直接取（包含記憶體降級佇列）
        try:
            from backend.core.task_queue import get_task_queue
            stats["pending"] = get_task_queue().get_pending_count()
        except Exception as e:
            logger.warning(f"[CostMonitor] pending_count 查詢失敗: {e}")

        # completed / failed 從 DB 統計今日資料
        try:
            from backend.data.storage.supabase_client import get_client
            client = get_client()
            if not client:
                return stats

            today_start = f"{today}T00:00:00+00:00"
            today_end   = f"{today}T23:59:59+00:00"

            for status_val in ("completed", "failed"):
                resp = (
                    client.table("job_queue")
                    .select("id", count="exact")
                    .eq("status", status_val)
                    .gte("created_at", today_start)
                    .lte("created_at", today_end)
                    .execute()
                )
                stats[status_val] = resp.count or 0

            stats["total_today"] = (
                stats["pending"] + stats["completed"] + stats["failed"]
            )

        except Exception as e:
            logger.warning(f"[CostMonitor] job_stats DB 查詢失敗: {e}")

        return stats

    # ─── 警告訊息 ──────────────────────────────────────────

    @staticmethod
    def _build_alerts(budget_status: dict) -> list[str]:
        """根據預算狀況生成警告訊息列表。"""
        alerts: list[str] = []

        status = budget_status.get("status", "unknown")
        usage_pct = budget_status.get("usage_pct", 0.0)
        remaining = budget_status.get("remaining", 0)
        total_budget = budget_status.get("total_budget", 0)

        if status == "critical":
            alerts.append(
                f"Gemini API 預算已達 {usage_pct:.1f}%（剩餘 {remaining}/{total_budget}），"
                "新工作已拒絕入隊"
            )
        elif status == "warning":
            alerts.append(
                f"Gemini API 預算使用率 {usage_pct:.1f}%，接近上限（剩餘 {remaining} 次）"
            )

        return alerts


# ─── 模組級單例 ────────────────────────────────────────────────

_monitor_instance: Optional[CostMonitor] = None


def get_cost_monitor() -> CostMonitor:
    """取得 CostMonitor 單例。"""
    global _monitor_instance
    if _monitor_instance is None:
        _monitor_instance = CostMonitor()
    return _monitor_instance
