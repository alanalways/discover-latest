"""
backend/agents/departments/event.py
事件驅動官（Sonnet 撰寫）
use_grounding=True（需要 Google Search 搜尋最新事件）
"""
import json
from datetime import date
from backend.agents.base_agent import BaseAgent


class EventAgent(BaseAgent):

    @property
    def agent_name(self) -> str:
        return "event_agent"

    @property
    def use_grounding(self) -> bool:
        return True  # 需要 Google Search 取得最新財報/事件資訊

    def analyze(
        self,
        symbol: str,
        market: str,
        report_id: str = None,
    ) -> dict:
        """
        執行事件驅動分析（透過 grounding 搜尋最新資訊）。

        Args:
            symbol:    股票代號
            market:    市場
            report_id: 關聯報告 UUID
        """
        result = self.run(
            report_id=report_id,
            symbol=symbol,
            market=market,
            analysis_date=date.today().isoformat(),
            current_year=date.today().year,
        )

        if result["status"] == "success":
            return _parse_json_output(result["output"], result)

        return result


def _parse_json_output(text: str, original_result: dict) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        cleaned = "\n".join(lines[1:-1]) if lines[-1] == "```" else "\n".join(lines[1:])
    try:
        parsed = json.loads(cleaned)
        parsed["_model_used"] = original_result.get("model_used")
        parsed["_duration_ms"] = original_result.get("duration_ms")
        return parsed
    except json.JSONDecodeError:
        return {
            "raw": text,
            "parse_failed": True,
            "_model_used": original_result.get("model_used"),
        }
