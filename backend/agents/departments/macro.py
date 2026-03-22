"""
backend/agents/departments/macro.py
宏觀策略官（Sonnet 撰寫）

v2.0：不再自行呼叫 Gemini grounding。
      接收 pipeline 傳入的 grounding_data（由 BatchGroundingAgent 預取）。
      分析工作交由 NVIDIA kimi-k2.5 執行。
"""
import json
from datetime import date
from backend.agents.base_agent import BaseAgent


class MacroAgent(BaseAgent):

    @property
    def agent_name(self) -> str:
        return "macro_agent"

    # use_grounding 廢棄，不覆寫（BaseAgent 預設回傳 False）

    def analyze(
        self,
        symbol: str,
        market: str,
        grounding_data: dict = None,
        industry: str = "科技",
        report_id: str = None,
    ) -> dict:
        """
        執行宏觀策略分析。

        Args:
            symbol:         股票代號
            market:         市場
            grounding_data: BatchGroundingAgent.fetch_all() 回傳的 macro_data 部分
            industry:       所屬產業（用於板塊輪動分析，可從基本面資料推斷）
            report_id:      關聯報告 UUID
        """
        macro_data = (grounding_data or {})
        result = self.run(
            report_id=report_id,
            symbol=symbol,
            market=market,
            macro_data=json.dumps(macro_data, ensure_ascii=False),
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
        cleaned = "\n".join(
            l for l in lines if not l.startswith("```")
        ).strip()
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
