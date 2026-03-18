"""
backend/agents/departments/fundamental.py
基本面研究官（Sonnet 撰寫）
use_grounding=False（使用傳入的 financial_data）
"""
import json
from backend.agents.base_agent import BaseAgent


class FundamentalAgent(BaseAgent):

    @property
    def agent_name(self) -> str:
        return "fundamental_agent"

    @property
    def use_grounding(self) -> bool:
        return False

    def analyze(
        self,
        symbol: str,
        market: str,
        financial_data: dict,
        report_id: str = None,
    ) -> dict:
        """
        執行基本面分析。

        Args:
            symbol:         股票代號
            market:         市場
            financial_data: 包含財報數據的字典（EPS、營收、比率等）
            report_id:      關聯報告 UUID
        """
        result = self.run(
            report_id=report_id,
            symbol=symbol,
            market=market,
            financial_data=json.dumps(financial_data, ensure_ascii=False, indent=2),
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
