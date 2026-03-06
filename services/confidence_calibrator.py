"""
Confidence Calibrator
Adjusts AI prediction confidence scores based on historical accuracy.
Uses prediction_tracker data to compute calibration curves.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Calibration cache (recompute every 6 hours)
_CALIBRATION_TTL = 21600
_calibration: Optional[Dict[str, Any]] = None
_calibration_ts: float = 0.0
_lock = threading.Lock()


def _compute_calibration() -> Dict[str, Any]:
    """
    Compute calibration data from historical predictions.
    Groups predictions by confidence bucket and computes actual win rate per bucket.
    """
    try:
        from services.ai_prediction_tracker import prediction_tracker
        # Fetch all resolved predictions
        data = prediction_tracker._request(
            "GET",
            "ai_predictions",
            params={
                "status": "neq.open",
                "select": "confidence,status,direction",
                "limit": "2000",
            },
            silent=True,
        )
        if not isinstance(data, list) or len(data) < 10:
            return {"buckets": {}, "sample_size": 0, "ready": False}

        # Group by confidence bucket (10-point ranges)
        buckets: Dict[str, Dict[str, int]] = {}
        for pred in data:
            conf = int(pred.get("confidence", 50))
            status = str(pred.get("status", ""))
            bucket_key = f"{(conf // 10) * 10}-{(conf // 10) * 10 + 9}"

            if bucket_key not in buckets:
                buckets[bucket_key] = {"total": 0, "correct": 0}
            buckets[bucket_key]["total"] += 1
            if status == "correct":
                buckets[bucket_key]["correct"] += 1

        # Compute actual win rate per bucket
        calibration_map = {}
        for bucket_key, counts in buckets.items():
            if counts["total"] >= 3:  # Need at least 3 samples
                actual_rate = counts["correct"] / counts["total"]
                calibration_map[bucket_key] = {
                    "actual_win_rate": round(actual_rate * 100, 1),
                    "sample_size": counts["total"],
                    "correct": counts["correct"],
                }

        return {
            "buckets": calibration_map,
            "sample_size": len(data),
            "ready": len(calibration_map) >= 3,
        }

    except Exception as e:
        logger.debug("[ConfidenceCalibrator] compute error: %s", e)
        return {"buckets": {}, "sample_size": 0, "ready": False}


def get_calibration(force: bool = False) -> Dict[str, Any]:
    """Get cached calibration data."""
    global _calibration, _calibration_ts
    with _lock:
        now = time.time()
        if not force and _calibration and (now - _calibration_ts) < _CALIBRATION_TTL:
            return _calibration

    result = _compute_calibration()

    with _lock:
        _calibration = result
        _calibration_ts = time.time()

    return result


def calibrate(raw_confidence: int, direction: str = "bullish") -> int:
    """
    Adjust raw AI confidence based on historical calibration data.

    If calibration data shows that predictions at confidence=80 actually
    win only 55% of the time, we adjust downward.

    Returns adjusted confidence (clamped 10-95).
    """
    cal = get_calibration()
    if not cal.get("ready"):
        return raw_confidence  # Not enough data yet

    buckets = cal.get("buckets", {})
    bucket_key = f"{(raw_confidence // 10) * 10}-{(raw_confidence // 10) * 10 + 9}"
    bucket_data = buckets.get(bucket_key)

    if not bucket_data or bucket_data.get("sample_size", 0) < 5:
        return raw_confidence  # Not enough data for this bucket

    actual_rate = bucket_data["actual_win_rate"]
    # Midpoint of the bucket represents "expected" rate
    expected_rate = (raw_confidence // 10) * 10 + 5

    # Compute adjustment factor
    if expected_rate > 0:
        ratio = actual_rate / expected_rate
        adjusted = int(raw_confidence * ratio)
    else:
        adjusted = raw_confidence

    # Clamp to reasonable range
    return max(10, min(95, adjusted))


def get_calibration_report() -> Dict[str, Any]:
    """Get a human-readable calibration report for admin dashboard."""
    cal = get_calibration(force=True)
    buckets = cal.get("buckets", {})

    overconfident = []
    underconfident = []
    well_calibrated = []

    for bucket_key, data in sorted(buckets.items()):
        midpoint = int(bucket_key.split("-")[0]) + 5
        actual = data["actual_win_rate"]
        diff = actual - midpoint

        entry = {
            "bucket": bucket_key,
            "expected": midpoint,
            "actual": actual,
            "samples": data["sample_size"],
            "diff": round(diff, 1),
        }

        if diff < -10:
            overconfident.append(entry)
        elif diff > 10:
            underconfident.append(entry)
        else:
            well_calibrated.append(entry)

    return {
        "ready": cal.get("ready", False),
        "total_predictions": cal.get("sample_size", 0),
        "overconfident_buckets": overconfident,
        "underconfident_buckets": underconfident,
        "well_calibrated_buckets": well_calibrated,
        "buckets": buckets,
    }


# Singleton access
confidence_calibrator = type("ConfidenceCalibrator", (), {
    "calibrate": staticmethod(calibrate),
    "get_calibration": staticmethod(get_calibration),
    "get_report": staticmethod(get_calibration_report),
})()
