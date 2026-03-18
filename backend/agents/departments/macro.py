"""
backend/agents/departments/macro.py
宏觀策略官（Sonnet 撰寫）
use_grounding=True（需要 Google Search 取得最新宏觀數據）
"""
import json
from datetime import date
from backend.agents.base_agent import BaseAgent


class MacroAgent(BaseAgent):

    @property
    def agent_name(self) -> str:
        return "macro_agent"

    @property
    def use_grounding(self) -> bool:
        return True  # 需要 Google Search 取得美股/VIX/Fed/匯率最新數據

    def analyze(
        self,
        symbol: str,
        market: str,
        industry: str = "科技",
        report_id: str = None,
    ) -> dict:
        """
        執行宏觀策略分析（透過 grounding 搜尋最新宏觀數據）。

        Args:
            symbol:    股票代號
            market:    市場
            industry:  所屬產業（用於板塊輪動分析）
            report_id: 關聯報告 UUID
        """
        result = self.run(
            report_id=report_id,
            symbol=symbol,
            market=market,
            industry=industry,
            analysis_date=date.today().isoformat(),
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
