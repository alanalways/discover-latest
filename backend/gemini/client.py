"""
backend/gemini/client.py
統一 Gemini API 呼叫入口。

設計重點：
- 支援多把 API key（使用者目前為多個獨立 project）
- round-robin 輪替 key，避免單一 project 先耗盡
- 依 agent 路由模型，支援 fallback
- 支援一般呼叫與 streaming 呼叫
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import date
from typing import Generator, Optional

from google import genai
from google.genai import types

from backend.config import (
    AGENT_MODEL_MAP,
    FALLBACK_MODEL,
    GEMINI_API_KEYS_LIST,
    GEMINI_GROUNDING_ENABLED_MODELS,
    GEMINI_GROUNDING_MODEL,
)
from backend.core.audit_log import log_gemini_call
from backend.gemini.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

_key_pool: list[str] = list(GEMINI_API_KEYS_LIST)
_key_index = 0
_key_lock = threading.Lock()
_key_usage_counts: dict[str, int] = {}
_key_exhausted: dict[int, date] = {}
_client_cache: dict[str, genai.Client] = {}

_rate_limiter = RateLimiter()
_BACKOFF_SECONDS = [1, 2, 4]


def _masked_key(api_key: str) -> str:
    return f"{api_key[:8]}..."


def _get_client(api_key: str) -> genai.Client:
    client = _client_cache.get(api_key)
    if client is None:
        client = genai.Client(api_key=api_key)
        _client_cache[api_key] = client
    return client


def _is_key_exhausted(key_idx: int) -> bool:
    exhausted_on = _key_exhausted.get(key_idx)
    if exhausted_on is None:
        return False
    if exhausted_on < date.today():
        with _key_lock:
            _key_exhausted.pop(key_idx, None)
        return False
    return True


def _mark_key_exhausted(key_idx: int) -> None:
    with _key_lock:
        _key_exhausted[key_idx] = date.today()


def _get_next_key() -> tuple[str, int]:
    global _key_index

    if not _key_pool:
        return "", -1

    with _key_lock:
        total = len(_key_pool)
        start_index = _key_index
        for offset in range(total):
            idx = (start_index + offset) % total
            if _is_key_exhausted(idx):
                continue
            api_key = _key_pool[idx]
            _key_index = (idx + 1) % total
            _key_usage_counts[_masked_key(api_key)] = _key_usage_counts.get(_masked_key(api_key), 0) + 1
            return api_key, idx
    return "", -1


def _resolve_model(agent_name: str, use_grounding: bool) -> Optional[str]:
    preferred = AGENT_MODEL_MAP.get(agent_name, GEMINI_GROUNDING_MODEL if use_grounding else GEMINI_FLASH)

    if use_grounding and preferred not in GEMINI_GROUNDING_ENABLED_MODELS:
        preferred = GEMINI_GROUNDING_MODEL

    model_name = preferred
    checked: set[str] = set()
    while model_name and model_name not in checked:
        checked.add(model_name)
        if _rate_limiter.can_call(model_name):
            return model_name
        model_name = FALLBACK_MODEL.get(model_name)
        if use_grounding and model_name not in GEMINI_GROUNDING_ENABLED_MODELS:
            model_name = GEMINI_GROUNDING_MODEL if model_name else None
    return None


def _build_config(use_grounding: bool) -> types.GenerateContentConfig:
    if use_grounding:
        return types.GenerateContentConfig(
            temperature=0.4,
            tools=[types.Tool(google_search=types.GoogleSearch())],
        )
    return types.GenerateContentConfig(temperature=0.4)


def call_gemini(
    agent_name: str,
    prompt: str,
    use_grounding: bool = False,
    report_id: Optional[str] = None,
) -> dict:
    if not _key_pool:
        return {
            "status": "failed",
            "output": None,
            "model_used": "none",
            "duration_ms": 0,
            "error": "GEMINI_API_KEY(S) 未設定",
        }

    model_name = _resolve_model(agent_name, use_grounding)
    if not model_name:
        return {
            "status": "rate_limited",
            "output": None,
            "model_used": AGENT_MODEL_MAP.get(agent_name, GEMINI_GROUNDING_MODEL),
            "duration_ms": 0,
            "error": "所有 Gemini 模型已達當前安全上限",
        }

    config = _build_config(use_grounding)
    last_error: Optional[str] = None

    for attempt in range(len(_key_pool) + len(_BACKOFF_SECONDS)):
        api_key, key_idx = _get_next_key()
        if not api_key:
            break

        start = time.time()
        try:
            response = _get_client(api_key).models.generate_content(
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
        except Exception as exc:
            last_error = str(exc)
            if "429" in last_error or "RESOURCE_EXHAUSTED" in last_error:
                _mark_key_exhausted(key_idx)
                logger.warning(
                    "[GeminiClient] %s key #%d exhausted, switching project",
                    agent_name,
                    key_idx,
                )
                continue

            retry_index = min(attempt, len(_BACKOFF_SECONDS) - 1)
            time.sleep(_BACKOFF_SECONDS[retry_index])

    log_gemini_call(
        agent_name=agent_name,
        model_name=model_name,
        report_id=report_id,
        status="failed",
        error=last_error,
        use_grounding=use_grounding,
    )
    return {
        "status": "rate_limited" if all(_is_key_exhausted(i) for i in range(len(_key_pool))) else "failed",
        "output": None,
        "model_used": model_name,
        "duration_ms": 0,
        "error": last_error,
    }


def call_gemini_streaming(
    agent_name: str,
    prompt: str,
    use_grounding: bool = False,
    report_id: Optional[str] = None,
) -> Generator[str, None, None]:
    if not _key_pool:
        return

    model_name = _resolve_model(agent_name, use_grounding)
    if not model_name:
        logger.warning("[GeminiClient] %s streaming blocked by rate limit", agent_name)
        return

    config = _build_config(use_grounding)

    # Streaming 也支援多 key 重試（最多嘗試所有 key 數次）
    for attempt in range(len(_key_pool) + len(_BACKOFF_SECONDS)):
        api_key, key_idx = _get_next_key()
        if not api_key:
            break

        start = time.time()
        try:
            response_stream = _get_client(api_key).models.generate_content_stream(
                model=model_name,
                contents=prompt,
                config=config,
            )

            for chunk in response_stream:
                text = getattr(chunk, "text", None)
                if text:
                    yield text

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
            return  # 成功，結束 generator

        except Exception as exc:
            error = str(exc)
            if "429" in error or "RESOURCE_EXHAUSTED" in error:
                _mark_key_exhausted(key_idx)
                logger.warning(
                    "[GeminiClient] %s streaming key #%d exhausted, trying next",
                    agent_name, key_idx,
                )
                continue  # 立即換下一把 key

            retry_index = min(attempt, len(_BACKOFF_SECONDS) - 1)
            logger.warning(
                "[GeminiClient] %s streaming error (attempt %d): %s",
                agent_name, attempt + 1, error,
            )
            time.sleep(_BACKOFF_SECONDS[retry_index])

    log_gemini_call(
        agent_name=agent_name,
        model_name=model_name,
        report_id=report_id,
        status="failed",
        error="streaming failed after all retries",
        use_grounding=use_grounding,
    )


def get_rate_limiter_status() -> dict:
    return _rate_limiter.get_status()


def get_key_usage_stats() -> dict:
    with _key_lock:
        exhausted = sum(1 for idx in range(len(_key_pool)) if _is_key_exhausted(idx))
        return {
            "total_keys": len(_key_pool),
            "current_index": _key_index,
            "exhausted_today": exhausted,
            "usage_counts": dict(_key_usage_counts),
        }
