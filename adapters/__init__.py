"""
Adapters 模組 - 資料來源整合
"""
from .supabase_adapter import SupabaseAdapter, supabase
from .twse_adapter import TWSEAdapter, twse_adapter
from .tpex_adapter import TPEXAdapter, tpex_adapter
from .yahoo_adapter import YahooAdapter, yahoo_adapter
from .stooq_adapter import StooqAdapter, stooq_adapter
from .fx_adapter import FXAdapter, fx_adapter
from .finmind_adapter import FinMindAdapter, finmind_adapter

__all__ = [
    # Supabase
    "SupabaseAdapter",
    "supabase",
    # TWSE
    "TWSEAdapter",
    "twse_adapter",
    # TPEX
    "TPEXAdapter",
    "tpex_adapter",
    # Yahoo Finance
    "YahooAdapter",
    "yahoo_adapter",
    # Stooq
    "StooqAdapter",
    "stooq_adapter",
    # FX
    "FXAdapter",
    "fx_adapter",
    # FinMind
    "FinMindAdapter",
    "finmind_adapter",
]
