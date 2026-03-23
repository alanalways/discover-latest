"""
backend/agents/infra/report_qa.py
規則式報告品質審查員（Sonnet 撰寫）

職責：
1. 在寫入 DB 前對 Pipeline 輸出做零 API 成本的規則檢查
2. 發現品質不合格時回傳失敗原因，由 CEOAgent 觸發重試
3. 所有規則只用 Python 本地計算，不呼叫任何外部 API

通過條件（全部滿足才算通過）：
A. final_report 長度 > 500 字元
B. final_report 不含明顯的錯誤字串（如 "error", "rate_limited"）
C. 六部門至少 2 部門輸出有意義（非 failed/rate_limited/empty）
D. rating 在合法清單內（非 None/空）
E. confidence_score > 0.3
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)

# ─── 常量 ────────────────────────────────────────────────────

# final_report 最短長度（字元）
_MIN_REPORT_LENGTH = 500

# 報告中出現以下任一字串即視為品質不合格
_ERROR_PHRASES = [
    "rate_limited",
    "rate limited",
    '"status": "failed"',
    '"status":"failed"',
    "Internal Server Error",
    "JSONDecodeError",
    "parse_failed",
    "分析失敗",
    "無法生成",
    "API 錯誤",
]

# 合法的 rating 值（首席分析師應輸出其中之一）
_VALID_RATINGS = {
    "強烈買進", "買進", "審慎買進",
    "中立", "觀望",
    "審慎賣出", "賣出", "強烈賣出",
    "strong_buy", "buy", "cautious_buy",
    "neutral", "hold", "watch",
    "cautious_sell", "sell", "strong_sell",
}

# 部門輸出中代表「無意義」的 status 值
_INVALID_DEPT_STATUSES = {"failed", "rate_limited", "error", "skipped"}

# 至少需要幾個部門成功
_MIN_VALID_DEPTS = 2

# confidence_score 最低門檻
_MIN_CONFIDENCE = 0.3


# ─── 主函式 ──────────────────────────────────────────────────

def check_report(
    chief_result: dict[str, Any],
    dept_outputs: dict[str, dict[str, Any]],
) -> tuple[bool, list[str]]:
    """
    對 Pipeline 輸出執行規則式品質審查。

    Args:
        chief_result:  首席分析師的輸出 dict
        dept_outputs:  六部門分析結果 dict（key = 部門名稱）

    Returns:
        (passed, reasons)
        - passed:  True = 全部通過，False = 至少一項不合格
        - reasons: 不合格原因列表（通過時為空 list）
    """
    reasons: list[str] = []

    # ── A. 報告長度 ───────────────────────────────────────────
    final_report = chief_result.get("final_report") or ""
    if len(final_report) < _MIN_REPORT_LENGTH:
        reasons.append(
            f"final_report 過短（{len(final_report)} 字元，需 > {_MIN_REPORT_LENGTH}）"
        )

    # ── B. 報告不含錯誤字串 ───────────────────────────────────
    final_report_lower = final_report.lower()
    for phrase in _ERROR_PHRASES:
        if phrase.lower() in final_report_lower:
            reasons.append(f"final_report 含錯誤字串：'{phrase}'")
            break  # 只回報第一個，避免重複

    # ── C. 至少 2 部門有效 ────────────────────────────────────
    valid_dept_count = 0
    for dept_name, dept_data in dept_outputs.items():
        if not isinstance(dept_data, dict):
            continue
        status = dept_data.get("status", "")
        if status in _INVALID_DEPT_STATUSES:
            continue
        # 有任意有效欄位（非 status/error 的 key）就算有意義
        meaningful_keys = {
            k for k in dept_data
            if k not in ("status", "error", "output", "model_used",
                         "duration_ms", "parse_failed")
               and dept_data[k] is not None
        }
        if meaningful_keys or dept_data.get("raw") or dept_data.get("summary"):
            valid_dept_count += 1

    if valid_dept_count < _MIN_VALID_DEPTS:
        reasons.append(
            f"有效部門過少（{valid_dept_count}/6，需 >= {_MIN_VALID_DEPTS}）"
        )

    # ── D. rating 合法 ────────────────────────────────────────
    rating = chief_result.get("rating")
    if not rating or str(rating).strip() not in _VALID_RATINGS:
        reasons.append(
            f"rating 不合法（收到：{rating!r}）"
        )

    # ── E. confidence_score 門檻 ──────────────────────────────
    confidence = chief_result.get("confidence_score")
    try:
        if confidence is None or float(confidence) < _MIN_CONFIDENCE:
            reasons.append(
                f"confidence_score 過低（{confidence}，需 > {_MIN_CONFIDENCE}）"
            )
    except (TypeError, ValueError):
        reasons.append(f"confidence_score 無法解析（{confidence!r}）")

    passed = len(reasons) == 0

    if passed:
        logger.debug("[ReportQA] 通過品質審查")
    else:
        logger.warning(f"[ReportQA] 品質審查不合格：{reasons}")

    return passed, reasons
