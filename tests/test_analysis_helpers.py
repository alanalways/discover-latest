"""Tests for lightweight analysis tracking helpers."""

from routes.analysis import _extract_numeric_levels, _pick_tracking_price


def test_extract_numeric_levels_handles_range_text():
    assert _extract_numeric_levels("101.5-108.2") == [101.5, 108.2]
    assert _extract_numeric_levels("進場區 233.0 ~ 236.5") == [233.0, 236.5]


def test_pick_tracking_price_uses_midpoint_for_entry():
    assert _pick_tracking_price("100-110", prefer="mid") == 105.0
    assert _pick_tracking_price("120", prefer="mid") == 120.0


def test_pick_tracking_price_uses_high_and_low():
    assert _pick_tracking_price("100-110", prefer="high") == 110.0
    assert _pick_tracking_price("100-110", prefer="low") == 100.0

