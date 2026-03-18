"""
backend/agents/base_agent.py
所有 Agent 的抽象基底類別（Sonnet 撰寫）
"""
import time
from abc import ABC, abstractmethod

from backend.gemini.client import call_gemini
from backend.core.audit_log import log_agent_action
from backend.prompts.registry import get_active_prompt


class BaseAgent(ABC):
    """
    所有研究部門 Agent 的基底類別。

    子類別必須實作：
    - agent_name (property)

    子類別可選覆寫：
    - use_grounding (property)：event/macro/sentiment 設為 True
    """

    @property
    @abstractmethod
    def agent_name(self) -> str:
        """Agent 識別名稱，對應 AGENT_MODEL_MAP 的 key。"""
        pass

    @property
    def use_grounding(self) -> bool:
        """是否啟用 Google Search grounding。預設 False。"""
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

        流程：
        1. 取得 prompt template 並填入變數
        2. 呼叫 Gemini（經 client.py 統一管理）
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

        result = call_gemini(
            agent_name=self.agent_name,
            prompt=prompt,
            use_grounding=self.use_grounding,
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
