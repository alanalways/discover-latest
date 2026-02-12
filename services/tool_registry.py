"""
Tool Registry — Dexter 工具註冊中心
映射現有 adapter/service 為 Dexter 可呼叫的工具
"""
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta


class Tool:
    """單一工具描述"""
    def __init__(self, name: str, description: str, adapter, methods: Dict[str, str]):
        self.name = name
        self.description = description
        self.adapter = adapter
        self.methods = methods  # {能力名 → 方法名}


class ToolRegistry:
    """工具註冊與選擇"""

    def __init__(self):
        self._tools: Dict[str, Tool] = {}
        self._initialized = False

    def _lazy_init(self):
        if self._initialized:
            return
        self._initialized = True
        try:
            from adapters.finmind_adapter import finmind_adapter
            self._tools["finmind"] = Tool(
                name="finmind",
                description="台股歷史價格、財報、籌碼、營收、PER/PBR、股利",
                adapter=finmind_adapter,
                methods={
                    "tw_price": "get_tw_stock_price_sync",
                    "tw_info": "get_tw_stock_info_sync",
                    "tw_institutional": "get_tw_institutional_sync",
                    "tw_margin": "get_tw_margin_sync",
                    "tw_revenue": "get_tw_revenue_sync",
                    "tw_per_pbr": "get_tw_per_pbr_sync",
                    "tw_financial": "get_tw_financial_statements_sync",
                    "tw_dividend": "get_tw_dividend_sync",
                    "us_price": "get_us_stock_price",
                    "us_info": "get_us_stock_info",
                    "search_tw": "search_tw_stocks_sync",
                },
            )
        except Exception:
            pass

        # 非 FinMind 資料來源已移除

        try:
            from services.gemini_service import gemini_service
            self._tools["gemini"] = Tool(
                name="gemini",
                description="LLM 推理、綜合分析",
                adapter=gemini_service,
                methods={
                    "analyze": "generate_analysis",
                },
            )
        except Exception:
            pass

    def get_tool(self, name: str) -> Optional[Tool]:
        self._lazy_init()
        return self._tools.get(name)

    def list_tools(self) -> List[str]:
        self._lazy_init()
        return list(self._tools.keys())

    def select_tools(self, symbol: str, query_type: str = "analysis") -> List[str]:
        """智能工具選擇"""
        self._lazy_init()
        tools = []

        if query_type == "analysis":
            if "finmind" in self._tools:
                tools.append("finmind")
            if "gemini" in self._tools:
                tools.append("gemini")
        elif query_type == "market":
            if "finmind" in self._tools:
                tools.append("finmind")
        elif query_type == "backtest":
            if "finmind" in self._tools:
                tools.append("finmind")

        return tools

    def call_tool(self, tool_name: str, method_key: str, **kwargs) -> Any:
        """呼叫指定工具的方法"""
        tool = self.get_tool(tool_name)
        if not tool:
            return {"error": f"Tool '{tool_name}' not found"}
        method_name = tool.methods.get(method_key)
        if not method_name:
            return {"error": f"Method '{method_key}' not found in tool '{tool_name}'"}
        fn = getattr(tool.adapter, method_name, None)
        if not fn:
            return {"error": f"Adapter method '{method_name}' not found"}
        try:
            return fn(**kwargs)
        except Exception as e:
            return {"error": f"{tool_name}.{method_key}: {type(e).__name__}: {e}"}


tool_registry = ToolRegistry()
