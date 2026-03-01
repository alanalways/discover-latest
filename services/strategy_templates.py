"""
Strategy Templates — 進出場規則 Schema + 驗證

P03：自訂進出場守則
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# 策略模板 JSON Schema
TEMPLATE_SCHEMA = {
    "name": str,         # 模板名稱
    "entry_rules": list,  # 進場條件 [{"indicator", "operator", "value"}]
    "exit_rules": list,   # 出場條件
    "stop_loss_pct": float,  # 停損百分比
    "take_profit_pct": float,  # 停利百分比
    "max_position_pct": float,  # 最大倉位
    "tags": list,         # 標籤
}

VALID_INDICATORS = {
    "RSI", "MACD", "KDJ_K", "KDJ_D", "KDJ_J",
    "EMA20", "EMA50", "EMA200", "BOLL_UPPER", "BOLL_LOWER",
    "VOLUME_RATIO", "PRICE", "CHANGE_PCT",
}

VALID_OPERATORS = {"gt", "lt", "gte", "lte", "eq", "cross_above", "cross_below"}


def validate_template(template: Dict[str, Any]) -> Dict[str, Any]:
    """驗證策略模板格式。"""
    errors: List[str] = []

    name = str(template.get("name") or "").strip()
    if not name or len(name) < 2:
        errors.append("名稱不可為空且至少 2 字")
    if len(name) > 50:
        errors.append("名稱不可超過 50 字")

    entry = template.get("entry_rules", [])
    exit_rules = template.get("exit_rules", [])

    if not isinstance(entry, list) or len(entry) == 0:
        errors.append("至少需要 1 條進場規則")
    if not isinstance(exit_rules, list) or len(exit_rules) == 0:
        errors.append("至少需要 1 條出場規則")

    for i, rule in enumerate(entry if isinstance(entry, list) else []):
        _validate_rule(rule, f"entry_rules[{i}]", errors)

    for i, rule in enumerate(exit_rules if isinstance(exit_rules, list) else []):
        _validate_rule(rule, f"exit_rules[{i}]", errors)

    sl = template.get("stop_loss_pct")
    if sl is not None:
        try:
            sl_val = float(sl)
            if sl_val < 0.5 or sl_val > 50:
                errors.append("停損百分比應在 0.5%~50% 之間")
        except (ValueError, TypeError):
            errors.append("停損百分比格式錯誤")

    tp = template.get("take_profit_pct")
    if tp is not None:
        try:
            tp_val = float(tp)
            if tp_val < 1 or tp_val > 200:
                errors.append("停利百分比應在 1%~200% 之間")
        except (ValueError, TypeError):
            errors.append("停利百分比格式錯誤")

    return {
        "valid": len(errors) == 0,
        "errors": errors,
    }


def evaluate_template(
    template: Dict[str, Any],
    snapshot: Dict[str, Any],
) -> Dict[str, Any]:
    """根據策略模板評估當前數據是否滿足進場/出場。"""
    entry_matched = []
    entry_failed = []
    exit_matched = []
    exit_failed = []

    for rule in template.get("entry_rules", []):
        match = _evaluate_rule(rule, snapshot)
        if match:
            entry_matched.append(rule)
        else:
            entry_failed.append(rule)

    for rule in template.get("exit_rules", []):
        match = _evaluate_rule(rule, snapshot)
        if match:
            exit_matched.append(rule)
        else:
            exit_failed.append(rule)

    entry_pct = len(entry_matched) / max(1, len(entry_matched) + len(entry_failed)) * 100
    exit_pct = len(exit_matched) / max(1, len(exit_matched) + len(exit_failed)) * 100

    signal = "none"
    if entry_pct >= 80:
        signal = "entry"
    elif exit_pct >= 80:
        signal = "exit"

    return {
        "signal": signal,
        "entry_score": round(entry_pct, 1),
        "exit_score": round(exit_pct, 1),
        "entry_matched": len(entry_matched),
        "entry_total": len(entry_matched) + len(entry_failed),
        "exit_matched": len(exit_matched),
        "exit_total": len(exit_matched) + len(exit_failed),
    }


def _validate_rule(rule: Any, path: str, errors: List[str]) -> None:
    if not isinstance(rule, dict):
        errors.append(f"{path}: 規則必須為物件")
        return
    ind = str(rule.get("indicator") or "").upper()
    if ind not in VALID_INDICATORS:
        errors.append(f"{path}: 不支援的指標 '{ind}'（可用: {', '.join(sorted(VALID_INDICATORS))}）")
    op = str(rule.get("operator") or "")
    if op not in VALID_OPERATORS:
        errors.append(f"{path}: 不支援的運算子 '{op}'（可用: {', '.join(sorted(VALID_OPERATORS))}）")
    if "value" not in rule:
        errors.append(f"{path}: 缺少 value")


def _evaluate_rule(rule: Dict, snapshot: Dict) -> bool:
    """評估單一規則。"""
    ind = str(rule.get("indicator") or "").upper()
    op = str(rule.get("operator") or "")
    target = float(rule.get("value", 0))

    current = snapshot.get(ind.lower(), snapshot.get(ind))
    if current is None:
        return False

    try:
        current = float(current)
    except (ValueError, TypeError):
        return False

    if op == "gt":
        return current > target
    elif op == "lt":
        return current < target
    elif op == "gte":
        return current >= target
    elif op == "lte":
        return current <= target
    elif op == "eq":
        return abs(current - target) < 0.001
    elif op == "cross_above":
        # 需要前一期值（snapshot 中以 prev_{indicator} 提供）
        prev_key = f"prev_{ind.lower()}"
        prev = snapshot.get(prev_key, snapshot.get(f"prev_{ind}"))
        if prev is None:
            return False
        try:
            prev = float(prev)
        except (ValueError, TypeError):
            return False
        return prev <= target and current > target
    elif op == "cross_below":
        prev_key = f"prev_{ind.lower()}"
        prev = snapshot.get(prev_key, snapshot.get(f"prev_{ind}"))
        if prev is None:
            return False
        try:
            prev = float(prev)
        except (ValueError, TypeError):
            return False
        return prev >= target and current < target
    return False
