"""
backend/gemini/grounding.py
Google Search Grounding 輔助模組
event/macro/sentiment agent 的 grounding 呼叫由 client.py 統一處理
此模組提供 grounding 相關的輔助工具函式
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def extract_grounding_sources(response_metadata) -> list[dict]:
    """
    從 Gemini response metadata 中提取 grounding 來源連結。
    供 audit_log 或前端顯示使用。
    """
    sources = []
    try:
        if not response_metadata:
            return sources

        grounding_metadata = getattr(
            response_metadata, "grounding_metadata", None
        )
        if not grounding_metadata:
            return sources

        for chunk in getattr(grounding_metadata, "grounding_chunks", []):
            web = getattr(chunk, "web", None)
            if web:
                sources.append({
                    "title": getattr(web, "title", ""),
                    "uri": getattr(web, "uri", ""),
                })

    except Exception as e:
        logger.debug(f"[Grounding] 無法提取來源: {e}")

    return sources


def format_grounding_disclaimer(sources: list[dict]) -> str:
    """
    將 grounding 來源格式化為報告末尾的免責聲明文字。
    """
    if not sources:
        return ""

    lines = ["\n\n---\n**資料來源（Google Search Grounding）**"]
    for i, src in enumerate(sources[:5], 1):  # 最多顯示 5 個來源
        title = src.get("title", "未知來源")
        uri = src.get("uri", "")
        if uri:
            lines.append(f"{i}. [{title}]({uri})")
        else:
            lines.append(f"{i}. {title}")

    return "\n".join(lines)
