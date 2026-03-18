"""
SLO Monitor — 服務等級目標監控

C20：分析成功率 >95%、P95 延遲 <8s
G06：endpoint/latency/success 紀錄
"""

from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict, deque
from typing import Any, Dict

logger = logging.getLogger(__name__)

# SLO 目標
SLO_TARGETS = {
    "analysis_success_rate": 0.95,  # 分析成功率 >95%
    "analysis_p95_latency_sec": 8.0,  # P95 延遲 <8s
    "api_success_rate": 0.99,  # API 成功率 >99%
    "api_p95_latency_sec": 2.0,  # API P95 延遲 <2s
}

# 滑動窗口大小（保留最近 N 筆）
WINDOW_SIZE = 1000


class SloMonitor:
    """SLO 監控器 — 單例。"""

    def __init__(self):
        self._lock = threading.Lock()
        self._metrics: Dict[str, deque] = defaultdict(lambda: deque(maxlen=WINDOW_SIZE))
        self._start_time = time.time()
        self._total_requests = 0
        self._total_errors = 0

    def record_request(
        self,
        endpoint: str,
        latency_sec: float,
        success: bool,
        status_code: int = 200,
    ) -> None:
        """記錄一次 API 請求。"""
        with self._lock:
            self._total_requests += 1
            if not success:
                self._total_errors += 1
            self._metrics[endpoint].append({
                "ts": time.time(),
                "latency": latency_sec,
                "success": success,
                "status": status_code,
            })

    def record_analysis(
        self,
        symbol: str,
        latency_sec: float,
        success: bool,
        degraded: bool = False,
    ) -> None:
        """記錄一次分析請求（用於分析 SLO）。"""
        with self._lock:
            self._metrics["_analysis"].append({
                "ts": time.time(),
                "symbol": symbol,
                "latency": latency_sec,
                "success": success,
                "degraded": degraded,
            })

    def get_slo_report(self) -> Dict[str, Any]:
        """產生完整 SLO 報告。"""
        with self._lock:
            report: Dict[str, Any] = {
                "uptime_sec": round(time.time() - self._start_time),
                "total_requests": self._total_requests,
                "total_errors": self._total_errors,
                "slo_targets": SLO_TARGETS,
                "slo_status": {},
                "endpoints": {},
            }

            # 分析 SLO
            analysis_entries = list(self._metrics.get("_analysis", []))
            if analysis_entries:
                succ = sum(1 for e in analysis_entries if e["success"])
                rate = succ / len(analysis_entries)
                latencies = sorted(e["latency"] for e in analysis_entries)
                p95_idx = max(0, int(len(latencies) * 0.95) - 1)
                p95 = latencies[p95_idx] if latencies else 0

                report["slo_status"]["analysis_success_rate"] = {
                    "current": round(rate, 4),
                    "target": SLO_TARGETS["analysis_success_rate"],
                    "met": rate >= SLO_TARGETS["analysis_success_rate"],
                    "sample_size": len(analysis_entries),
                }
                report["slo_status"]["analysis_p95_latency_sec"] = {
                    "current": round(p95, 2),
                    "target": SLO_TARGETS["analysis_p95_latency_sec"],
                    "met": p95 <= SLO_TARGETS["analysis_p95_latency_sec"],
                    "sample_size": len(analysis_entries),
                }

            # 各 endpoint SLO
            for endpoint, entries in self._metrics.items():
                if endpoint == "_analysis":
                    continue
                entries_list = list(entries)
                if not entries_list:
                    continue

                succ = sum(1 for e in entries_list if e["success"])
                rate = succ / len(entries_list)
                latencies = sorted(e["latency"] for e in entries_list)
                p95_idx = max(0, int(len(latencies) * 0.95) - 1)
                p50_idx = max(0, int(len(latencies) * 0.50) - 1)

                report["endpoints"][endpoint] = {
                    "count": len(entries_list),
                    "success_rate": round(rate, 4),
                    "p50_latency": round(latencies[p50_idx], 3),
                    "p95_latency": round(latencies[p95_idx], 3),
                    "max_latency": round(max(latencies), 3),
                }

            # 整體 API SLO
            all_api = []
            for ep, entries in self._metrics.items():
                if ep == "_analysis":
                    continue
                all_api.extend(entries)
            if all_api:
                succ = sum(1 for e in all_api if e["success"])
                rate = succ / len(all_api)
                latencies = sorted(e["latency"] for e in all_api)
                p95_idx = max(0, int(len(latencies) * 0.95) - 1)
                report["slo_status"]["api_success_rate"] = {
                    "current": round(rate, 4),
                    "target": SLO_TARGETS["api_success_rate"],
                    "met": rate >= SLO_TARGETS["api_success_rate"],
                    "sample_size": len(all_api),
                }
                report["slo_status"]["api_p95_latency_sec"] = {
                    "current": round(latencies[p95_idx], 3),
                    "target": SLO_TARGETS["api_p95_latency_sec"],
                    "met": latencies[p95_idx] <= SLO_TARGETS["api_p95_latency_sec"],
                    "sample_size": len(all_api),
                }

            # Error budget
            for key in ("analysis_success_rate", "api_success_rate"):
                status = report["slo_status"].get(key)
                if status:
                    target = status["target"]
                    current = status["current"]
                    # Error budget = (current - target) / (1 - target) * 100
                    if target < 1.0:
                        budget = (current - target) / (1 - target) * 100
                    else:
                        budget = 100 if current >= 1.0 else 0
                    status["error_budget_pct"] = round(max(-100, min(100, budget)), 1)
                    status["error_budget_ok"] = budget >= 0

            return report


# 全域單例
slo_monitor = SloMonitor()
