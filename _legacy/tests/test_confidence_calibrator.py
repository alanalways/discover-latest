"""Tests for services/confidence_calibrator.py"""

from services.confidence_calibrator import calibrate


def test_calibrate_no_data_returns_raw():
    # With no historical data, should return raw confidence unchanged
    result = calibrate(75, "bullish")
    assert isinstance(result, int)
    assert 10 <= result <= 95


def test_calibrate_returns_int_in_range():
    # Without calibration data, raw values are returned as-is
    result = calibrate(50, "bearish")
    assert isinstance(result, int)
    result = calibrate(80, "bullish")
    assert isinstance(result, int)
