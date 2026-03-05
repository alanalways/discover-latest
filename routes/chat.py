"""AI Chat API route — 直接用 Gemini with Google Search grounding。"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

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
        api_key = gemini_service._get_api_key()
    except Exception:
        api_key = None

    if not api_key:
        raise HTTPException(status_code=500, detail="Gemini API key 未設定")

    # 建立 system prompt
    system_prompt = (
        "你是 DiscoverLatest AI 投資研究助手。\n"
        "1. 請用繁體中文回答。\n"
        "2. 請用 Google Search 搜尋最新資訊後回答。\n"
        "3. 回答要專業、有條理，適度使用 emoji 增加可讀性。\n"
        "4. 如果用戶問的是個股，請包含：最新價格、近期新聞、基本面摘要、風險提示。\n"
        "5. 回答長度 200-400 字。\n"
        "6. 不要使用 markdown 格式。\n"
    )

    user_prompt = message
    if symbol:
        user_prompt = f"[股票代號: {symbol}] {message}"

    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=0.4,
                max_output_tokens=600,
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
