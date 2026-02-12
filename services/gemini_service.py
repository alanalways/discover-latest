"""
Gemini AI Service - 雙段 AI 生成（Grounding + Final）
Stage 1: 使用 MODEL_GROUNDING + Google Search grounding 取得事實基礎
Stage 2: 使用 MODEL_FINAL 產生最終分析輸出
支援 7 組 API Key 輪流使用（Round-robin）
v3: 遷移至 google.genai SDK（取代已棄用的 google.generativeai）
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

    def _create_client(self, api_key: str):
        """建立 google.genai Client"""
        from google import genai
        return genai.Client(api_key=api_key)

    def generate_analysis(
        self,
        symbol: str,
        stock_info: Dict = None,
        smc_summary: str = "",
        prediction_summary: str = "",
        macro_data: Dict = None,
        user_question: str = "",
        tier: str = "free",
    ) -> Dict[str, Any]:
        """
        雙段 AI 分析生成（支援 tier 分級 prompt）

        Stage 1 (Grounding): 使用 Google Search 查詢即時資訊
        Stage 2 (Final): 根據 grounding 結果 + 本地分析產生最終輸出
        """
        api_key = self._get_api_key()
        if not api_key:
            return {"success": False, "error": "Gemini API 金鑰未設定"}

        try:
            from google import genai
            from google.genai import types
        except ImportError:
            return {"success": False, "error": "google-genai 未安裝", "analysis": "", "grounding_sources": []}

        with self._generate_lock:
            return self._generate_analysis_locked(
                api_key, symbol, stock_info, smc_summary,
                prediction_summary, macro_data, user_question, tier,
            )

    def _generate_analysis_locked(
        self,
        api_key: str,
        symbol: str,
        stock_info: Dict = None,
        smc_summary: str = "",
        prediction_summary: str = "",
        macro_data: Dict = None,
        user_question: str = "",
        tier: str = "free",
    ) -> Dict[str, Any]:
        """Internal: runs under self._generate_lock to prevent race conditions."""
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)

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
            context_parts.append(f"技術指標快照: {prediction_summary}")
        if macro_data:
            score = macro_data.get("score")
            light = macro_data.get("light")
            date = macro_data.get("date")
            context_parts.append(f"台灣景氣對策信號 (國發會 {date}): 分數 {score}, 燈號 {light}")
        context = "\n".join(context_parts)

        # ── Stage 1: Grounding with Google Search ──
        grounding_text = ""
        grounding_sources = []
        stage1_start = time.time()
        print(f"[Gemini] Stage 1 starting for {symbol}...")

        grounding_prompt = f"""你是一位專業金融分析師。請針對以下股票搜尋最新的市場新聞、財報資訊和分析師觀點。
股票代號: {symbol}
{context}
{f'用戶問題: {user_question}' if user_question else ''}
請簡潔列出 3-5 條最相關的即時資訊。"""

        def _run_stage1():
            """Stage 1 執行函數（可被 timeout 包裝）"""
            try:
                response = client.models.generate_content(
                    model=MODEL_GROUNDING,
                    contents=grounding_prompt,
                    config=types.GenerateContentConfig(
                        tools=[types.Tool(google_search=types.GoogleSearch())]
                    ),
                )
                return response
            except Exception as e1:
                print(f"[Gemini] Stage 1 grounding tool failed: {e1}")
                # Fallback: no grounding tool
                response = client.models.generate_content(
                    model=MODEL_GROUNDING,
                    contents=grounding_prompt,
                )
                return response

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
                            gm = getattr(candidate, 'grounding_metadata', None)
                            if gm:
                                chunks = getattr(gm, 'grounding_chunks', None) or getattr(gm, 'search_entry_point', None)
                                if hasattr(gm, 'grounding_chunks') and gm.grounding_chunks:
                                    for chunk in gm.grounding_chunks:
                                        web = getattr(chunk, 'web', None)
                                        if web:
                                            grounding_sources.append({
                                                "title": getattr(web, 'title', ''),
                                                "uri": getattr(web, 'uri', ''),
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
        client2 = genai.Client(api_key=api_key_2) if api_key_2 else client

        # ── Prompt 分級：Free vs Pro/Premium ──
        is_paid = tier in ("pro", "premium")
        is_premium = tier == "premium"

        # SMC 條件化：僅在有數據時才要求分析（防止幻覺）
        smc_section = ""
        if smc_summary and is_paid:
            smc_section = """\n📈 技術面觀察\n結合 SMC/ICT 分析（結構突破、訂單區塊、流動性等），說明目前的技術面狀況。用淺白的方式解釋，讓一般投資人也能理解。"""

        if is_paid:
            # Pro/Premium 完整版（Premium 額外要求更細的情境拆解）
            premium_extra = ""
            if is_premium:
                premium_extra = """
📚 SMC/ICT 進階觀察
根據市場結構（BOS/CHoCH）、流動性掃描、可能的訂單區塊，補充目前最可能的主力行為。

🧭 三情境交易地圖
請給「偏多情境」「偏空情境」「震盪情境」各一段，且每段都要有：觸發條件、進場想法、失效點。"""

            final_prompt = f"""你是「洞察運算」的資深投資分析顧問，正在為付費會員提供策略型建議。
請用專業、直接、可執行的語氣輸出，不要空泛。

【股票資訊】
{context}

【即時市場情報】
{grounding_text}

