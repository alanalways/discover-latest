"""
backend/agents/departments/chips.py
籌碼分析官（Sonnet 撰寫）
use_grounding=False（使用傳入的 chips_data）
"""
import json
from backend.agents.base_agent import BaseAgent


class ChipsAgent(BaseAgent):

    @property
    def agent_name(self) -> str:
        return "chips_agent"

    @property
    def use_grounding(self) -> bool:
        return False

    def analyze(
        self,
        symbol: str,
        market: str,
        chips_data: dict,
        report_id: str = None,
    ) -> dict:
        """
        執行籌碼分析。

        Args:
            symbol:     股票代號
            market:     市場
            chips_data: 包含三大法人、融資融券、持股分布的字典
            report_id:  關聯報告 UUID
        """
        result = self.run(
            report_id=report_id,
            symbol=symbol,
            market=market,
            chips_data=json.dumps(chips_data, ensure_ascii=False, indent=2),
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
