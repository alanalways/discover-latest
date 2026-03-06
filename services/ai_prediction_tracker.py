"""
AI Prediction Tracker Service
\u8ffd\u8e64 AI \u5206\u6790\u9810\u6e2c\u7d00\u9304\u4e26\u8a08\u7b97\u6e96\u78ba\u5ea6\uff0c\u63d0\u4f9b\u6bcf\u65e5/\u6bcf\u9031/\u6bcf\u6708/\u6bcf\u5b63\u5831\u544a\u3002
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import httpx
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

_TZ_NAME = str(os.environ.get("AI_USAGE_TIMEZONE", "Asia/Taipei") or "Asia/Taipei").strip()

try:
    _TZ = ZoneInfo(_TZ_NAME)
except Exception:
    _TZ = timezone.utc


def _now() -> datetime:
    return datetime.now(_TZ)


class AIPredictionTracker:
    """Track AI predictions and compute accuracy metrics."""

    def __init__(self):
        self._url: Optional[str] = None
        self._service_key: Optional[str] = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_config(self):
        if not self._url:
            self._url = os.environ.get("SUPABASE_URL")
            self._service_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        return self._url, self._service_key

    def _headers(self) -> Dict[str, str]:
        url, key = self._get_config()
        return {
            "apikey": key or "",
            "Authorization": f"Bearer {key}" if key else "",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }

    def _rest_url(self, table: str) -> str:
        url, _ = self._get_config()
        return f"{url}/rest/v1/{table}" if url else ""

    def _request(
        self,
        method: str,
        table: str,
        params: Optional[Dict[str, str]] = None,
        json_body: Any = None,
        silent: bool = False,
    ) -> Optional[Any]:
        """Generic REST request to Supabase PostgREST."""
        try:
            rest = self._rest_url(table)
            if not rest:
                logger.warning("[PredictionTracker] Supabase URL not configured")
                return None
            with httpx.Client(timeout=30.0) as client:
                resp = client.request(
                    method=method,
                    url=rest,
                    headers=self._headers(),
                    params=params or {},
                    json=json_body,
                )
                resp.raise_for_status()
                return resp.json() if resp.text else None
        except httpx.HTTPStatusError as exc:
            if not silent:
                status = exc.response.status_code if exc.response is not None else "?"
                body = ""
                try:
                    body = (exc.response.text or "")[:300] if exc.response is not None else ""
                except Exception:
                    pass
                logger.warning(
                    "[PredictionTracker] %s %s failed: HTTP %s %s",
                    method, table, status, body,
                )
            return None
        except Exception as exc:
            if not silent:
                logger.warning(
                    "[PredictionTracker] %s %s error: %s: %s",
                    method, table, type(exc).__name__, exc,
                )
            return None

    # ------------------------------------------------------------------
    # 1) Record prediction
    # ------------------------------------------------------------------

    def record_prediction(
        self,
        symbol: str,
        direction: str,
        confidence: int,
        entry_price: float,
        target_price: float,
        stop_price: float,
        horizon_days: int,
        tier: str,
    ) -> dict:
        """
        \u8a18\u9304\u4e00\u7b46 AI \u9810\u6e2c\u5230 ai_predictions \u8868\u3002
        Returns the inserted row dict on success, or an error dict.
        """
        # Map Chinese verdicts to English
        _direction_map = {
            "\u504f\u591a": "bullish", "\u770b\u591a": "bullish", "bullish": "bullish",
            "\u504f\u7a7a": "bearish", "\u770b\u7a7a": "bearish", "bearish": "bearish",
            "\u4e2d\u6027": "neutral", "\u89c0\u671b": "neutral", "neutral": "neutral",
        }
        direction = _direction_map.get(direction.strip(), direction.strip().lower())
        if direction not in ("bullish", "bearish", "neutral"):
            return {"ok": False, "error": "direction must be bullish/bearish/neutral"}
        if not (0 <= confidence <= 100):
            return {"ok": False, "error": "confidence must be 0-100"}

        prediction_id = str(uuid.uuid4())
        now_iso = _now().isoformat()

        row = {
            "id": prediction_id,
            "symbol": symbol.upper().strip(),
            "predicted_at": now_iso,
            "direction": direction,
            "confidence": confidence,
            "entry_price": float(entry_price),
            "target_price": float(target_price),
            "stop_price": float(stop_price),
            "horizon_days": int(horizon_days),
            "tier": tier,
            "status": "open",
            "actual_return_pct": None,
            "evaluated_at": None,
            "evaluation_notes": None,
        }

        result = self._request("POST", "ai_predictions", json_body=row)
        if result:
            inserted = result[0] if isinstance(result, list) and result else result
            return {"ok": True, "prediction": inserted}
        return {"ok": False, "error": "Failed to insert prediction"}

    # ------------------------------------------------------------------
    # 2) Evaluate open predictions
    # ------------------------------------------------------------------

    async def evaluate_open_predictions(self) -> dict:
        """
        \u6aa2\u67e5\u6240\u6709 status='open' \u7684\u9810\u6e2c\uff0c\u5c0d\u7167\u7576\u524d\u50f9\u683c\u5224\u65b7\u662f\u5426\u547d\u4e2d target/stop \u6216\u904e\u671f\u3002
        Uses yfinance for current prices.
        """
        open_rows = self._request(
            "GET",
            "ai_predictions",
            params={
                "status": "eq.open",
                "select": "*",
                "order": "predicted_at.asc",
            },
        )
        if not open_rows:
            return {"ok": True, "evaluated": 0, "message": "No open predictions"}

        if not isinstance(open_rows, list):
            open_rows = [open_rows]

        # Group by symbol to batch price lookups
        symbols: set[str] = {row["symbol"] for row in open_rows if row.get("symbol")}
        current_prices = self._fetch_current_prices(list(symbols))

        now = _now()
        evaluated_count = 0
        results: List[Dict[str, Any]] = []

        for row in open_rows:
            symbol = row.get("symbol", "")
            price = current_prices.get(symbol)
            if price is None:
                results.append({
                    "id": row["id"],
                    "symbol": symbol,
                    "status": "skipped",
                    "reason": "price_unavailable",
                })
                continue

            entry = float(row.get("entry_price") or 0)
            target = float(row.get("target_price") or 0)
            stop = float(row.get("stop_price") or 0)
            direction = row.get("direction", "bullish")
            horizon = int(row.get("horizon_days") or 30)
            predicted_at_str = row.get("predicted_at", "")

            # Parse predicted_at
            try:
                predicted_at = datetime.fromisoformat(predicted_at_str)
                if predicted_at.tzinfo is None:
                    predicted_at = predicted_at.replace(tzinfo=_TZ)
            except Exception:
                predicted_at = now - timedelta(days=horizon + 1)

            expired = (now - predicted_at).days >= horizon

            # Determine outcome
            new_status = "open"
            return_pct = 0.0
            notes = ""

            if entry > 0:
                if direction == "bullish":
                    return_pct = round(((price - entry) / entry) * 100, 2)
                    if target > 0 and price >= target:
                        new_status = "hit_target"
                        notes = f"Target {target} hit at {price}"
                    elif stop > 0 and price <= stop:
                        new_status = "hit_stop"
                        notes = f"Stop {stop} hit at {price}"
                    elif expired:
                        new_status = "expired"
                        notes = f"Expired after {horizon}d, price={price}"
                elif direction == "bearish":
                    return_pct = round(((entry - price) / entry) * 100, 2)
                    if target > 0 and price <= target:
                        new_status = "hit_target"
                        notes = f"Target {target} hit at {price}"
                    elif stop > 0 and price >= stop:
                        new_status = "hit_stop"
                        notes = f"Stop {stop} hit at {price}"
                    elif expired:
                        new_status = "expired"
                        notes = f"Expired after {horizon}d, price={price}"
                else:
                    # neutral
                    return_pct = round(((price - entry) / entry) * 100, 2)
                    if expired:
                        new_status = "expired"
                        notes = f"Neutral expired after {horizon}d, price={price}"
            else:
                if expired:
                    new_status = "expired"
                    notes = "No entry price, expired"

            if new_status == "open":
                results.append({
                    "id": row["id"],
                    "symbol": symbol,
                    "status": "still_open",
                    "current_price": price,
                    "return_pct": return_pct,
                })
                continue

            # Update the row
            update_data = {
                "status": new_status,
                "actual_return_pct": return_pct,
                "evaluated_at": now.isoformat(),
                "evaluation_notes": notes,
            }
            self._request(
                "PATCH",
                "ai_predictions",
                params={"id": f"eq.{row['id']}"},
                json_body=update_data,
            )
            evaluated_count += 1
            results.append({
                "id": row["id"],
                "symbol": symbol,
                "status": new_status,
                "return_pct": return_pct,
                "notes": notes,
            })

        return {
            "ok": True,
            "evaluated": evaluated_count,
            "total_open": len(open_rows),
            "details": results,
        }

    def _fetch_current_prices(self, symbols: List[str]) -> Dict[str, Optional[float]]:
        """Fetch current prices for a list of symbols via yfinance."""
        prices: Dict[str, Optional[float]] = {}
        if not symbols:
            return prices
        try:
            import yfinance as yf

            for sym in symbols:
                try:
                    ticker = yf.Ticker(sym)
                    info = ticker.fast_info
                    last_price = getattr(info, "last_price", None)
                    if last_price is None:
                        hist = ticker.history(period="1d")
                        if not hist.empty:
                            last_price = float(hist["Close"].iloc[-1])
                    prices[sym] = float(last_price) if last_price else None
                except Exception as exc:
                    logger.debug("[PredictionTracker] Price fetch failed for %s: %s", sym, exc)
                    prices[sym] = None
        except ImportError:
            logger.warning("[PredictionTracker] yfinance not installed, cannot fetch prices")
        return prices

    # ------------------------------------------------------------------
    # 3) Weekly stats
    # ------------------------------------------------------------------

    def get_weekly_stats(self, weeks_back: int = 1) -> dict:
        """
        \u904e\u53bb N \u9031\u7684\u52dd\u7387\u3001\u7e3d\u6578\u3001\u5e73\u5747\u5831\u916c\u7387\u3002
        """
        now = _now()
        start = (now - timedelta(weeks=weeks_back)).isoformat()

        rows = self._request(
            "GET",
            "ai_predictions",
            params={
                "status": "neq.open",
                "evaluated_at": f"gte.{start}",
                "select": "id,symbol,direction,confidence,status,actual_return_pct,evaluated_at",
                "order": "evaluated_at.desc",
            },
        )
        if not rows or not isinstance(rows, list):
            return {
                "ok": True,
                "period": f"last_{weeks_back}_weeks",
                "total": 0,
                "win_rate": 0.0,
                "avg_return_pct": 0.0,
                "predictions": [],
            }

        total = len(rows)
        wins = sum(1 for r in rows if r.get("status") == "hit_target")
        returns = [
            float(r["actual_return_pct"])
            for r in rows
            if r.get("actual_return_pct") is not None
        ]
        avg_return = round(sum(returns) / len(returns), 2) if returns else 0.0
        win_rate = round((wins / total) * 100, 2) if total > 0 else 0.0

        return {
            "ok": True,
            "period": f"last_{weeks_back}_weeks",
            "start": start,
            "total": total,
            "wins": wins,
            "losses": total - wins,
            "win_rate": win_rate,
            "avg_return_pct": avg_return,
            "predictions": rows,
        }

    # ------------------------------------------------------------------
    # 4) Monthly review
    # ------------------------------------------------------------------

    def get_monthly_review(self, year: int, month: int) -> dict:
        """
        \u7279\u5b9a\u6708\u4efd\u8a73\u7d30\u5206\u6790\uff1a\u52dd\u7387\u3001\u5e73\u5747\u5831\u916c\u3001\u6700\u4f73/\u6700\u5dee\u9810\u6e2c\u3001\u65b9\u5411\u5206\u5e03\u3002
        """
        month_start = datetime(year, month, 1, tzinfo=_TZ)
        if month == 12:
            month_end = datetime(year + 1, 1, 1, tzinfo=_TZ)
        else:
            month_end = datetime(year, month + 1, 1, tzinfo=_TZ)

        rows = self._request(
            "GET",
            "ai_predictions",
            params={
                "predicted_at": f"gte.{month_start.isoformat()}",
                "and": f"(predicted_at.lt.{month_end.isoformat()})",
                "select": "*",
                "order": "predicted_at.asc",
            },
        )
        if not rows or not isinstance(rows, list):
            rows = []

        evaluated = [r for r in rows if r.get("status") != "open"]
        still_open = [r for r in rows if r.get("status") == "open"]

        wins = [r for r in evaluated if r.get("status") == "hit_target"]
        stops = [r for r in evaluated if r.get("status") == "hit_stop"]
        expired = [r for r in evaluated if r.get("status") == "expired"]

        returns = [
            float(r["actual_return_pct"])
            for r in evaluated
            if r.get("actual_return_pct") is not None
        ]
        avg_return = round(sum(returns) / len(returns), 2) if returns else 0.0
        best = max(returns) if returns else 0.0
        worst = min(returns) if returns else 0.0

        win_rate = (
            round((len(wins) / len(evaluated)) * 100, 2) if evaluated else 0.0
        )

        # Direction breakdown
        direction_stats: Dict[str, Dict[str, Any]] = {}
        for d in ("bullish", "bearish", "neutral"):
            d_rows = [r for r in evaluated if r.get("direction") == d]
            d_wins = [r for r in d_rows if r.get("status") == "hit_target"]
            d_returns = [
                float(r["actual_return_pct"])
                for r in d_rows
                if r.get("actual_return_pct") is not None
            ]
            direction_stats[d] = {
                "total": len(d_rows),
                "wins": len(d_wins),
                "win_rate": round((len(d_wins) / len(d_rows)) * 100, 2) if d_rows else 0.0,
                "avg_return_pct": round(sum(d_returns) / len(d_returns), 2) if d_returns else 0.0,
            }

        # Tier breakdown
        tier_stats: Dict[str, Dict[str, Any]] = {}
        for t in ("free", "pro", "premium"):
            t_rows = [r for r in evaluated if r.get("tier") == t]
            t_wins = [r for r in t_rows if r.get("status") == "hit_target"]
            tier_stats[t] = {
                "total": len(t_rows),
                "wins": len(t_wins),
                "win_rate": round((len(t_wins) / len(t_rows)) * 100, 2) if t_rows else 0.0,
            }

        return {
            "ok": True,
            "year": year,
            "month": month,
            "total_predictions": len(rows),
            "evaluated": len(evaluated),
            "still_open": len(still_open),
            "wins": len(wins),
            "stops": len(stops),
            "expired": len(expired),
            "win_rate": win_rate,
            "avg_return_pct": avg_return,
            "best_return_pct": best,
            "worst_return_pct": worst,
            "direction_stats": direction_stats,
            "tier_stats": tier_stats,
        }

    # ------------------------------------------------------------------
    # 5) Quarterly audit
    # ------------------------------------------------------------------

    def get_quarterly_audit(self, year: int, quarter: int) -> dict:
        """
        \u6bcf\u5b63\u5b8c\u6574\u5be9\u8a08\uff1a\u7d9c\u5408\u5206\u6790 + \u5efa\u8b70\u3002
        """
        if quarter < 1 or quarter > 4:
            return {"ok": False, "error": "quarter must be 1-4"}

        start_month = (quarter - 1) * 3 + 1
        end_month = start_month + 3

        q_start = datetime(year, start_month, 1, tzinfo=_TZ)
        if end_month <= 12:
            q_end = datetime(year, end_month, 1, tzinfo=_TZ)
        else:
            q_end = datetime(year + 1, 1, 1, tzinfo=_TZ)

        rows = self._request(
            "GET",
            "ai_predictions",
            params={
                "predicted_at": f"gte.{q_start.isoformat()}",
                "and": f"(predicted_at.lt.{q_end.isoformat()})",
                "select": "*",
                "order": "predicted_at.asc",
            },
        )
        if not rows or not isinstance(rows, list):
            rows = []

        evaluated = [r for r in rows if r.get("status") != "open"]
        still_open = [r for r in rows if r.get("status") == "open"]

        wins = [r for r in evaluated if r.get("status") == "hit_target"]
        stops = [r for r in evaluated if r.get("status") == "hit_stop"]
        expired_rows = [r for r in evaluated if r.get("status") == "expired"]

        returns = [
            float(r["actual_return_pct"])
            for r in evaluated
            if r.get("actual_return_pct") is not None
        ]
        avg_return = round(sum(returns) / len(returns), 2) if returns else 0.0
        best = max(returns) if returns else 0.0
        worst = min(returns) if returns else 0.0
        win_rate = round((len(wins) / len(evaluated)) * 100, 2) if evaluated else 0.0

        # Monthly breakdown within the quarter
        monthly_breakdown: List[Dict[str, Any]] = []
        for m_offset in range(3):
            m = start_month + m_offset
            m_rows = [
                r for r in evaluated
                if _parse_month(r.get("predicted_at", "")) == m
            ]
            m_wins = [r for r in m_rows if r.get("status") == "hit_target"]
            m_returns = [
                float(r["actual_return_pct"])
                for r in m_rows
                if r.get("actual_return_pct") is not None
            ]
            monthly_breakdown.append({
                "month": m,
                "total": len(m_rows),
                "wins": len(m_wins),
                "win_rate": round((len(m_wins) / len(m_rows)) * 100, 2) if m_rows else 0.0,
                "avg_return_pct": round(sum(m_returns) / len(m_returns), 2) if m_returns else 0.0,
            })

        # Top symbols
        symbol_stats: Dict[str, Dict[str, Any]] = {}
        for r in evaluated:
            sym = r.get("symbol", "UNKNOWN")
            if sym not in symbol_stats:
                symbol_stats[sym] = {"total": 0, "wins": 0, "returns": []}
            symbol_stats[sym]["total"] += 1
            if r.get("status") == "hit_target":
                symbol_stats[sym]["wins"] += 1
            ret = r.get("actual_return_pct")
            if ret is not None:
                symbol_stats[sym]["returns"].append(float(ret))

        top_symbols = []
        for sym, st in sorted(symbol_stats.items(), key=lambda x: x[1]["total"], reverse=True)[:10]:
            top_symbols.append({
                "symbol": sym,
                "total": st["total"],
                "wins": st["wins"],
                "win_rate": round((st["wins"] / st["total"]) * 100, 2) if st["total"] else 0.0,
                "avg_return_pct": round(sum(st["returns"]) / len(st["returns"]), 2) if st["returns"] else 0.0,
            })

        # Confidence calibration: group by confidence buckets
        confidence_buckets: Dict[str, Dict[str, Any]] = {}
        for bucket_label, lo, hi in [
            ("0-20", 0, 20), ("21-40", 21, 40), ("41-60", 41, 60),
            ("61-80", 61, 80), ("81-100", 81, 100),
        ]:
            b_rows = [
                r for r in evaluated
                if lo <= int(r.get("confidence") or 0) <= hi
            ]
            b_wins = [r for r in b_rows if r.get("status") == "hit_target"]
            confidence_buckets[bucket_label] = {
                "total": len(b_rows),
                "wins": len(b_wins),
                "win_rate": round((len(b_wins) / len(b_rows)) * 100, 2) if b_rows else 0.0,
            }

        # Generate recommendations
        recommendations: List[str] = []
        if win_rate < 40:
            recommendations.append(
                "Win rate below 40%: consider recalibrating AI analysis prompts."
            )
        if win_rate >= 60:
            recommendations.append(
                "Win rate above 60%: model performance is strong this quarter."
            )
        if len(expired_rows) > len(evaluated) * 0.5 and evaluated:
            recommendations.append(
                "Over 50% of predictions expired without hitting target or stop. "
                "Consider tightening horizon or adjusting price targets."
            )
        high_conf = confidence_buckets.get("81-100", {})
        if high_conf.get("total", 0) > 0 and high_conf.get("win_rate", 0) < 50:
            recommendations.append(
                "High-confidence (81-100) predictions have low win rate. "
                "AI may be overconfident; review confidence calibration."
            )
        if not recommendations:
            recommendations.append("No specific issues detected this quarter.")

        return {
            "ok": True,
            "year": year,
            "quarter": quarter,
            "period": f"Q{quarter} {year}",
            "total_predictions": len(rows),
            "evaluated": len(evaluated),
            "still_open": len(still_open),
            "wins": len(wins),
            "stops": len(stops),
            "expired": len(expired_rows),
            "win_rate": win_rate,
            "avg_return_pct": avg_return,
            "best_return_pct": best,
            "worst_return_pct": worst,
            "monthly_breakdown": monthly_breakdown,
            "top_symbols": top_symbols,
            "confidence_calibration": confidence_buckets,
            "recommendations": recommendations,
        }

    # ------------------------------------------------------------------
    # 6) Accuracy dashboard (overall)
    # ------------------------------------------------------------------

    def get_accuracy_dashboard(self) -> dict:
        """
        \u7576\u524d\u7e3d\u9ad4\u7d71\u8a08\u6578\u64da\uff0c\u4f9b Admin \u7528\u3002
        """
        # All evaluated predictions
        all_rows = self._request(
            "GET",
            "ai_predictions",
            params={
                "select": "id,symbol,direction,confidence,status,actual_return_pct,tier,predicted_at,evaluated_at",
                "order": "predicted_at.desc",
                "limit": "5000",
            },
        )
        if not all_rows or not isinstance(all_rows, list):
            all_rows = []

        total = len(all_rows)
        open_count = sum(1 for r in all_rows if r.get("status") == "open")
        evaluated = [r for r in all_rows if r.get("status") != "open"]
        eval_count = len(evaluated)

        wins = sum(1 for r in evaluated if r.get("status") == "hit_target")
        stops = sum(1 for r in evaluated if r.get("status") == "hit_stop")
        expired_count = sum(1 for r in evaluated if r.get("status") == "expired")

        returns = [
            float(r["actual_return_pct"])
            for r in evaluated
            if r.get("actual_return_pct") is not None
        ]
        avg_return = round(sum(returns) / len(returns), 2) if returns else 0.0
        best = max(returns) if returns else 0.0
        worst = min(returns) if returns else 0.0
        win_rate = round((wins / eval_count) * 100, 2) if eval_count > 0 else 0.0

        # Recent 7 days stats
        now = _now()
        week_ago = (now - timedelta(days=7)).isoformat()
        recent = [
            r for r in evaluated
            if (r.get("evaluated_at") or "") >= week_ago
        ]
        recent_wins = sum(1 for r in recent if r.get("status") == "hit_target")
        recent_win_rate = (
            round((recent_wins / len(recent)) * 100, 2) if recent else 0.0
        )

        return {
            "ok": True,
            "total_predictions": total,
            "open": open_count,
            "evaluated": eval_count,
            "wins": wins,
            "stops": stops,
            "expired": expired_count,
            "win_rate": win_rate,
            "avg_return_pct": avg_return,
            "best_return_pct": best,
            "worst_return_pct": worst,
            "recent_7d": {
                "evaluated": len(recent),
                "wins": recent_wins,
                "win_rate": recent_win_rate,
            },
        }


def _parse_month(iso_str: str) -> int:
    """Extract month number from an ISO datetime string."""
    try:
        return datetime.fromisoformat(iso_str).month
    except Exception:
        return 0


# Module-level singleton
prediction_tracker = AIPredictionTracker()
