"""
Event Calendar — 除息/財報日查詢

C06：事件窗口內降 confidence
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

# 事件類型
EVENT_TYPES = {
    "ex_dividend": "除息日",
    "earnings": "財報公布",
    "shareholder_meeting": "股東會",
    "right_offering": "除權日",
    "fed_meeting": "Fed 利率會議",
}

# 事件窗口天數（前後各 N 天降 confidence）
EVENT_WINDOW_DAYS = {
    "ex_dividend": 3,
    "earnings": 5,
    "shareholder_meeting": 2,
    "right_offering": 3,
    "fed_meeting": 2,
}

# 事件 confidence 折扣（乘以此係數）
EVENT_CONFIDENCE_DISCOUNT = {
    "ex_dividend": 0.85,
    "earnings": 0.70,
    "shareholder_meeting": 0.90,
    "right_offering": 0.85,
    "fed_meeting": 0.80,
}


def get_upcoming_events(
    symbol: str,
    days_ahead: int = 30,
) -> List[Dict[str, Any]]:
    """查詢未來 N 天內的事件。"""
    events: List[Dict[str, Any]] = []
    today = datetime.now()

    # 從 Supabase 或 FinMind 取得事件
    try:
        from adapters.supabase_adapter import supabase_adapter
        stored = supabase_adapter.get_stock_events(symbol, days_ahead)
        if stored:
            events.extend(stored)
    except Exception:
        pass

    # 從 FinMind 取得除息/除權日
    try:
        from adapters.finmind_adapter import finmind_adapter
        start = today.strftime("%Y-%m-%d")
        end = (today + timedelta(days=days_ahead)).strftime("%Y-%m-%d")
        raw_symbol = symbol.replace(".TW", "").replace(".TWO", "")
        dividends = finmind_adapter.get_tw_dividend_sync(raw_symbol, start, end)
        if isinstance(dividends, list):
            for d in dividends:
                date_str = str(d.get("date") or d.get("ex_dividend_date") or "")
                if date_str:
                    events.append({
                        "type": "ex_dividend",
                        "type_label": EVENT_TYPES["ex_dividend"],
                        "date": date_str,
                        "symbol": symbol,
                        "detail": d,
                    })
    except Exception:
        pass

    return events


def check_event_window(
    symbol: str,
    days_ahead: int = 10,
) -> Dict[str, Any]:
    """檢查事件窗口，回傳 confidence 折扣與警示。"""
    events = get_upcoming_events(symbol, days_ahead)
    today = datetime.now()
    active_events: List[Dict] = []
    min_discount = 1.0

    for ev in events:
        ev_type = ev.get("type", "")
        date_str = str(ev.get("date") or "")
        if not date_str:
            continue

        try:
            ev_date = datetime.strptime(date_str[:10], "%Y-%m-%d")
        except ValueError:
            continue

        window = EVENT_WINDOW_DAYS.get(ev_type, 3)
        delta = (ev_date - today).days

        if -window <= delta <= window:
            discount = EVENT_CONFIDENCE_DISCOUNT.get(ev_type, 0.85)
            min_discount = min(min_discount, discount)
            active_events.append({
                "type": ev_type,
                "type_label": EVENT_TYPES.get(ev_type, ev_type),
                "date": date_str[:10],
                "days_until": delta,
                "confidence_discount": discount,
            })

    return {
        "in_event_window": len(active_events) > 0,
        "active_events": active_events,
        "confidence_multiplier": round(min_discount, 2),
        "warning": f"近期有 {len(active_events)} 個事件，建議降低信心度" if active_events else None,
    }


def adjust_confidence_for_events(
    symbol: str,
    base_confidence: float,
) -> Dict[str, Any]:
    """根據事件窗口調整 confidence。"""
    event_check = check_event_window(symbol)
    adjusted = base_confidence * event_check["confidence_multiplier"]

    return {
        "original_confidence": round(base_confidence, 2),
        "adjusted_confidence": round(adjusted, 2),
        "multiplier": event_check["confidence_multiplier"],
        "events": event_check["active_events"],
        "in_event_window": event_check["in_event_window"],
    }
