"""
backend/gemini/client.py
統一 Gemini API 呼叫入口（Sonnet 撰寫）

規則：
- 禁止在其他地方直接 import genai
- 所有 Gemini 呼叫必須經過此模組（僅限 Batch Search Grounding 用途）
- 無降級機制：Gemini 只做一件事（batch_grounding）
- 多把 API Key 輪流使用（round-robin），每把 key 各自有獨立 RPD 配額
- 收到 429 時：標記該 key 當日耗盡，立即換下一把 key 重試
- 所有 key 都耗盡才回傳 rate_limited

⚠️ 使用新版 SDK（google-genai），不是舊版 google-generativeai

配額計算（以 7 把 key 為例）：
  每把 key：20 RPD，5 RPM
  Pool 合計：7 × 20 = 140 RPD / 天，7 × 5 = 35 RPM（輪換）
"""
import time
import logging
import threading
from datetime import date
from typing import Optional

from google import genai
from google.genai import types

from backend.config import (
    GEMINI_GROUNDING_MODEL,
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

# ── Per-key 每日耗盡追蹤（429 時標記）───────────────────
# {key_index: date_when_exhausted}
_key_exhausted: dict[int, date] = {}

if _key_pool:
    logger.warning(
        f"[GeminiClient] Key pool initialized: {len(_key_pool)} keys, "
        f"prefixes={[k[:8]+'...' for k in _key_pool]}, "
        f"daily_capacity={len(_key_pool) * 20} RPD"
    )
else:
    logger.warning("[GeminiClient] GEMINI_API_KEYS 未設定，呼叫將失敗")


def _is_key_exhausted(key_idx: int) -> bool:
    """
    檢查指定 key 是否當日耗盡（429 標記，過了今天自動重置）。
    """
    exhausted_date = _key_exhausted.get(key_idx)
    if exhausted_date is None:
        return False
    if exhausted_date < date.today():
        # 新的一天，清除耗盡標記
        with _key_lock:
            _key_exhausted.pop(key_idx, None)
        return False
    return True


def _mark_key_exhausted(key_idx: int) -> None:
    """標記指定 key 當日 RPD 耗盡（收到 429 時呼叫）。"""
    with _key_lock:
        _key_exhausted[key_idx] = date.today()
        exhausted_count = sum(
            1 for i, d in _key_exhausted.items()
            if d == date.today()
        )
        remaining = len(_key_pool) - exhausted_count
        logger.warning(
            f"[GeminiClient] Key #{key_idx} 當日 RPD 耗盡，"
            f"剩餘可用 key: {remaining}/{len(_key_pool)}"
        )


def _get_key_for_attempt(attempt: int) -> tuple[str, int]:
    """
    取得第 attempt 次嘗試應使用的 key（跳過已耗盡的）。
    Returns: (api_key, key_index)，若全部耗盡則 return ("", -1)
    """
    global _key_index
    with _key_lock:
        n = len(_key_pool)
        for offset in range(n):
            idx = (_key_index + attempt + offset) % n
            if not _is_key_exhausted(idx):
                key = _key_pool[idx]
                masked = key[:8] + "..."
                _key_usage_counts[masked] = _key_usage_counts.get(masked, 0) + 1
                return (key, idx)
    return ("", -1)  # 所有 key 都耗盡


# ── Rate Limiter 單例 ────────────────────────────────────
_rate_limiter = RateLimiter()

# ── 重試設定 ─────────────────────────────────────────────
_BACKOFF_SECONDS = [1, 2, 4]  # 非 429 錯誤的 backoff


def call_gemini(
    agent_name: str,
    prompt: str,
    use_grounding: bool = False,
    report_id: Optional[str] = None,
) -> dict:
    """
    統一 Gemini 呼叫入口。

    Key 輪換策略：
    - 正常：round-robin 輪換
    - 429：立即標記該 key 耗盡 → 換下一把 key → 繼續重試
    - 全部耗盡：回傳 rate_limited

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
    model_name = _resolve_model()
    if model_name is None:
        logger.warning(f"[GeminiClient] {agent_name} 所有 Gemini key 當日 RPD 均耗盡")
        return {
            "status": "rate_limited",
            "output": None,
            "model_used": GEMINI_GROUNDING_MODEL,
            "duration_ms": 0,
        }

    # ── 主迴圈：每次嘗試用不同的 key ─────────────────────
    # 最多嘗試 min(key數量, key數量+2次non-429重試) 次
    last_error: Optional[str] = None
    non_429_attempts = 0
    _MAX_NON_429_RETRIES = 2

    for attempt in range(len(_key_pool) + _MAX_NON_429_RETRIES):
        api_key, key_idx = _get_key_for_attempt(attempt)
        if not api_key:
            logger.warning(f"[GeminiClient] {agent_name} 所有 key 已耗盡，放棄")
            break

        start = time.time()
        try:
            client = genai.Client(api_key=api_key)

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

            logger.info(
                f"[GeminiClient] {agent_name} 成功（key #{key_idx}）: "
                f"{model_name}, {duration_ms}ms"
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
            err_str = str(e)

            # ── 429 / RESOURCE_EXHAUSTED：換下一把 key ───
            if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                _mark_key_exhausted(key_idx)
                logger.warning(
                    f"[GeminiClient] {agent_name} key #{key_idx} 429，"
                    f"換下一把 key 繼續..."
                )
                continue  # 不 sleep，立即換 key 重試

            # ── API_KEY_INVALID：換下一把 key ─────────────
            if "API_KEY_INVALID" in err_str:
                _mark_key_exhausted(key_idx)
                logger.warning(f"[GeminiClient] Key #{key_idx} 無效，換下一把")
                continue

            # ── 其他錯誤：短暫 backoff 後以同一把 key 重試 ─
            logger.warning(
                f"[GeminiClient] {agent_name} 第 {attempt + 1} 次失敗: {e}"
            )
            non_429_attempts += 1
            if non_429_attempts <= _MAX_NON_429_RETRIES:
                sleep_time = _BACKOFF_SECONDS[min(non_429_attempts - 1, len(_BACKOFF_SECONDS) - 1)]
                logger.info(f"[GeminiClient] {sleep_time}s 後重試...")
                time.sleep(sleep_time)
            else:
                break  # 非 429 錯誤超過重試上限

    # ── 所有嘗試均失敗 ───────────────────────────────────
    log_gemini_call(
        agent_name=agent_name,
        model_name=model_name,
        report_id=report_id,
        status="failed",
        error=last_error,
    )

    # 判斷是 rate_limited 還是 failed
    all_exhausted = all(_is_key_exhausted(i) for i in range(len(_key_pool)))
    status = "rate_limited" if all_exhausted else "failed"

    return {
        "status": status,
        "output": None,
        "model_used": model_name,
        "duration_ms": 0,
        "error": last_error,
    }


def _resolve_model() -> Optional[str]:
    """
    決定使用 Gemini 模型（固定為 GEMINI_GROUNDING_MODEL）。
    若所有 key 的 RPD 都耗盡則回傳 None。
    """
    # 先檢查是否有任何 key 尚未耗盡
    for i in range(len(_key_pool)):
        if not _is_key_exhausted(i):
            # 至少有一把 key 可用，再確認 rate limiter 本地追蹤
            if _rate_limiter.can_call(GEMINI_GROUNDING_MODEL):
                return GEMINI_GROUNDING_MODEL
            # rate limiter 認為超限（可能計算保守），但 API 實際可能可用
            # 仍然回傳 model，讓 API 決定（429 時會換 key）
            return GEMINI_GROUNDING_MODEL
    return None  # 所有 key 都被 429 標記


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

    model_name = _resolve_model()
    if model_name is None:
        logger.warning(f"[GeminiClient] {agent_name} streaming: Gemini RPD 已耗盡")
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
