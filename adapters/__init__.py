"""
Adapters 模組 - 資料來源整合
僅匯出實際被 service/route 使用的 adapter。
"""
from .supabase_adapter import SupabaseAdapter, supabase
from .yahoo_adapter import YahooAdapter, yahoo_adapter
from .fx_adapter import FXAdapter, fx_adapter
from .finmind_adapter import FinMindAdapter, finmind_adapter

__all__ = [
    "SupabaseAdapter",
    "supabase",
    "YahooAdapter",
    "yahoo_adapter",
    "FXAdapter",
    "fx_adapter",
    "FinMindAdapter",
    "finmind_adapter",
]
