"""
DiscoverLatest 洞察運算 - 設定模組
"""
from .models import MODEL_GROUNDING, MODEL_FINAL, get_model_list, validate_models_on_startup
from .analysis_versions import (
    PROMPT_ANALYSIS_VERSION,
    RULE_ANALYSIS_VERSION,
    SYSTEM_ANALYSIS_VERSION,
)

__all__ = [
    'MODEL_GROUNDING',
    'MODEL_FINAL', 
    'get_model_list',
    'validate_models_on_startup',
    'PROMPT_ANALYSIS_VERSION',
    'RULE_ANALYSIS_VERSION',
    'SYSTEM_ANALYSIS_VERSION',
]
