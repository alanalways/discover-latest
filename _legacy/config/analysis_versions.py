"""
Analysis / prompt / rule version registry.

所有 AI 建議記錄都會寫入這些版本號，方便後續回溯：
- prompt 調整是否真的提升命中率
- 規則修改是否讓系統更穩
- 不同部署版本是否造成表現漂移
"""

PROMPT_ANALYSIS_VERSION = "analysis-prompt-2026-03-13-v1"
RULE_ANALYSIS_VERSION = "analysis-rules-2026-03-13-v1"
SYSTEM_ANALYSIS_VERSION = "analysis-system-2026-03-13-v1"

