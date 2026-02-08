"""
Gemini AI Service - 雙段 AI 生成（Grounding + Final）
Stage 1: 使用 MODEL_GROUNDING + Google Search grounding 取得事實基礎
Stage 2: 使用 MODEL_FINAL 產生最終分析輸出
支援 7 組 API Key 輪流使用（Round-robin）
v2: 加入 timeout 機制和詳細 debug logging
"""
import os
import threading
import traceback
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from typing import Optional, Dict, Any, List
from config.models import MODEL_GROUNDING, MODEL_FINAL

# Timeout 設定（秒）
GEMINI_TIMEOUT_STAGE1 = 30  # Grounding stage
GEMINI_TIMEOUT_STAGE2 = 45  # Final generation stage

# ── Key Rotation ──
_key_pool: List[str] = []
_key_index: int = 0
_key_lock = threading.Lock()


def _load_key_pool() -> List[str]:
    """從環境變數載入 API Key 池"""
    global _key_pool
    if _key_pool:
        return _key_pool

    # 1. 優先：GEMINI_API_KEYS（逗號分隔，支援 7 組 Key 輪流使用）
    multi_keys = os.environ.get("GEMINI_API_KEYS", "")
    if multi_keys:
        keys = [k.strip() for k in multi_keys.split(",") if k.strip()]
        if keys:
            _key_pool = keys
            print(f"[Gemini] Loaded {len(keys)} API keys from GEMINI_API_KEYS")
            return _key_pool

    # 2. 備援：單一 GEMINI_API_KEY
    single = os.environ.get("GEMINI_API_KEY", "")
    if single:
        _key_pool = [single]
        print("[Gemini] Loaded 1 API key from GEMINI_API_KEY")
        return _key_pool

    # 3. 最後備援：Supabase Vault
    try:
        from adapters.supabase_adapter import supabase_adapter
        vault_keys = supabase_adapter.get_gemini_keys()
        if vault_keys:
            _key_pool = vault_keys
            print(f"[Gemini] Loaded {len(vault_keys)} API keys from Supabase Vault")
            return _key_pool
    except Exception:
        pass

    print("[Gemini] No API keys found")
    return []


def _get_next_key() -> str:
    """Round-robin 取得下一組 API Key"""
    global _key_index
    pool = _load_key_pool()
    if not pool:
        return ""
    with _key_lock:
        key = pool[_key_index % len(pool)]
        _key_index += 1
    return key


class GeminiService:
    """Gemini AI 雙段生成服務（支援 Key 輪流使用）"""

    def __init__(self):
        self._models_valid: bool = False
        self._errors: List[str] = []
        self._generate_lock = threading.Lock()

    def _get_api_key(self) -> str:
        """取得 API Key（Round-robin 輪流）"""
        return _get_next_key()

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
            return {"success": False, "error": "Discover Latest AI 金鑰未設定", "analysis": "", "grounding_sources": []}

        try:
            import google.generativeai as genai
        except ImportError:
            return {"success": False, "error": "google-generativeai 未安裝", "analysis": "", "grounding_sources": []}

        with self._generate_lock:
            return self._generate_analysis_locked(
                genai, api_key, symbol, stock_info, smc_summary,
                prediction_summary, user_question,
            )

    def _generate_analysis_locked(
        self,
        genai,
        api_key: str,
        symbol: str,
        stock_info: Dict = None,
        smc_summary: str = "",
        prediction_summary: str = "",
        user_question: str = "",
    ) -> Dict[str, Any]:
        """Internal: runs under self._generate_lock to prevent race conditions."""
        genai.configure(api_key=api_key)

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
        stage1_start = time.time()
        print(f"[Gemini] Stage 1 starting for {symbol}...")
        
        def _run_stage1():
            """Stage 1 執行函數（可被 timeout 包裝）"""
            nonlocal grounding_text, grounding_sources
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
            except Exception as e:
                print(f"[Gemini] Stage 1 grounding tool failed, falling back: {e}")
                # Fallback without grounding tool
                grounding_response = grounding_model.generate_content(grounding_prompt)

            if grounding_response and grounding_response.text:
                return grounding_response
            return None

        try:
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(_run_stage1)
                try:
                    grounding_response = future.result(timeout=GEMINI_TIMEOUT_STAGE1)
                    if grounding_response and grounding_response.text:
                        grounding_text = grounding_response.text
                        print(f"[Gemini] Stage 1 completed in {time.time() - stage1_start:.1f}s")
                        
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
                except FuturesTimeoutError:
                    print(f"[Gemini] Stage 1 TIMEOUT after {GEMINI_TIMEOUT_STAGE1}s")
                    grounding_text = "(Grounding 階段超時，使用本地資料)"
                    
        except Exception as e:
            print(f"[Gemini] Stage 1 (Grounding) error: {e}")
            traceback.print_exc()
            grounding_text = "(Grounding 階段失敗，使用本地資料)"

        # ── Stage 2: Final Output (may use a different key for load distribution) ──
        stage2_start = time.time()
        print(f"[Gemini] Stage 2 starting for {symbol}...")
        
        # Get another key for Stage 2 (round-robin continues)
        api_key_2 = self._get_api_key()
        if api_key_2 and api_key_2 != api_key:
            genai.configure(api_key=api_key_2)
            
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
- 必須標註「此分析由 AI 生成，不構成投資建議」"""

        def _run_stage2():
            """Stage 2 執行函數（可被 timeout 包裝）"""
            final_model = genai.GenerativeModel(MODEL_FINAL)
            return final_model.generate_content(final_prompt)
            
        try:
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(_run_stage2)
                try:
                    final_response = future.result(timeout=GEMINI_TIMEOUT_STAGE2)
                    
                    analysis = final_response.text if final_response and final_response.text else "AI 分析生成失敗"
                    print(f"[Gemini] Stage 2 completed in {time.time() - stage2_start:.1f}s, {len(analysis)} chars")

                    return {
                        "success": True,
                        "analysis": analysis,
                        "grounding_sources": grounding_sources,
                        "model_used": MODEL_FINAL,
                        "grounding_model": MODEL_GROUNDING,
                        "error": None,
                    }
                    
                except FuturesTimeoutError:
                    print(f"[Gemini] Stage 2 TIMEOUT after {GEMINI_TIMEOUT_STAGE2}s")
                    return {
                        "success": False,
                        "error": f"AI 生成超時（{GEMINI_TIMEOUT_STAGE2}秒），請稍後再試",
                        "analysis": "",
                        "grounding_sources": grounding_sources,
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
