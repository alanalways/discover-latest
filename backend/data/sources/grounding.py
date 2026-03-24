"""
與文件結構對齊的 grounding wrapper。

實際實作仍位於 backend.gemini.grounding。
"""

from backend.gemini.grounding import (
    BatchGroundingAgent,
    extract_grounding_sources,
    format_grounding_disclaimer,
)

__all__ = [
    "BatchGroundingAgent",
    "extract_grounding_sources",
    "format_grounding_disclaimer",
]
