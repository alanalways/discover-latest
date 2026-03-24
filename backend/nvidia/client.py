"""
backend/nvidia/client.py
NVIDIA NIM API 呼叫入口（OpenAI 相容介面）

規則：
- 所有 NVIDIA NIM 呼叫必須經過此模組
- 模型固定為 moonshotai/kimi-k2.5（config.NVIDIA_MODEL）
- 失敗重試：3 次，backoff 2s/4s/8s
- RPM 超限時 blocking wait（不降級，無其他模型）
- 呼叫結果透過 audit_log 記錄

使用方式：
    from backend.nvidia.client import call_nvidia, call_nvidia_streaming
"""
import time
import logging
from typing import Optional, Generator

from openai import OpenAI

from backend.config import NVIDIA_API_KEY, NVIDIA_BASE_URL, NVIDIA_MODEL
from backend.nvidia.rate_limiter import get_nvidia_rate_limiter
from backend.core.audit_log import log_agent_action

logger = logging.getLogger(__name__)

# ── 重試設定 ─────────────────────────────────────────────
_MAX_RETRIES = 3
_BACKOFF_SECONDS = [2, 4, 8]

# ── 單例 Client（OpenAI SDK 指向 NVIDIA NIM）────────────
_client: OpenAI | None = None


def _get_client() -> OpenAI:
    """取得全局 OpenAI Client 單例（指向 NVIDIA NIM base_url）。"""
    global _client
    if _client is None:
        if not NVIDIA_API_KEY:
            raise RuntimeError(
                "[NvidiaClient] NVIDIA_API_KEY 未設定，請在 .env 加入 NVIDIA_API_KEY"
            )
        _client = OpenAI(
            base_url=NVIDIA_BASE_URL,
            api_key=NVIDIA_API_KEY,
        )
        logger.info(
            f"[NvidiaClient] Client 初始化完成，"
            f"base_url={NVIDIA_BASE_URL}, model={NVIDIA_MODEL}"
        )
    return _client


def call_nvidia(
    agent_name: str,
    prompt: str,
    report_id: Optional[str] = None,
    temperature: float = 0.6,
    max_tokens: int = 4096,
) -> dict:
    """
    統一 NVIDIA NIM 呼叫入口。

    Args:
        agent_name:  Agent 識別名稱（用於 audit_log）
        prompt:      完整 prompt 文字
        report_id:   關聯報告 ID（可選，用於 audit_log）
        temperature: 生成溫度（預設 0.6，kimi-k2.5 推薦範圍）
        max_tokens:  最大輸出 token 數

    Returns:
        {
            "status":      "success" | "rate_limited" | "failed",
            "output":      str | None,
            "model_used":  str,
            "duration_ms": int,
            "error":       str | None,
        }
    """
    limiter = get_nvidia_rate_limiter()

    # Rate limit：超限時 blocking wait（預佔位，防止 TOCTOU race）
    limiter.wait_if_needed()

    client = _get_client()
    last_error: Optional[str] = None

    _MAX_429_RETRIES = 5  # 429 最多重試 5 次，避免無限迴圈
    retries_429 = 0

    for attempt in range(_MAX_RETRIES):
        start = time.time()
        try:
            response = client.chat.completions.create(
                model=NVIDIA_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            duration_ms = int((time.time() - start) * 1000)
            output_text = response.choices[0].message.content or ""

            # record_call() 已是 no-op（wait_if_needed 預佔位）
            limiter.record_call()

            log_agent_action(
                agent_name=agent_name,
                report_id=report_id,
                status="success",
                metadata={
                    "model": NVIDIA_MODEL,
                    "duration_ms": duration_ms,
                    "provider": "nvidia",
                },
            )

            logger.info(
                f"[NvidiaClient] {agent_name} 完成: "
                f"{duration_ms}ms, {len(output_text)} chars"
            )

            return {
                "status": "success",
                "output": output_text,
                "model_used": NVIDIA_MODEL,
                "duration_ms": duration_ms,
            }

        except Exception as e:
            last_error = str(e)
            duration_ms = int((time.time() - start) * 1000)
            err_str = str(e)
            logger.warning(
                f"[NvidiaClient] {agent_name} 第 {attempt + 1} 次失敗: {e}"
            )

            # ── NVIDIA 429：有限次重試，避免無限迴圈 ──
            if "429" in err_str or "Too Many Requests" in err_str:
                retries_429 += 1
                if retries_429 >= _MAX_429_RETRIES:
                    logger.error(
                        f"[NvidiaClient] {agent_name} 429 重試已達上限 "
                        f"({_MAX_429_RETRIES} 次)，放棄"
                    )
                    break
                logger.warning(
                    f"[NvidiaClient] {agent_name} NVIDIA 429 "
                    f"({retries_429}/{_MAX_429_RETRIES})，"
                    f"等待 rate limit 清空後重試..."
                )
                time.sleep(2.0)
                limiter.wait_if_needed()
                continue

            if attempt < _MAX_RETRIES - 1:
                sleep_time = _BACKOFF_SECONDS[attempt]
                logger.info(f"[NvidiaClient] {sleep_time}s 後重試...")
                time.sleep(sleep_time)

    # ── 所有重試均失敗 ───────────────────────────────────
    final_status = "rate_limited" if retries_429 >= _MAX_429_RETRIES else "failed"

    log_agent_action(
        agent_name=agent_name,
        report_id=report_id,
        status=final_status,
        metadata={
            "model": NVIDIA_MODEL,
            "error": last_error,
            "provider": "nvidia",
            "retries_429": retries_429,
        },
    )

    return {
        "status": final_status,
        "output": None,
        "model_used": NVIDIA_MODEL,
        "duration_ms": 0,
        "error": last_error,
    }


def call_nvidia_streaming(
    agent_name: str,
    prompt: str,
    report_id: Optional[str] = None,
    temperature: float = 0.6,
    max_tokens: int = 8192,
) -> Generator[str, None, None]:
    """
    Streaming 版 NVIDIA NIM 呼叫，逐段 yield 文字。

    用於 Chief Analyst 報告生成，讓前端透過 SSE 即時顯示。

    Usage:
        chunks = []
        for chunk in call_nvidia_streaming("chief_analyst", prompt):
            chunks.append(chunk)
            # 透過 SSE 推給前端
        full_text = "".join(chunks)
    """
    limiter = get_nvidia_rate_limiter()
    limiter.wait_if_needed()

    client = _get_client()
    start = time.time()

    try:
        stream = client.chat.completions.create(
            model=NVIDIA_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        )

        chunk_count = 0
        for chunk in stream:
            delta = chunk.choices[0].delta.content if chunk.choices else None
            if delta:
                chunk_count += 1
                yield delta

        duration_ms = int((time.time() - start) * 1000)
        limiter.record_call()

        log_agent_action(
            agent_name=agent_name,
            report_id=report_id,
            status="success",
            metadata={
                "model": NVIDIA_MODEL,
                "duration_ms": duration_ms,
                "chunks": chunk_count,
                "provider": "nvidia",
                "streaming": True,
            },
        )

        logger.info(
            f"[NvidiaClient] {agent_name} streaming 完成: "
            f"{duration_ms}ms, {chunk_count} chunks"
        )

    except Exception as e:
        duration_ms = int((time.time() - start) * 1000)
        logger.error(f"[NvidiaClient] {agent_name} streaming 失敗: {e}")
        log_agent_action(
            agent_name=agent_name,
            report_id=report_id,
            status="failed",
            metadata={
                "model": NVIDIA_MODEL,
                "error": str(e),
                "provider": "nvidia",
                "streaming": True,
            },
        )
