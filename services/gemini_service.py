"""
Gemini AI Service - 雙段 AI 生成（Grounding + Final）
Stage 1: 使用 MODEL_GROUNDING + Google Search grounding 取得事實基礎
Stage 2: 使用 MODEL_FINAL 產生最終分析輸出
"""
import os
import traceback
from typing import Optional, Dict, Any, List
from config.models import MODEL_GROUNDING, MODEL_FINAL


class GeminiService:
    """Gemini AI 雙段生成服務"""

    def __init__(self):
        self._api_key: Optional[str] = None
        self._models_valid: bool = False
        self._errors: List[str] = []

    def _get_api_key(self) -> str:
        if not self._api_key:
            self._api_key = os.environ.get("GEMINI_API_KEY", "")
            if not self._api_key:
                try:
                    from adapters.supabase_adapter import supabase_adapter
                    keys = supabase_adapter.get_gemini_keys()
                    if keys:
                        self._api_key = keys[0]
                except Exception:
                    pass
        return self._api_key or ""

    def is_available(self) -> bool:
        """AI 功能是否可用"""
        return bool(self._get_api_key())

    def generate_analysis(
        self,
        symbol: str,
        stock_info: Dict = None,
        smc_summary: str = "",
        prediction_summary: str = "",
        user_question: str = "",
        max_output_chars: int = 2000,
    ) -> Dict[str, Any]:
        """
        雙段 AI 分析生成

        Stage 1 (Grounding): 使用 Google Search 查詢即時資訊
        Stage 2 (Final): 根據 grounding 結果 + 本地分析產生最終輸出

        Returns:
            {
                "success": bool,
                "analysis": str,           # 最終分析文字
                "grounding_sources": list,  # Google Search grounding 來源
                "model_used": str,
                "error": str or None,
            }
        """
        api_key = self._get_api_key()
        if not api_key:
            return {"success": False, "error": "Gemini API Key 未設定", "analysis": "", "grounding_sources": []}

        try:
            import google.generativeai as genai
            genai.configure(api_key=api_key)
        except ImportError:
            return {"success": False, "error": "google-generativeai 未安裝", "analysis": "", "grounding_sources": []}

        # Build context
        context_parts = []
        if stock_info:
            name = stock_info.get("name", symbol)
            price = stock_info.get("price", 0)
            chg = stock_info.get("change_percent", 0)
            context_parts.append(f"股票: {symbol} ({name}), 現價: {price}, 漲跌: {chg:.2f}%")
        if smc_summary:
            context_parts.append(f"SMC 分析: {smc_summary}")
        if prediction_summary:
            context_parts.append(f"預測摘要: {prediction_summary}")
        context = "\n".join(context_parts)

        # ── Stage 1: Grounding with Google Search ──
        grounding_text = ""
        grounding_sources = []
        try:
            grounding_prompt = f"""你是一位專業金融分析師。請針對以下股票搜尋最新的市場新聞、財報資訊和分析師觀點。
股票代號: {symbol}
{context}
{f'用戶問題: {user_question}' if user_question else ''}
請簡潔列出 3-5 條最相關的即時資訊。"""

            grounding_model = genai.GenerativeModel(MODEL_GROUNDING)
            # Try with Google Search grounding tool
            try:
                from google.generativeai.types import Tool
                google_search_tool = Tool(google_search={})
                grounding_response = grounding_model.generate_content(
                    grounding_prompt,
                    tools=[google_search_tool],
                )
            except Exception:
                # Fallback without grounding tool
                grounding_response = grounding_model.generate_content(grounding_prompt)

            if grounding_response and grounding_response.text:
                grounding_text = grounding_response.text

            # Extract grounding metadata if available
            if hasattr(grounding_response, 'candidates') and grounding_response.candidates:
                candidate = grounding_response.candidates[0]
                if hasattr(candidate, 'grounding_metadata') and candidate.grounding_metadata:
                    gm = candidate.grounding_metadata
                    if hasattr(gm, 'grounding_chunks'):
                        for chunk in gm.grounding_chunks:
                            if hasattr(chunk, 'web'):
                                grounding_sources.append({
                                    "title": getattr(chunk.web, 'title', ''),
                                    "uri": getattr(chunk.web, 'uri', ''),
                                })

        except Exception as e:
            print(f"[Gemini] Stage 1 (Grounding) error: {e}")
            traceback.print_exc()
            grounding_text = "(Grounding 階段失敗，使用本地資料)"

        # ── Stage 2: Final Output ──
        try:
            final_prompt = f"""你是「DiscoverLatest 洞察運算」AI 分析師。
請根據以下資訊，產生一份精簡的投資分析報告（繁體中文）。

【股票資訊】
{context}

【即時市場情報（Grounding）】
{grounding_text}

【分析要求】
1. 市場觀點摘要（2-3 句）
2. 技術面分析（結合 SMC/ICT）
3. 風險提示
4. 投資建議（偏多/偏空/觀望 + 理由）

重要：
- 所有策略輸出必須包含 SMC/ICT 解讀
- 必須標註「此分析由 AI 生成，不構成投資建議」
- 輸出不超過 {max_output_chars} 字"""

            final_model = genai.GenerativeModel(MODEL_FINAL)
            final_response = final_model.generate_content(final_prompt)

            analysis = final_response.text if final_response and final_response.text else "AI 分析生成失敗"

            # Truncate if needed
            if len(analysis) > max_output_chars:
                analysis = analysis[:max_output_chars] + "…\n\n[輸出已截斷]"

            return {
                "success": True,
                "analysis": analysis,
                "grounding_sources": grounding_sources,
                "model_used": MODEL_FINAL,
                "grounding_model": MODEL_GROUNDING,
                "error": None,
            }

        except Exception as e:
            print(f"[Gemini] Stage 2 (Final) error: {e}")
            traceback.print_exc()
            return {
                "success": False,
                "error": f"AI 生成失敗: {type(e).__name__}",
                "analysis": "",
                "grounding_sources": grounding_sources,
            }


# Singleton
gemini_service = GeminiService()
