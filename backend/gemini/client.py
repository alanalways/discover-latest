"""
backend/gemini/client.py
統一 Gemini API 呼叫入口（Sonnet 撰寫）

規則：
- 禁止在其他地方直接 import google.generativeai
- 所有 Gemini 呼叫必須經過此模組
- 超出 rate limit 自動降級（見 FALLBACK_MODEL）
- 失敗最多重試 3 次（2s / 4s / 8s backoff）
"""
import os
import time
import logging
from typing import Optional

import google.generativeai as genai

from backend.config import AGENT_MODEL_MAP, FALLBACK_MODEL, GEMINI_API_KEY
from backend.gemini.rate_limiter import RateLimiter
from backend.core.audit_log import log_gemini_call

logger = logging.getLogger(__name__)

# ── 初始化 Gemini SDK ────────────────────────────────────
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
else:
    logger.warning("[GeminiClient] GEMINI_API_KEY 未設定，呼叫將失敗")

# ── Rate Limiter 單例 ────────────────────────────────────
_rate_limiter = RateLimiter()

# ── 重試設定 ─────────────────────────────────────────────
_MAX_RETRIES = 3
_BACKOFF_SECONDS = [2, 4, 8]


def call_gemini(
    agent_name: str,
    prompt: str,
    use_grounding: bool = False,
    report_id: Optional[str] = None,
) -> dict:
    """
    統一 Gemini 呼叫入口。

    Args:
        agent_name:    呼叫者名稱（對應 AGENT_MODEL_MAP key）
        prompt:        傳入 Gemini 的完整 prompt
        use_grounding: 是否啟用 Google Search grounding
        report_id:     關聯的報告 UUID（可選，用於 audit log）

    Returns:
        {
            "status":      "success" | "rate_limited" | "failed",
            "output":      str | None,
            "model_used":  str,
            "duration_ms": int,
            "error":       str | None,   # 僅 failed 時存在
        }
    """
    # ── 決定使用模型 ─────────────────────────────────────
    model_name = _resolve_model(agent_name)
    if model_name is None:
        logger.warning(f"[GeminiClient] {agent_name} 所有模型均達 rate limit")
        return {
            "status": "rate_limited",
            "output": None,
            "model_used": AGENT_MODEL_MAP.get(agent_name, "unknown"),
            "duration_ms": 0,
        }

    # ── 重試迴圈 ─────────────────────────────────────────
    last_error: Optional[str] = None
    for attempt in range(_MAX_RETRIES):
        start = time.time()
        try:
            tools = [{"google_search": {}}] if use_grounding else None
            model = genai.GenerativeModel(
                model_name,
                generation_config={"temperature": 1.0},  # Gemini 3 建議保持 1.0
                tools=tools,
            )
            response = model.generate_content(prompt)
            duration_ms = int((time.time() - start) * 1000)

            # 記錄成功的呼叫到 rate limiter
            _rate_limiter.record_call(model_name)

            # 寫入 audit log
            log_gemini_call(
                agent_name=agent_name,
                model_name=model_name,
                report_id=report_id,
                status="success",
                duration_ms=duration_ms,
                use_grounding=use_grounding,
            )

            return {
                "status": "success",
                "output": response.text,
                "model_used": model_name,
                "duration_ms": duration_ms,
            }

        except Exception as e:
            last_error = str(e)
            duration_ms = int((time.time() - start) * 1000)
            logger.warning(
                f"[GeminiClient] {agent_name} 第 {attempt + 1} 次失敗: {e}"
            )

            # 429 Rate Limit 錯誤：不重試，直接降級
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                logger.warning(
                    f"[GeminiClient] {model_name} 收到 429，嘗試降級"
                )
                fallback = FALLBACK_MODEL.get(model_name)
                if fallback and _rate_limiter.can_call(fallback):
                    model_name = fallback
                    logger.info(f"[GeminiClient] 降級至 {model_name}")
                    continue
                else:
                    break

            # 其他錯誤：backoff 後重試
            if attempt < _MAX_RETRIES - 1:
                sleep_time = _BACKOFF_SECONDS[attempt]
                logger.info(f"[GeminiClient] {sleep_time}s 後重試...")
                time.sleep(sleep_time)

    # ── 所有重試均失敗 ───────────────────────────────────
    log_gemini_call(
        agent_name=agent_name,
        model_name=model_name,
        report_id=report_id,
        status="failed",
        error=last_error,
    )

    return {
        "status": "failed",
        "output": None,
        "model_used": model_name,
        "duration_ms": 0,
        "error": last_error,
    }


def _resolve_model(agent_name: str) -> Optional[str]:
    """
    決定使用哪個模型。
    若主要模型達到 rate limit，沿 FALLBACK_MODEL 鏈往下找。
    找不到可用模型回傳 None。
    """
    model_name = AGENT_MODEL_MAP.get(agent_name, "gemini-2.5-flash")

    # 嘗試主要模型
    if _rate_limiter.can_call(model_name):
        return model_name

    # 沿降級鏈往下找
    current = model_name
    while current in FALLBACK_MODEL:
        fallback = FALLBACK_MODEL[current]
        if _rate_limiter.can_call(fallback):
            logger.info(
                f"[GeminiClient] {agent_name} 主模型 {model_name} 達限，"
                f"降級至 {fallback}"
            )
            return fallback
        current = fallback

    return None


def get_rate_limiter_status() -> dict:
    """供 cost_monitor 查詢目前 rate limit 使用狀況。"""
    return _rate_limiter.get_status()
