"""
AI Prediction Tracker Service

以本地 SQLite 為主儲存 AI 建議與驗證結果，預設不強依賴 Supabase 額外表，
避免超出 free tier 寫入與查詢成本。若使用者之後建立 `ai_predictions` 表，
可透過環境變數啟用低頻鏡像。
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

_TZ_NAME = str(os.environ.get("AI_USAGE_TIMEZONE", "Asia/Taipei") or "Asia/Taipei").strip()
_ENABLE_SUPABASE_MIRROR = str(
    os.environ.get("AI_PREDICTIONS_ENABLE_SUPABASE_MIRROR", "0") or ""
).strip().lower() in {"1", "true", "yes", "on"}

try:
    _TZ = ZoneInfo(_TZ_NAME)
except Exception:
    _TZ = timezone.utc


def _now() -> datetime:
    return datetime.now(_TZ)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return float(default)
        return float(value)
    except Exception:
        return float(default)


def _normalize_direction(direction: str) -> str:
    raw = str(direction or "").strip().lower()
    mapping = {
        "偏多": "bullish",
        "看多": "bullish",
        "bullish": "bullish",
        "long": "bullish",
        "偏空": "bearish",
        "看空": "bearish",
        "bearish": "bearish",
        "short": "bearish",
        "中性": "neutral",
        "觀望": "neutral",
        "neutral": "neutral",
    }
    return mapping.get(raw, raw)


def _parse_month(iso_str: str) -> int:
    try:
        return datetime.fromisoformat(str(iso_str or "")).month
    except Exception:
        return 0


class AIPredictionTracker:
    """Track AI recommendations, evaluate outcomes, and summarize tuning signals."""

    def __init__(self):
        self._url: Optional[str] = None
        self._service_key: Optional[str] = None

    # ------------------------------------------------------------------
    # Storage helpers
    # ------------------------------------------------------------------

    def _get_local_store(self):
        from adapters.local_store import local_store

        return local_store

    def _get_config(self):
        if not self._url:
            self._url = os.environ.get("SUPABASE_URL")
            self._service_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        return self._url, self._service_key

    def _mirror_to_supabase(self, row: Dict[str, Any]) -> None:
        """Best-effort mirror for users who explicitly create ai_predictions table."""
        if not _ENABLE_SUPABASE_MIRROR:
            return
        try:
            from adapters.supabase_adapter import supabase_adapter

            payload = dict(row)
            payload["quality_pass"] = bool(payload.get("quality_pass", True))
            supabase_adapter._request(
                "POST",
                "ai_predictions",
                params={"on_conflict": "id"},
                json=payload,
                use_service_key=True,
                silent=True,
            )
        except Exception:
            # Mirror is optional. Never let it affect primary path.
            pass

    def list_predictions(
        self,
        *,
        status: Optional[str] = None,
        exclude_status: Optional[str] = None,
        predicted_since: Optional[str] = None,
        predicted_before: Optional[str] = None,
        evaluated_since: Optional[str] = None,
        limit: int = 5000,
    ) -> List[Dict[str, Any]]:
        return self._get_local_store().list_ai_predictions(
            status=status,
            exclude_status=exclude_status,
            predicted_since=predicted_since,
            predicted_before=predicted_before,
            evaluated_since=evaluated_since,
            limit=limit,
        )

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
        *,
        user_id: str = "",
        raw_confidence: Optional[int] = None,
        model_name: str = "",
        analysis_type: str = "full",
        source_route: str = "",
        prompt_version: str = "",
        rule_version: str = "",
        system_version: str = "",
        quality_pass: bool = True,
        summary_json: Any = None,
        predicted_at: Optional[str] = None,
    ) -> dict:
        direction = _normalize_direction(direction)
        if direction not in {"bullish", "bearish", "neutral"}:
            return {"ok": False, "error": "direction must be bullish/bearish/neutral"}

        conf = max(0, min(100, int(confidence or 0)))
        raw_conf = max(0, min(100, int(raw_confidence if raw_confidence is not None else conf)))
        record = {
            "id": str(uuid.uuid4()),
            "user_id": str(user_id or "").strip(),
            "symbol": str(symbol or "").strip().upper(),
            "predicted_at": predicted_at or _now().isoformat(),
            "evaluated_at": None,
            "direction": direction,
            "confidence": conf,
            "raw_confidence": raw_conf,
            "entry_price": round(_safe_float(entry_price), 4),
            "target_price": round(_safe_float(target_price), 4),
            "stop_price": round(_safe_float(stop_price), 4),
            "horizon_days": max(1, int(horizon_days or 20)),
            "tier": str(tier or "free").strip().lower(),
            "model_name": str(model_name or "").strip(),
            "analysis_type": str(analysis_type or "full").strip(),
            "source_route": str(source_route or "").strip(),
            "prompt_version": str(prompt_version or "").strip(),
            "rule_version": str(rule_version or "").strip(),
            "system_version": str(system_version or "").strip(),
            "quality_pass": bool(quality_pass),
            "status": "open",
            "actual_return_pct": None,
            "evaluation_notes": "",
            "summary_json": json.dumps(summary_json, ensure_ascii=False) if summary_json is not None else "",
        }

        if not record["symbol"]:
            return {"ok": False, "error": "symbol is required"}

        ok = self._get_local_store().save_ai_prediction(record)
        if not ok:
            return {"ok": False, "error": "Failed to save prediction in local store"}

        self._mirror_to_supabase(record)
        return {"ok": True, "prediction": record}

    # ------------------------------------------------------------------
    # 2) Evaluate open predictions
    # ------------------------------------------------------------------

    async def evaluate_open_predictions(self) -> dict:
        open_rows = self.list_predictions(status="open", limit=2000)
        if not open_rows:
            return {"ok": True, "evaluated": 0, "message": "No open predictions"}

        prices = self._fetch_current_prices(
            sorted({str(row.get("symbol") or "").strip().upper() for row in open_rows if row.get("symbol")})
        )
        now = _now()
        results: List[Dict[str, Any]] = []
        evaluated_count = 0

        for row in open_rows:
            symbol = str(row.get("symbol") or "").strip().upper()
            current_price = prices.get(symbol)
            if current_price is None or current_price <= 0:
                results.append({
                    "id": row.get("id"),
                    "symbol": symbol,
                    "status": "skipped",
                    "reason": "price_unavailable",
                })
                continue

            entry = _safe_float(row.get("entry_price"))
            target = _safe_float(row.get("target_price"))
            stop = _safe_float(row.get("stop_price"))
            direction = _normalize_direction(str(row.get("direction") or "neutral"))
            horizon = max(1, int(row.get("horizon_days") or 20))

            try:
                predicted_at = datetime.fromisoformat(str(row.get("predicted_at") or ""))
                if predicted_at.tzinfo is None:
                    predicted_at = predicted_at.replace(tzinfo=_TZ)
            except Exception:
                predicted_at = now - timedelta(days=horizon + 1)

            expired = (now - predicted_at).days >= horizon
            status = "open"
            return_pct = 0.0
            notes = ""

            if entry > 0:
                if direction == "bullish":
                    return_pct = round(((current_price - entry) / entry) * 100, 2)
                    if target > 0 and current_price >= target:
                        status = "hit_target"
                        notes = f"Target {target:.2f} hit at {current_price:.2f}"
                    elif stop > 0 and current_price <= stop:
                        status = "hit_stop"
                        notes = f"Stop {stop:.2f} hit at {current_price:.2f}"
                    elif expired:
                        status = "expired"
                        notes = f"Expired after {horizon}d at {current_price:.2f}"
                elif direction == "bearish":
                    return_pct = round(((entry - current_price) / entry) * 100, 2)
                    if target > 0 and current_price <= target:
                        status = "hit_target"
                        notes = f"Target {target:.2f} hit at {current_price:.2f}"
                    elif stop > 0 and current_price >= stop:
                        status = "hit_stop"
                        notes = f"Stop {stop:.2f} hit at {current_price:.2f}"
                    elif expired:
                        status = "expired"
                        notes = f"Expired after {horizon}d at {current_price:.2f}"
                else:
                    return_pct = round(((current_price - entry) / entry) * 100, 2)
                    if expired:
                        status = "expired"
                        notes = f"Neutral expired after {horizon}d at {current_price:.2f}"
            elif expired:
                status = "expired"
                notes = "No entry price, expired"

            if status == "open":
                results.append({
                    "id": row.get("id"),
                    "symbol": symbol,
                    "status": "still_open",
                    "current_price": current_price,
                    "return_pct": return_pct,
                })
                continue

            updates = {
                "status": status,
                "actual_return_pct": return_pct,
                "evaluated_at": now.isoformat(),
                "evaluation_notes": notes,
            }
            self._get_local_store().update_ai_prediction(str(row.get("id") or ""), updates)
            self._mirror_to_supabase({**row, **updates})
            evaluated_count += 1
            results.append({
                "id": row.get("id"),
                "symbol": symbol,
                "status": status,
                "return_pct": return_pct,
                "notes": notes,
            })

        try:
            self._get_local_store().add_ai_evaluation_run(
                run_id=str(uuid.uuid4()),
                run_type="scheduled",
                evaluated_count=evaluated_count,
                details_json=json.dumps(results, ensure_ascii=False)[:20000],
            )
        except Exception:
            pass

        return {
            "ok": True,
            "evaluated": evaluated_count,
            "total_open": len(open_rows),
            "details": results,
        }

    def _quote_candidates(self, symbol: str) -> List[str]:
        sym = str(symbol or "").strip().upper()
        if not sym:
            return []
        if sym.isdigit():
            return [f"{sym}.TW", f"{sym}.TWO", sym]
        return [sym]

    def _fetch_current_prices(self, symbols: List[str]) -> Dict[str, Optional[float]]:
        prices: Dict[str, Optional[float]] = {}
        if not symbols:
            return prices
        try:
            import yfinance as yf

            for symbol in symbols:
                price: Optional[float] = None
                for candidate in self._quote_candidates(symbol):
                    try:
                        ticker = yf.Ticker(candidate)
                        fast_info = getattr(ticker, "fast_info", None)
                        last_price = getattr(fast_info, "last_price", None) if fast_info is not None else None
                        if last_price is None:
                            hist = ticker.history(period="5d")
                            if hist is not None and not hist.empty:
                                last_price = float(hist["Close"].dropna().iloc[-1])
                        if last_price:
                            price = float(last_price)
                            break
                    except Exception:
                        continue
                prices[symbol] = price
        except ImportError:
            logger.warning("[PredictionTracker] yfinance not installed, cannot evaluate prices")
        return prices

    # ------------------------------------------------------------------
    # Shared aggregation helpers
    # ------------------------------------------------------------------

    def _split_rows(self, rows: List[Dict[str, Any]]) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        evaluated = [r for r in rows if str(r.get("status") or "") != "open"]
        still_open = [r for r in rows if str(r.get("status") or "") == "open"]
        return evaluated, still_open

    def _returns(self, rows: List[Dict[str, Any]]) -> List[float]:
        values: List[float] = []
        for row in rows:
            val = row.get("actual_return_pct")
            if val is None:
                continue
            try:
                values.append(float(val))
            except Exception:
                continue
        return values

    def _version_breakdown(self, rows: List[Dict[str, Any]], field: str) -> List[Dict[str, Any]]:
        grouped: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            key = str(row.get(field) or "unknown").strip() or "unknown"
            bucket = grouped.setdefault(key, {"version": key, "total": 0, "wins": 0, "returns": []})
            bucket["total"] += 1
            if row.get("status") == "hit_target":
                bucket["wins"] += 1
            ret = row.get("actual_return_pct")
            if ret is not None:
                try:
                    bucket["returns"].append(float(ret))
                except Exception:
                    pass

        result: List[Dict[str, Any]] = []
        for key, item in grouped.items():
            total = int(item["total"])
            wins = int(item["wins"])
            returns = item["returns"]
            result.append({
                "version": key,
                "total": total,
                "wins": wins,
                "win_rate": round((wins / total) * 100, 2) if total else 0.0,
                "avg_return_pct": round(sum(returns) / len(returns), 2) if returns else 0.0,
            })
        result.sort(key=lambda x: (x["total"], x["win_rate"]), reverse=True)
        return result

    def _confidence_buckets(self, rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        buckets: Dict[str, Dict[str, Any]] = {}
        for label, lo, hi in [
            ("0-20", 0, 20),
            ("21-40", 21, 40),
            ("41-60", 41, 60),
            ("61-80", 61, 80),
            ("81-100", 81, 100),
        ]:
            bucket_rows = [r for r in rows if lo <= int(r.get("confidence") or 0) <= hi]
            wins = [r for r in bucket_rows if r.get("status") == "hit_target"]
            buckets[label] = {
                "total": len(bucket_rows),
                "wins": len(wins),
                "win_rate": round((len(wins) / len(bucket_rows)) * 100, 2) if bucket_rows else 0.0,
            }
        return buckets

    def _build_recommendations(self, evaluated: List[Dict[str, Any]], confidence_buckets: Dict[str, Dict[str, Any]]) -> List[str]:
        if not evaluated:
            return ["目前尚無足夠已驗證樣本，先持續蒐集建議與結果。"]

        wins = [r for r in evaluated if r.get("status") == "hit_target"]
        expired = [r for r in evaluated if r.get("status") == "expired"]
        win_rate = round((len(wins) / len(evaluated)) * 100, 2) if evaluated else 0.0
        notes: List[str] = []

        if win_rate < 40:
            notes.append("整體命中率低於 40%，建議先收緊 prompt 的結論強度與進場條件。")
        if len(expired) > len(evaluated) * 0.45:
            notes.append("過期未達標比例偏高，建議縮短 horizon 或收斂目標價設定。")
        high_conf = confidence_buckets.get("81-100", {})
        if high_conf.get("total", 0) >= 5 and high_conf.get("win_rate", 0) < 50:
            notes.append("高信心區間勝率偏低，表示模型過度自信，應優先調整 confidence calibration。")

        prompt_versions = self._version_breakdown(evaluated, "prompt_version")
        if prompt_versions:
            worst_prompt = sorted(prompt_versions, key=lambda x: (x["win_rate"], -x["total"]))[0]
            if worst_prompt["total"] >= 5:
                notes.append(
                    f"Prompt 版本 {worst_prompt['version']} 表現最弱，建議先檢查該版本的輸出格式與判斷規則。"
                )

        if not notes:
            notes.append("目前模型與規則表現穩定，可先持續累積樣本再調整 prompt。")
        return notes

    # ------------------------------------------------------------------
    # 3) Weekly stats
    # ------------------------------------------------------------------

    def get_weekly_stats(self, weeks_back: int = 1) -> dict:
        start = (_now() - timedelta(weeks=max(1, weeks_back))).isoformat()
        rows = self.list_predictions(exclude_status="open", evaluated_since=start, limit=5000)
        returns = self._returns(rows)
        wins = sum(1 for r in rows if r.get("status") == "hit_target")
        total = len(rows)
        return {
            "ok": True,
            "period": f"last_{weeks_back}_weeks",
            "start": start,
            "total": total,
            "wins": wins,
            "losses": total - wins,
            "win_rate": round((wins / total) * 100, 2) if total else 0.0,
            "avg_return_pct": round(sum(returns) / len(returns), 2) if returns else 0.0,
            "predictions": rows,
        }

    # ------------------------------------------------------------------
    # 4) Monthly review
    # ------------------------------------------------------------------

    def get_monthly_review(self, year: int, month: int) -> dict:
        month_start = datetime(year, month, 1, tzinfo=_TZ)
        month_end = datetime(year + (1 if month == 12 else 0), 1 if month == 12 else month + 1, 1, tzinfo=_TZ)
        rows = self.list_predictions(
            predicted_since=month_start.isoformat(),
            predicted_before=month_end.isoformat(),
            limit=5000,
        )
        evaluated, still_open = self._split_rows(rows)
        wins = [r for r in evaluated if r.get("status") == "hit_target"]
        stops = [r for r in evaluated if r.get("status") == "hit_stop"]
        expired = [r for r in evaluated if r.get("status") == "expired"]
        returns = self._returns(evaluated)

        direction_stats: Dict[str, Dict[str, Any]] = {}
        for direction in ("bullish", "bearish", "neutral"):
            d_rows = [r for r in evaluated if r.get("direction") == direction]
            d_returns = self._returns(d_rows)
            d_wins = [r for r in d_rows if r.get("status") == "hit_target"]
            direction_stats[direction] = {
                "total": len(d_rows),
                "wins": len(d_wins),
                "win_rate": round((len(d_wins) / len(d_rows)) * 100, 2) if d_rows else 0.0,
                "avg_return_pct": round(sum(d_returns) / len(d_returns), 2) if d_returns else 0.0,
            }

        tier_stats: Dict[str, Dict[str, Any]] = {}
        for tier in ("free", "pro", "premium"):
            tier_rows = [r for r in evaluated if str(r.get("tier") or "") == tier]
            tier_wins = [r for r in tier_rows if r.get("status") == "hit_target"]
            tier_stats[tier] = {
                "total": len(tier_rows),
                "wins": len(tier_wins),
                "win_rate": round((len(tier_wins) / len(tier_rows)) * 100, 2) if tier_rows else 0.0,
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
            "win_rate": round((len(wins) / len(evaluated)) * 100, 2) if evaluated else 0.0,
            "avg_return_pct": round(sum(returns) / len(returns), 2) if returns else 0.0,
            "best_return_pct": max(returns) if returns else 0.0,
            "worst_return_pct": min(returns) if returns else 0.0,
            "direction_stats": direction_stats,
            "tier_stats": tier_stats,
            "prompt_versions": self._version_breakdown(evaluated, "prompt_version"),
            "rule_versions": self._version_breakdown(evaluated, "rule_version"),
            "model_versions": self._version_breakdown(evaluated, "model_name"),
        }

    # ------------------------------------------------------------------
    # 5) Quarterly audit
    # ------------------------------------------------------------------

    def get_quarterly_audit(self, year: int, quarter: int) -> dict:
        if quarter < 1 or quarter > 4:
            return {"ok": False, "error": "quarter must be 1-4"}

        start_month = (quarter - 1) * 3 + 1
        q_start = datetime(year, start_month, 1, tzinfo=_TZ)
        end_month = start_month + 3
        q_end = datetime(year + (1 if end_month > 12 else 0), 1 if end_month > 12 else end_month, 1, tzinfo=_TZ)
        rows = self.list_predictions(
            predicted_since=q_start.isoformat(),
            predicted_before=q_end.isoformat(),
            limit=5000,
        )
        evaluated, still_open = self._split_rows(rows)
        wins = [r for r in evaluated if r.get("status") == "hit_target"]
        stops = [r for r in evaluated if r.get("status") == "hit_stop"]
        expired = [r for r in evaluated if r.get("status") == "expired"]
        returns = self._returns(evaluated)

        monthly_breakdown: List[Dict[str, Any]] = []
        for offset in range(3):
            month = start_month + offset
            m_rows = [r for r in evaluated if _parse_month(r.get("predicted_at", "")) == month]
            m_returns = self._returns(m_rows)
            m_wins = [r for r in m_rows if r.get("status") == "hit_target"]
            monthly_breakdown.append({
                "month": month,
                "total": len(m_rows),
                "wins": len(m_wins),
                "win_rate": round((len(m_wins) / len(m_rows)) * 100, 2) if m_rows else 0.0,
                "avg_return_pct": round(sum(m_returns) / len(m_returns), 2) if m_returns else 0.0,
            })

        symbol_stats: Dict[str, Dict[str, Any]] = {}
        for row in evaluated:
            symbol = str(row.get("symbol") or "UNKNOWN")
            item = symbol_stats.setdefault(symbol, {"total": 0, "wins": 0, "returns": []})
            item["total"] += 1
            if row.get("status") == "hit_target":
                item["wins"] += 1
            if row.get("actual_return_pct") is not None:
                try:
                    item["returns"].append(float(row["actual_return_pct"]))
                except Exception:
                    pass

        top_symbols: List[Dict[str, Any]] = []
        for symbol, item in sorted(symbol_stats.items(), key=lambda x: x[1]["total"], reverse=True)[:10]:
            total = int(item["total"])
            wins_for_symbol = int(item["wins"])
            sym_returns = item["returns"]
            top_symbols.append({
                "symbol": symbol,
                "total": total,
                "wins": wins_for_symbol,
                "win_rate": round((wins_for_symbol / total) * 100, 2) if total else 0.0,
                "avg_return_pct": round(sum(sym_returns) / len(sym_returns), 2) if sym_returns else 0.0,
            })

        confidence_buckets = self._confidence_buckets(evaluated)
        recommendations = self._build_recommendations(evaluated, confidence_buckets)

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
            "expired": len(expired),
            "win_rate": round((len(wins) / len(evaluated)) * 100, 2) if evaluated else 0.0,
            "avg_return_pct": round(sum(returns) / len(returns), 2) if returns else 0.0,
            "best_return_pct": max(returns) if returns else 0.0,
            "worst_return_pct": min(returns) if returns else 0.0,
            "monthly_breakdown": monthly_breakdown,
            "top_symbols": top_symbols,
            "confidence_calibration": confidence_buckets,
            "prompt_versions": self._version_breakdown(evaluated, "prompt_version"),
            "rule_versions": self._version_breakdown(evaluated, "rule_version"),
            "model_versions": self._version_breakdown(evaluated, "model_name"),
            "recommendations": recommendations,
        }

    # ------------------------------------------------------------------
    # 6) Accuracy dashboard
    # ------------------------------------------------------------------

    def get_accuracy_dashboard(self) -> dict:
        rows = self.list_predictions(limit=5000)
        evaluated, still_open = self._split_rows(rows)
        returns = self._returns(evaluated)
        wins = [r for r in evaluated if r.get("status") == "hit_target"]
        stops = [r for r in evaluated if r.get("status") == "hit_stop"]
        expired = [r for r in evaluated if r.get("status") == "expired"]

        recent_start = (_now() - timedelta(days=7)).isoformat()
        recent = [r for r in evaluated if str(r.get("evaluated_at") or "") >= recent_start]
        recent_wins = [r for r in recent if r.get("status") == "hit_target"]

        return {
            "ok": True,
            "total_predictions": len(rows),
            "open": len(still_open),
            "evaluated": len(evaluated),
            "wins": len(wins),
            "stops": len(stops),
            "expired": len(expired),
            "win_rate": round((len(wins) / len(evaluated)) * 100, 2) if evaluated else 0.0,
            "avg_return_pct": round(sum(returns) / len(returns), 2) if returns else 0.0,
            "best_return_pct": max(returns) if returns else 0.0,
            "worst_return_pct": min(returns) if returns else 0.0,
            "recent_7d": {
                "evaluated": len(recent),
                "wins": len(recent_wins),
                "win_rate": round((len(recent_wins) / len(recent)) * 100, 2) if recent else 0.0,
            },
            "confidence_calibration": self._confidence_buckets(evaluated),
            "prompt_versions": self._version_breakdown(evaluated, "prompt_version"),
            "rule_versions": self._version_breakdown(evaluated, "rule_version"),
            "model_versions": self._version_breakdown(evaluated, "model_name"),
            "recommendations": self._build_recommendations(evaluated, self._confidence_buckets(evaluated)),
        }


prediction_tracker = AIPredictionTracker()
