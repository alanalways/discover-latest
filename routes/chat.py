"""AI Chat API route — 直接用 Gemini with Google Search grounding。"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from config.models import MODEL_GROUNDING

router = APIRouter()
logger = logging.getLogger(__name__)


class ChatRequest(BaseModel):
    message: str
    symbol: str = ""


def _extract_user(auth_header: str) -> Optional[dict]:
    if not auth_header or not auth_header.startswith("Bearer "):
        return None
    token = auth_header[7:]
    try:
        from services.auth_service import auth_service
        return auth_service.verify_session(token)
    except Exception:
        return None


@router.post("/chat/ask")
async def chat_ask(req: ChatRequest, request: Request):
    """用 Gemini + Google Search grounding 回答用戶的投資問題。"""
    auth_header = request.headers.get("Authorization", "")
    user = _extract_user(auth_header)
    if not user:
        raise HTTPException(status_code=401, detail="請先登入")

    message = (req.message or "").strip()
    if not message:
        raise HTTPException(status_code=400, detail="請輸入問題")

    symbol = (req.symbol or "").strip().upper()

    try:
        from google import genai
        from google.genai import types
    except ImportError:
        raise HTTPException(status_code=500, detail="google-genai 套件未安裝")

    try:
        from services.gemini_service import gemini_service
        api_key = gemini_service.get_api_key()
    except Exception:
        api_key = None

    if not api_key:
        raise HTTPException(status_code=500, detail="Gemini API key 未設定")

    # 建立 system prompt
    system_prompt = (
        "你是 DiscoverLatest 的首席投資研究員，擁有 20 年市場實戰經驗。\n"
        "你的角色不是迴避問題的客服，而是一位敢於給出觀點的專業分析師。\n\n"
        "核心原則：\n"
        "1. 請用繁體中文回答，語氣像資深分析師跟客戶對話，自信、直接、有觀點。\n"
        "2. 用 Google Search 搜尋最新資訊，確保數據即時。\n"
        "3. 用戶問「會漲嗎」「該買嗎」「怎麼看」→ 你必須給出明確的多空判斷和操作建議。\n"
        "   例如：「短線偏多，建議回測 XX 元附近可分批佈局」或「目前估值偏高，建議觀望」。\n"
        "4. 個股分析請包含：即時價格、技術面位階（支撐/壓力）、基本面亮點或隱憂、\n"
        "   法人動向或籌碼面、明確的操作建議（買/賣/觀望 + 理由）。\n"
        "5. 每次回答結尾附上一句風險提示（例如「以上為個人研究觀點，非投資建議，請自行評估風險」），\n"
        "   但不要讓免責聲明影響你在正文中給出專業判斷。\n"
        "6. 回答可以詳盡完整，結構清晰，適度用 emoji 標記重點。\n"
        "7. 格式規則（非常重要）：\n"
        "   - 嚴禁使用任何 markdown：不要 #、##、###、*、**、***、- 列表。\n"
        "   - 段落標題用 emoji 開頭，例如「📊 技術面位階」「💡 操作建議」。\n"
        "   - 列點用「・」符號，不要用 - 或 *。\n"
        "   - 用空行分段，保持乾淨易讀。\n"
    )

    user_prompt = message
    if symbol:
        user_prompt = f"[股票代號: {symbol}] {message}"

    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=MODEL_GROUNDING,
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=0.5,
                max_output_tokens=3000,
                tools=[types.Tool(google_search=types.GoogleSearch())],
            ),
        )

        text = (getattr(response, "text", "") or "").strip()

        # 擷取 grounding sources
        sources = []
        try:
            candidates = getattr(response, "candidates", None) or []
            if candidates:
                gm = getattr(candidates[0], "grounding_metadata", None)
                chunks = getattr(gm, "grounding_chunks", None) if gm else None
                if chunks:
                    for chunk in chunks[:5]:
                        web = getattr(chunk, "web", None)
                        if web:
                            sources.append({
                                "title": getattr(web, "title", "") or "",
                                "uri": getattr(web, "uri", "") or "",
                            })
        except Exception:
            pass

        return {
            "answer": text or "抱歉，AI 無法回答這個問題，請換個方式提問。",
            "sources": sources,
            "symbol": symbol,
        }

    except Exception as e:
        logger.warning("[Chat] Gemini grounding failed: %s", e, exc_info=True)
        return {
            "answer": f"AI 回應失敗：{type(e).__name__}",
            "sources": [],
            "symbol": symbol,
        }
