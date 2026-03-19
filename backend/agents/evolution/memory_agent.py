"""
backend/agents/evolution/memory_agent.py
RAG 記憶官（Sonnet 撰寫）

職責：
- 將報告摘要向量化並存入 Pinecone
- 查詢相似報告（供 Chief Analyst 參考歷史脈絡）

向量化：使用 Gemini Embedding（gemini-embedding-exp-03-07）
儲存：  透過 backend/data/storage/vector_store.py
"""

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

_EMBEDDING_MODEL  = "gemini-embedding-exp-03-07"
_EMBEDDING_DIM    = 3072  # gemini-embedding-exp-03-07 輸出維度
_AGENT_DISPLAY    = "MemoryAgent"


class MemoryAgent:
    """
    RAG 記憶官 — 負責報告向量化與相似召回。

    設計原則：
    - Pinecone 或 Embedding 失敗均 graceful degrade（回傳空，不拋例外）
    - 不在主分析 Pipeline 的關鍵路徑上（失敗不影響報告生成）
    """

    def store_report(
        self,
        report_id:    str,
        symbol:       str,
        market:       str,
        summary_text: str,
    ) -> bool:
        """
        將報告摘要向量化後存入 Pinecone。

        Args:
            report_id:    reports 表的 UUID
            symbol:       股票代號
            market:       市場（TW / US）
            summary_text: 報告摘要文字（通常取 final_report 前 1000 字）

        Returns:
            True 表示成功存入，False 表示失敗（已 graceful degrade）
        """
        vector = self._embed(summary_text)
        if vector is None:
            logger.warning(f"[{_AGENT_DISPLAY}] embedding 失敗，跳過儲存 {report_id}")
            return False

        from backend.data.storage.vector_store import upsert

        metadata = {
            "report_id": report_id,
            "symbol":    symbol,
            "market":    market,
            "text":      summary_text[:500],  # metadata 截短以節省空間
        }

        ok = upsert(
            vector_id=report_id,
            vector=vector,
            metadata=metadata,
            namespace="reports",
        )
        if ok:
            logger.info(f"[{_AGENT_DISPLAY}] 已儲存 {symbol} ({report_id})")
        return ok

    def recall_similar(
        self,
        symbol:     str,
        market:     str,
        query_text: str,
        top_k:      int = 5,
    ) -> list[dict]:
        """
        召回相似的歷史報告。

        Args:
            symbol:     股票代號（用於 metadata 過濾）
            market:     市場
            query_text: 查詢文字（通常是當前分析的摘要）
            top_k:      最多回傳幾筆

        Returns:
            list of dict: [{report_id, symbol, market, score, text}]
            失敗時回傳空列表。
        """
        vector = self._embed(query_text)
        if vector is None:
            logger.warning(f"[{_AGENT_DISPLAY}] embedding 失敗，跳過召回")
            return []

        from backend.data.storage.vector_store import query as vec_query

        # 可選：只召回同一支股票的歷史
        filter_dict = {"symbol": symbol, "market": market}

        results = vec_query(
            vector=vector,
            top_k=top_k,
            namespace="reports",
            filter=filter_dict,
        )

        # 格式化輸出
        output = []
        for r in results:
            meta = r.get("metadata", {})
            output.append(
                {
                    "report_id": meta.get("report_id", r["id"]),
                    "symbol":    meta.get("symbol", symbol),
                    "market":    meta.get("market", market),
                    "score":     r["score"],
                    "text":      meta.get("text", ""),
                }
            )

        return output

    # ─────────────────────────────────────────────────────────
    # 內部：Gemini Embedding
    # ─────────────────────────────────────────────────────────

    def _embed(self, text: str) -> Optional[list[float]]:
        """
        使用 Gemini Embedding 將文字轉換為向量。
        失敗時回傳 None。
        """
        try:
            from google import genai
            from google.genai import types

            api_key = os.environ.get("GEMINI_API_KEY", "")
            if not api_key:
                logger.warning(f"[{_AGENT_DISPLAY}] GEMINI_API_KEY 未設定，跳過 embedding")
                return None

            client = genai.Client(api_key=api_key)

            # 截斷過長文字（embedding 有 token 上限）
            truncated = text[:8000]

            result = client.models.embed_content(
                model=_EMBEDDING_MODEL,
                contents=truncated,
                config=types.EmbedContentConfig(
                    task_type="RETRIEVAL_DOCUMENT",
                ),
            )

            # 新版 SDK 回傳結構
            if hasattr(result, "embeddings") and result.embeddings:
                return result.embeddings[0].values
            # 相容舊回傳格式
            if hasattr(result, "embedding") and result.embedding:
                return result.embedding.values

            logger.warning(f"[{_AGENT_DISPLAY}] embedding 回傳格式異常: {result}")
            return None

        except Exception as e:
            logger.error(f"[{_AGENT_DISPLAY}] Gemini embedding 失敗: {e}")
            return None


# ─────────────────────────────────────────────────────────
# 模組級單例
# ─────────────────────────────────────────────────────────

_memory_agent: Optional[MemoryAgent] = None


def get_memory_agent() -> MemoryAgent:
    global _memory_agent
    if _memory_agent is None:
        _memory_agent = MemoryAgent()
    return _memory_agent
