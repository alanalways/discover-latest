"""
backend/agents/departments/technical.py
技術分析官（Sonnet 撰寫）
use_grounding=False（使用傳入的 price_data）
"""
import json
from backend.agents.base_agent import BaseAgent


class TechnicalAgent(BaseAgent):

    @property
    def agent_name(self) -> str:
        return "technical_agent"

    @property
    def use_grounding(self) -> bool:
        return False  # 使用傳入的 price_data，不需 Google Search

    def analyze(
        self,
        symbol: str,
        market: str,
        price_data: dict,
        report_id: str = None,
    ) -> dict:
        """
        執行技術面分析。

        Args:
            symbol:     股票代號（如 "2330"）
            market:     市場（如 "TW" 或 "US"）
            price_data: 包含 OHLCV、指標數值的字典
            report_id:  關聯報告 UUID

        Returns:
            解析後的技術面 JSON dict，或含 parse_failed 的原始文字
        """
        result = self.run(
            report_id=report_id,
            symbol=symbol,
            market=market,
            price_data=json.dumps(price_data, ensure_ascii=False, indent=2),
        )

        if result["status"] == "success":
            return _parse_json_output(result["output"], result)

        return result


def _parse_json_output(text: str, original_result: dict) -> dict:
    """嘗試解析 JSON 輸出，失敗時回傳 raw。"""
    # 清除 markdown code block 包裝
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
