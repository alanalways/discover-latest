"""Tests for services/macro_context_service.py"""

from services.macro_context_service import format_macro_for_prompt, get_macro_context


def test_get_macro_context_returns_dict():
    ctx = get_macro_context()
    assert isinstance(ctx, dict)
    assert "indicators" in ctx
    assert "regime" in ctx


def test_format_macro_for_prompt_returns_string():
    result = format_macro_for_prompt()
    assert isinstance(result, str)
