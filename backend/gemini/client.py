"""
backend/gemini/client.py
統一 Gemini API 呼叫入口（Sonnet 撰寫）

規則：
- 禁止在其他地方直接 import genai
- 所有 Gemini 呼叫必須經過此模組
- 超出 rate limit 自動降級（見 FALLBACK_MODEL）
- 失敗最多重試 3 次（2s / 4s / 8s backoff）
- 多把 API Key 輪流使用（round-robin），遵守 Free Tier 限制

⚠️ 使用新版 SDK（google-genai），不是舊版 google-generativeai
"""
import time
import logging
import threading
from typing import Optional

from google import genai
from google.genai import types

from backend.config import (
    AGENT_MODEL_MAP, FALLBACK_MODEL,
    GEMINI_API_KEYS_LIST,
)
from backend.gemini.rate_limiter import RateLimiter
from backend.core.audit_log import log_gemini_call

logger = logging.getLogger(__name__)

# ── Key Pool（多把 API Key 輪流使用）─────────────────────
_key_pool: list[str] = GEMINI_API_KEYS_LIST
_key_index: int = 0
_key_lock = threading.Lock()
_key_usage_counts: dict[str, int] = {}

if _key_pool:
    logger.warning(
        f"[GeminiClient] Key pool initialized: {len(_key_pool)} keys, "
        f"prefixes={[k[:8]+'...' for k in _key_pool]}"
    )
else:
    logger.warning("[GeminiClient] GEMINI_API_KEYS 未設定，呼叫將失敗")


def _get_next_key() -> str:
    """Round-robin 取得下一把 API Key（thread-safe）。"""
    global _key_index
    with _key_lock:
        key = _key_pool[_key_index % len(_key_pool)]
        _key_index += 1
        # 使用量追蹤（masked）
        masked = key[:8] + "..."
        _key_usage_counts[masked] = _key_usage_counts.get(masked, 0) + 1
    return key


def _create_client() -> genai.Client:
    """每次呼叫建立新 Client，使用輪流的 API Key。"""
    api_key = _get_next_key()
    return genai.Client(api_key=api_key)


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

    Returns:
        {
            "status":      "success" | "rate_limited" | "failed",
            "output":      str | None,
            "model_used":  str,
            "duration_ms": int,
            "error":       str | None,
        }
    """
    if not _key_pool:
        return {
            "status": "failed",
            "output": None,
            "model_used": "none",
            "duration_ms": 0,
            "error": "GEMINI_API_KEYS 未設定",
        }

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
            # 每次呼叫建立新 Client（輪流使用不同 key）
            client = _create_client()

            # 新版 SDK 寫法（google-genai>=1.0.0）
            config = types.GenerateContentConfig(temperature=1.0)
            if use_grounding:
                config = types.GenerateContentConfig(
                    temperature=1.0,
                    tools=[types.Tool(google_search=types.GoogleSearch())],
                )

            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=config,
            )
            duration_ms = int((time.time() - start) * 1000)

            _rate_limiter.record_call(model_name)

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

            # API_KEY_INVALID：換下一把 key 重試（不 sleep）
            if "API_KEY_INVALID" in str(e):
                logger.warning(
                    f"[GeminiClient] Key invalid，輪換下一把 key 重試"
                )
                continue

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
    """
    model_name = AGENT_MODEL_MAP.get(agent_name, "gemini-2.5-flash")

    if _rate_limiter.can_call(model_name):
        return model_name

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


def get_key_usage_stats() -> dict:
    """查詢各 API Key 的使用次數（masked）。"""
    with _key_lock:
        return {
            "total_keys": len(_key_pool),
            "current_index": _key_index,
            "usage_counts": dict(_key_usage_counts),
        }


# ── Streaming 版本（Chief Analyst 用）────────────────────
from typing import Generator


def call_gemini_streaming(
    agent_name: str,
    prompt: str,
    use_grounding: bool = False,
    report_id: Optional[str] = None,
) -> Generator[str, None, dict]:
    """
    Streaming 版 Gemini 呼叫，逐段 yield 文字。

    用於 Chief Analyst 報告生成，讓前端透過 SSE 即時顯示。
    最終 return 完整結果 dict（可用 generator.send() 取得）。

    Usage:
        chunks = []
        gen = call_gemini_streaming("chief_analyst", prompt)
        for chunk in gen:
            chunks.append(chunk)
            # 透過 SSE 推給前端
        full_text = "".join(chunks)
    """
    if not _key_pool:
        return

    model_name = _resolve_model(agent_name)
    if model_name is None:
        logger.warning(f"[GeminiClient] {agent_name} streaming: 所有模型達 rate limit")
        return

    start = time.time()
    try:
        client = _create_client()

        config = types.GenerateContentConfig(temperature=1.0)
        if use_grounding:
            config = types.GenerateContentConfig(
                temperature=1.0,
                tools=[types.Tool(google_search=types.GoogleSearch())],
            )

        # Streaming 呼叫
        response_stream = client.models.generate_content_stream(
            model=model_name,
            contents=prompt,
            config=config,
        )

        full_text_parts = []
        for chunk in response_stream:
            if chunk.text:
                full_text_parts.append(chunk.text)
                yield chunk.text

        duration_ms = int((time.time() - start) * 1000)
        _rate_limiter.record_call(model_name)

        log_gemini_call(
            agent_name=agent_name,
            model_name=model_name,
            report_id=report_id,
            status="success",
            duration_ms=duration_ms,
            use_grounding=use_grounding,
        )

        logger.info(
            f"[GeminiClient] {agent_name} streaming 完成: "
            f"{model_name}, {duration_ms}ms, "
            f"{len(full_text_parts)} chunks"
        )

    except Exception as e:
        duration_ms = int((time.time() - start) * 1000)
        logger.error(f"[GeminiClient] {agent_name} streaming 失敗: {e}")
        log_gemini_call(
            agent_name=agent_name,
            model_name=model_name,
            report_id=report_id,
            status="failed",
            error=str(e),
        )
