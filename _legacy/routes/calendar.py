"""Economic calendar API routes."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, List
from zoneinfo import ZoneInfo

from fastapi import APIRouter

router = APIRouter()
logger = logging.getLogger(__name__)

_TW_TZ = ZoneInfo("Asia/Taipei")

# Hard-coded major economic events for 2026
_DEFAULT_EVENTS: List[Dict[str, Any]] = [
    {"date": "2026-01-28", "time_utc": "19:00", "event": "FOMC 利率決議", "type": "FOMC", "importance": "high", "region": "US"},
    {"date": "2026-03-18", "time_utc": "18:00", "event": "FOMC 利率決議", "type": "FOMC", "importance": "high", "region": "US"},
    {"date": "2026-05-06", "time_utc": "18:00", "event": "FOMC 利率決議", "type": "FOMC", "importance": "high", "region": "US"},
    {"date": "2026-06-17", "time_utc": "18:00", "event": "FOMC 利率決議", "type": "FOMC", "importance": "high", "region": "US"},
    {"date": "2026-07-29", "time_utc": "18:00", "event": "FOMC 利率決議", "type": "FOMC", "importance": "high", "region": "US"},
    {"date": "2026-09-16", "time_utc": "18:00", "event": "FOMC 利率決議", "type": "FOMC", "importance": "high", "region": "US"},
    {"date": "2026-11-04", "time_utc": "18:00", "event": "FOMC 利率決議", "type": "FOMC", "importance": "high", "region": "US"},
    {"date": "2026-12-16", "time_utc": "18:00", "event": "FOMC 利率決議", "type": "FOMC", "importance": "high", "region": "US"},
    # CPI
    {"date": "2026-01-14", "time_utc": "13:30", "event": "美國 CPI 公布", "type": "CPI", "importance": "high", "region": "US"},
    {"date": "2026-02-11", "time_utc": "13:30", "event": "美國 CPI 公布", "type": "CPI", "importance": "high", "region": "US"},
    {"date": "2026-03-11", "time_utc": "12:30", "event": "美國 CPI 公布", "type": "CPI", "importance": "high", "region": "US"},
    {"date": "2026-04-14", "time_utc": "12:30", "event": "美國 CPI 公布", "type": "CPI", "importance": "high", "region": "US"},
    {"date": "2026-05-12", "time_utc": "12:30", "event": "美國 CPI 公布", "type": "CPI", "importance": "high", "region": "US"},
    {"date": "2026-06-10", "time_utc": "12:30", "event": "美國 CPI 公布", "type": "CPI", "importance": "high", "region": "US"},
    # NFP
    {"date": "2026-01-09", "time_utc": "13:30", "event": "非農就業數據", "type": "NFP", "importance": "high", "region": "US"},
    {"date": "2026-02-06", "time_utc": "13:30", "event": "非農就業數據", "type": "NFP", "importance": "high", "region": "US"},
    {"date": "2026-03-06", "time_utc": "13:30", "event": "非農就業數據", "type": "NFP", "importance": "high", "region": "US"},
    {"date": "2026-04-03", "time_utc": "12:30", "event": "非農就業數據", "type": "NFP", "importance": "high", "region": "US"},
    # GDP
    {"date": "2026-01-29", "time_utc": "13:30", "event": "美國 Q4 GDP 初估值", "type": "GDP", "importance": "medium", "region": "US"},
    {"date": "2026-04-29", "time_utc": "12:30", "event": "美國 Q1 GDP 初估值", "type": "GDP", "importance": "medium", "region": "US"},
    # Earnings season markers
    {"date": "2026-01-15", "time_utc": "00:00", "event": "美股財報季開始（Q4）", "type": "EARNINGS", "importance": "medium", "region": "US"},
    {"date": "2026-04-15", "time_utc": "00:00", "event": "美股財報季開始（Q1）", "type": "EARNINGS", "importance": "medium", "region": "US"},
    {"date": "2026-07-15", "time_utc": "00:00", "event": "美股財報季開始（Q2）", "type": "EARNINGS", "importance": "medium", "region": "US"},
    {"date": "2026-10-15", "time_utc": "00:00", "event": "美股財報季開始（Q3）", "type": "EARNINGS", "importance": "medium", "region": "US"},
    # TW specific
    {"date": "2026-02-16", "time_utc": "00:00", "event": "台股開紅盤", "type": "TW_MARKET", "importance": "medium", "region": "TW"},
]


def _load_events() -> List[Dict[str, Any]]:
    """Load events from env or use defaults."""
    raw = os.environ.get("EVENT_CALENDAR_JSON", "")
    if raw.strip():
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list) and parsed:
                return parsed
        except Exception:
            logger.warning("[Calendar] Failed to parse EVENT_CALENDAR_JSON")
    return _DEFAULT_EVENTS


@router.get("/calendar/events")
async def get_calendar_events():
    """Return economic calendar events with countdown info."""
    events = _load_events()
    now = datetime.now(_TW_TZ)

    enriched = []
    for ev in events:
        try:
            ev_date = datetime.strptime(ev["date"], "%Y-%m-%d").replace(tzinfo=_TW_TZ)
            delta = ev_date - now
            days_away = delta.days

            enriched.append({
                **ev,
                "days_away": days_away,
                "is_past": days_away < 0,
                "is_today": days_away == 0,
                "is_upcoming": 0 < days_away <= 7,
            })
        except Exception:
            continue

    # Sort by date
    enriched.sort(key=lambda e: e.get("date", ""))

    # Split into past and upcoming
    upcoming = [e for e in enriched if not e["is_past"]]
    past = [e for e in enriched if e["is_past"]][-10:]  # last 10 past events

    return {
        "upcoming": upcoming,
        "past": past,
        "today": now.strftime("%Y-%m-%d"),
    }
