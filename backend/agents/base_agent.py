"""
backend/agents/base_agent.py
所有 Agent 的抽象基底類別（Sonnet 撰寫）

Provider 路由規則（來自 config.AGENT_PROVIDER_MAP）：
- "gemini"  → call_gemini()（僅 batch_grounding Agent 使用）
- "nvidia"  → call_nvidia()（所有分析 Agent 使用，12 個）
"""
import time
from abc import ABC, abstractmethod

from backend.config import AGENT_PROVIDER_MAP
from backend.core.audit_log import log_agent_action
from backend.prompts.registry import get_active_prompt


class BaseAgent(ABC):
    """
    所有研究部門 Agent 的基底類別。

    子類別必須實作：
    - agent_name (property)

    子類別可選覆寫：
    - use_grounding (property)：現已廢棄，保留相容性，一律回傳 False
    """

    @property
    @abstractmethod
    def agent_name(self) -> str:
        """Agent 識別名稱，對應 AGENT_PROVIDER_MAP 的 key。"""
        pass

    @property
    def use_grounding(self) -> bool:
        """廢棄：grounding 現由 BatchGroundingAgent 統一處理。"""
        return False

    def get_prompt(self, **kwargs) -> str:
        """
        取得填入變數後的完整 prompt。
        從 registry 取得 template，再 format 填入 kwargs。
        """
        template = get_active_prompt(self.agent_name)
        try:
            return template.format(**kwargs)
        except KeyError as e:
            raise ValueError(
                f"[{self.agent_name}] Prompt template 缺少變數: {e}. "
                f"提供的變數: {list(kwargs.keys())}"
            )

    def run(self, report_id: str = None, **kwargs) -> dict:
        """
        執行 Agent 分析。

        根據 AGENT_PROVIDER_MAP 自動路由至：
        - NVIDIA NIM（call_nvidia）：所有分析 Agent（12 個）
        - Gemini（call_gemini）：僅 batch_grounding

        流程：
        1. 取得 prompt template 並填入變數
        2. 根據 provider 路由呼叫對應 API
        3. 記錄執行結果到 audit log
        4. 回傳結果 dict

        Returns:
            {
                "status":      "success" | "rate_limited" | "failed",
                "output":      str | None,
                "model_used":  str,
                "duration_ms": int,
            }
        """
        start = time.time()

        # ── 建立 Prompt ───────────────────────────────────
        try:
            prompt = self.get_prompt(**kwargs)
        except ValueError as e:
            log_agent_action(
                self.agent_name, report_id, "failed",
                action="prompt_build", error=str(e)
            )
            return {
                "status": "failed",
                "output": None,
                "model_used": "none",
                "duration_ms": 0,
                "error": str(e),
            }

        # ── Provider 路由 ────────────────────────────────
        provider = AGENT_PROVIDER_MAP.get(self.agent_name, "nvidia")

        if provider == "gemini":
            from backend.gemini.client import call_gemini
            result = call_gemini(
                agent_name=self.agent_name,
                prompt=prompt,
                use_grounding=True,  # Gemini 呼叫永遠帶 grounding
                report_id=report_id,
            )
        else:
            # 預設 nvidia（所有分析 Agent）
            from backend.nvidia.client import call_nvidia
            result = call_nvidia(
                agent_name=self.agent_name,
                prompt=prompt,
                report_id=report_id,
            )

        duration_ms = int((time.time() - start) * 1000)

        log_agent_action(
            agent_name=self.agent_name,
            report_id=report_id,
            status=result["status"],
            action="run",
            duration_ms=duration_ms,
            error=result.get("error"),
        )

        return result
