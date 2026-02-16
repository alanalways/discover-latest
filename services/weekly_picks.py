"""Weekly picks generation based on scanner results."""

from __future__ import annotations

import random
import threading
import time
from datetime import datetime
from typing import Any, Dict, List

from services.gemini_service import gemini_service
from services.market_scanner import scan_market

_WEEKLY_CACHE: Dict[str, Any] = {"week_key": "", "rows": [], "ts": 0.0}
_WEEKLY_LOCK = threading.Lock()


def _week_key() -> str:
    dt = datetime.utcnow()
    iso_year, iso_week, _ = dt.isocalendar()
    return f"{iso_year}-W{iso_week:02d}"


def _fallback_summary(symbol: str, score: float) -> str:
    if score >= 75:
        return f"{symbol} 近期動能與趨勢分數強，適合列入觀察名單。"
    if score >= 60:
        return f"{symbol} 結構偏多，但建議搭配風險控管分批布局。"
    return f"{symbol} 基本分數中性，建議等待更明確的趨勢訊號。"


def generate_weekly_picks(limit: int = 5) -> List[Dict[str, Any]]:
    key = _week_key()
    with _WEEKLY_LOCK:
        if _WEEKLY_CACHE["week_key"] == key and _WEEKLY_CACHE["rows"]:
            return list(_WEEKLY_CACHE["rows"][: max(1, int(limit))])

    scanner_rows = scan_market(limit=max(20, limit))
    top = scanner_rows[: max(1, int(limit))]

    output: List[Dict[str, Any]] = []
    for row in top:
        symbol = str(row.get("symbol") or "").strip().upper()
        score = float(row.get("score") or 0.0)
        summary = ""
        try:
            summary = gemini_service.quick_summary(symbol=symbol, max_tokens=120)
        except Exception:
            summary = ""
        if not summary:
            summary = _fallback_summary(symbol, score)

        out = dict(row)
        out["summary"] = summary
        out["fomo_text"] = f"本週已有 {random.randint(80, 220)} 位 Pro 會員查看"
        output.append(out)

    with _WEEKLY_LOCK:
        _WEEKLY_CACHE["week_key"] = key
        _WEEKLY_CACHE["rows"] = list(output)
        _WEEKLY_CACHE["ts"] = time.time()
    return output
