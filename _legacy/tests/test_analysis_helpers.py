"""Tests for technical indicator helpers."""

from services.technical_indicators import (
    extract_numeric_levels,
    pick_tracking_price,
    ema,
    rsi,
    safe_num,
    build_technical_snapshot,
)


def test_extract_numeric_levels_handles_range_text():
    assert extract_numeric_levels("101.5-108.2") == [101.5, 108.2]
    assert extract_numeric_levels("進場區 233.0 ~ 236.5") == [233.0, 236.5]


def test_pick_tracking_price_uses_midpoint_for_entry():
    assert pick_tracking_price("100-110", prefer="mid") == 105.0
    assert pick_tracking_price("120", prefer="mid") == 120.0


def test_pick_tracking_price_uses_high_and_low():
    assert pick_tracking_price("100-110", prefer="high") == 110.0
    assert pick_tracking_price("100-110", prefer="low") == 100.0


def test_ema_basic():
    values = [float(i) for i in range(1, 21)]
    result = ema(values, 5)
    assert result is not None
    assert isinstance(result, float)


def test_rsi_basic():
    values = [float(i) for i in range(1, 30)]
    result = rsi(values, 14)
    assert result is not None
    assert 0 <= result <= 100


def test_safe_num():
    assert safe_num(None) == 0.0
    assert safe_num("12.5") == 12.5
    assert safe_num("1,234.56") == 1234.56
    assert safe_num("abc") == 0.0


def test_build_technical_snapshot_returns_empty_for_short_history():
    assert build_technical_snapshot([]) == ""
    assert build_technical_snapshot([{"close": 100}] * 10) == ""