請務必結合以下維度：EMA、RSI、MACD、布林帶、Keltner 通道，以及（若有）SMC/ICT。
若資料不足請明確說「資料不足」，不要杜撰數值。

請依照以下結構回覆：

📊 市場快報
用 2-3 句話說明最新市場動態與基本定位（偏多/偏空/盤整）。

📈 技術面判讀
整理短中長線趨勢，明確指出 EMA 結構、RSI 區間、MACD 狀態、布林/Keltner 位置關係。
{smc_section}
🎯 進出場計畫
分成短線（1-5日）、中線（2-6週）、波段（1-3月）三段，每段都給：進場區、失效點（停損）、第一目標位。

⚠️ 風險提醒
列 2-3 個最重要風險，包含「什麼訊號出現時代表判斷失效」。

💡 結論
給出偏多、偏空或觀望，並說明一個最關鍵理由。
{premium_extra}

最後加上一行：
⚖️ 以上分析僅供參考，不構成投資建議，投資人應獨立評估風險。

【格式規則 - 極重要，必須遵守】
1. 禁止使用任何 Markdown 語法，包括：##、**、__、---、```、- 列表符號
2. 不要用星號 * 做強調
3. 段落之間用空行分隔
4. 每個段落標題用上面指定的 emoji 開頭
5. 用自然中文段落，不要用條列式"""
        else:
            # Free 用戶精簡版（省 token）
            final_prompt = f"""你是「洞察運算」的投資分析工具。請用簡潔的方式分析這檔股票。

【股票資訊】
{context}

【市場情報】
{grounding_text}

請依照以下結構回覆（簡潔版）：

📊 市場快報
用 2-3 句話說明市場動態。

⚠️ 風險提醒
列出 2 個風險因素。

⚖️ 以上分析僅供參考，不構成投資建議。

💬 升級 Pro / Premium 可解鎖 EMA、RSI、MACD、布林帶、Keltner、SMC/ICT 與進出場計畫。

【格式規則】
1. 禁止 Markdown 語法（##、**、```、- 列表）
2. 段落之間用空行分隔
3. 用 emoji 開頭
4. 總字數控制在 300 字以內"""

        def _run_stage2():
            """Stage 2 執行函數（含 503 retry 機制）"""
            last_err = None
            for attempt in range(3):
                try:
                    _client = client2
                    if attempt > 0:
                        # 503 可能是單一 key 負載問題，換 key 重試
                        retry_key = self._get_api_key()
                        if retry_key:
                            _client = genai.Client(api_key=retry_key)
                        print(f"[Gemini] Stage 2 retry #{attempt} with new key")
                        time.sleep(1.5 * attempt)  # backoff
                    return _client.models.generate_content(
                        model=MODEL_FINAL,
                        contents=final_prompt,
                    )
                except Exception as e:
                    last_err = e
                    err_str = str(e)
                    if "503" in err_str or "UNAVAILABLE" in err_str or "overloaded" in err_str.lower():
                        print(f"[Gemini] Stage 2 attempt {attempt+1} got 503, retrying...")
                        continue
                    raise  # 其他錯誤不 retry
            raise last_err  # 全部 retry 失敗

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


            return {
                "success": False,
                "error": f"AI 生成失敗: {type(e).__name__}",
                "analysis": "",
                "grounding_sources": grounding_sources,
            }

    def generate_chat_response(
        self,
        history: List[Dict],
        user_message: str,
        context_str: str = "",
        tier: str = "free",
    ) -> Dict[str, Any]:
        """
        生成對話回應 (Follow-up)
        
        Args:
            history: 對話歷史 [{'role': 'user'|'model', 'parts': [...]}]
            user_message: 當前用戶問題
            context_str: 股票上下文資訊 (從第一次分析結果或 info 取得)
            tier: 用戶等級
        """
        api_key = self._get_api_key()
        if not api_key:
            return {"success": False, "error": "Gemini API 金鑰未設定"}

        try:
            from google import genai
            client = genai.Client(api_key=api_key)
            
            # 轉換 history 格式 (OpenAI-like dict -> Gemini history)
            # 但 google.genai 的 chat.send_message 不需要手動組 history if using chat session
            # 這裡我們用 stateless 方式，手動組 prompt 或者使用 SDK 的 history 物件
            
            # 限制歷史長度以節省 Token
            max_turns = 10 if tier == "premium" else (3 if tier == "pro" else 0)
            if tier == "free":
                 return {"success": False, "error": "Free 用戶不支援 AI 追問功能，請升級 Pro 方案"}
                 
            # 截斷歷史
            active_history = history[- (max_turns * 2):] if history else []
            
            # 建構系統提示
            system_instruction = f"""你是「洞察運算」的投資顧問 Dexter。
你的任務是回答客戶關於股票的後續追問。
回答要簡潔有力，重點清晰。
不要使用 Markdown 標題 (##)，直接分段即可。
上下文資訊：
{context_str}
"""
            
            # 使用 SDK 的 Chat 介面
            chat = client.chats.create(
                model=MODEL_FINAL,
                config={'system_instruction': system_instruction},
                history=active_history
            )
            
            response = chat.send_message(user_message)
            return {
                "success": True,
                "reply": response.text,
            }

        except Exception as e:
            print(f"[Gemini] Chat error: {e}")
            return {"success": False, "error": str(e)}


# Singleton
gemini_service = GeminiService()
