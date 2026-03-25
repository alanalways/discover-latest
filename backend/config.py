"""
backend/config.py
DiscoverLatest 2.0 全域設定

核心原則：
- FinMind 是主要資料來源，TWSE 做台股校驗，yfinance 僅作 fallback
- NVIDIA NIM 負責六大研究部門主分析
- Gemini 僅用在高價值節點：Batch Grounding、Arbitrator、Chief Analyst
- 所有設定以 free tier 安全值為主，避免超出免費額度
"""

from __future__ import annotations

import logging
import os

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("backend.config")


def _split_env_list(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


# ─────────────────────────────────────────────────────────
# 環境設定
# ─────────────────────────────────────────────────────────
APP_ENV: str = os.getenv("APP_ENV", "development")
SECRET_KEY: str = os.getenv("SECRET_KEY", "change-me-in-production")


# ─────────────────────────────────────────────────────────
# Gemini API
# ─────────────────────────────────────────────────────────
_raw_gemini_keys = os.getenv("GEMINI_API_KEYS") or os.getenv("GEMINI_API_KEY") or ""
GEMINI_API_KEYS_LIST: list[str] = _split_env_list(_raw_gemini_keys)
GEMINI_API_KEY: str = GEMINI_API_KEYS_LIST[0] if GEMINI_API_KEYS_LIST else ""

if GEMINI_API_KEYS_LIST:
    source = "GEMINI_API_KEYS" if os.getenv("GEMINI_API_KEYS") else "GEMINI_API_KEY"
    logger.warning(
        "[Config] Gemini key pool loaded from %s, count=%d, prefixes=%s",
        source,
        len(GEMINI_API_KEYS_LIST),
        [f"{key[:8]}..." for key in GEMINI_API_KEYS_LIST],
    )
else:
    logger.warning("[Config] Gemini key NOT found in env")

GEMINI_FLASH: str = "gemini-2.5-flash"
GEMINI_FLASH_LITE: str = "gemini-2.5-flash-lite"
GEMINI_PRO: str = "gemini-2.5-pro"
GEMINI_3_FLASH: str = "gemini-3-flash-preview"
GEMINI_3_1_FLASH_LITE: str = "gemini-3.1-flash-lite-preview"

GEMINI_GROUNDING_MODEL: str = GEMINI_FLASH
GEMINI_GROUNDING_ENABLED_MODELS: set[str] = {GEMINI_FLASH, GEMINI_FLASH_LITE}

# 以 free tier 安全值為主；實際值可再依 AI Studio 專案設定覆寫
GEMINI_RATE_LIMITS: dict[str, dict[str, int | bool]] = {
    GEMINI_FLASH: {"rpm": 5, "rpd": 20, "tpm": 250_000, "supports_grounding": True},
    GEMINI_FLASH_LITE: {"rpm": 10, "rpd": 20, "tpm": 250_000, "supports_grounding": True},
    GEMINI_PRO: {"rpm": 4, "rpd": 20, "tpm": 250_000, "supports_grounding": False},
    GEMINI_3_FLASH: {"rpm": 5, "rpd": 20, "tpm": 250_000, "supports_grounding": False},
    GEMINI_3_1_FLASH_LITE: {"rpm": 10, "rpd": 200, "tpm": 250_000, "supports_grounding": False},
}

AGENT_MODEL_MAP: dict[str, str] = {
    "batch_grounding": GEMINI_FLASH,
    "arbitrator": GEMINI_3_FLASH,
    "chief_analyst": GEMINI_3_FLASH,
    "scanner": GEMINI_3_1_FLASH_LITE,
}

FALLBACK_MODEL: dict[str, str] = {
    GEMINI_3_FLASH: GEMINI_PRO,
    GEMINI_PRO: GEMINI_FLASH,
    GEMINI_FLASH: GEMINI_FLASH_LITE,
    GEMINI_3_1_FLASH_LITE: GEMINI_FLASH_LITE,
}

ANALYSIS_GEMINI_MODELS: set[str] = {
    GEMINI_FLASH,
    GEMINI_FLASH_LITE,
    GEMINI_PRO,
    GEMINI_3_FLASH,
}

# Search grounding 為 per-project 配額；使用多個獨立 project 時可近似線性放大
GEMINI_SEARCH_GROUNDING_SHARED_RPD: int = 500 * max(1, len(GEMINI_API_KEYS_LIST))


# ─────────────────────────────────────────────────────────
# Supabase
# ─────────────────────────────────────────────────────────
SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY: str = (
    os.getenv("SUPABASE_SERVICE_KEY")
    or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    or ""
)
SUPABASE_ANON_KEY: str = os.getenv("SUPABASE_ANON_KEY", "")


# ─────────────────────────────────────────────────────────
# OAuth / Admin
# ─────────────────────────────────────────────────────────
GOOGLE_CLIENT_ID: str = os.getenv("GOOGLE_CLIENT_ID", "")
DEFAULT_ADMIN_EMAIL: str = os.getenv("DEFAULT_ADMIN_EMAIL", "cmshj30326@gmail.com")
SPACE_URL: str = os.getenv("SPACE_URL", "https://alanalways-discover-latest-v2.hf.space")


# ─────────────────────────────────────────────────────────
# Gmail SMTP
# ─────────────────────────────────────────────────────────
GMAIL_SMTP_USER: str = os.getenv("GMAIL_SMTP_USER", "cmshj30326@gmail.com")
GMAIL_SMTP_APP_PASSWORD: str = os.getenv("GMAIL_SMTP_APP_PASSWORD", "")


# ─────────────────────────────────────────────────────────
# 使用者方案
# ─────────────────────────────────────────────────────────
TIER_LIMITS: dict[str, dict[str, int]] = {
    "free": {"daily_limit": 5, "per_minute": 2},
    "pro": {"daily_limit": 30, "per_minute": 5},
    "premium": {"daily_limit": 200, "per_minute": 15},
}


# ─────────────────────────────────────────────────────────
# FinMind
# ─────────────────────────────────────────────────────────
_raw_finmind_tokens = os.getenv("FINMIND_TOKENS", "")
FINMIND_TOKENS_LIST: list[str] = _split_env_list(_raw_finmind_tokens)
if not FINMIND_TOKENS_LIST:
    fallback_keys = ["FINMIND_TOKEN", "FINMIND_TOKEN_2", "FINMIND_TOKEN_3", "FINMIND_TOKEN_4"]
    FINMIND_TOKENS_LIST = [
        os.getenv(name, "").strip()
        for name in fallback_keys
        if os.getenv(name, "").strip()
    ]

if FINMIND_TOKENS_LIST:
    logger.warning(
        "[Config] FinMind token pool loaded, count=%d, prefixes=%s",
        len(FINMIND_TOKENS_LIST),
        [f"{token[:8]}..." for token in FINMIND_TOKENS_LIST],
    )
else:
    logger.warning("[Config] FinMind token NOT found, anonymous quota only")

FINMIND_RATE_LIMITS: dict[str, int] = {
    "rpm_per_token": 10,
    "rph_per_token": 550,
}

FINMIND_CACHE_TTL: dict[str, int] = {
    "TaiwanStockInfo": 3600,
    "TaiwanStockPrice": 900,
    "TaiwanStockPER": 7200,
    "TaiwanStockMonthRevenue": 86400,
    "TaiwanStockFinancialStatements": 86400,
    "TaiwanStockBalanceSheet": 86400,
    "TaiwanStockCashFlowsStatement": 86400,
    "TaiwanStockDividend": 86400,
    "TaiwanStockMarketValue": 7200,
    "TaiwanStockInstitutionalInvestorsBuySell": 900,
    "TaiwanStockMarginPurchaseShortSale": 900,
    "USStockPrice": 900,
    "USStockInfo": 3600,
    "_default": 600,
}


# ─────────────────────────────────────────────────────────
# Pinecone / HuggingFace
# ─────────────────────────────────────────────────────────
PINECONE_API_KEY: str = os.getenv("PINECONE_API_KEY", "")
PINECONE_INDEX_NAME: str = os.getenv("PINECONE_INDEX_NAME", "discoverlatest-knowledge")

HF_TOKEN: str = os.getenv("HF_TOKEN", "")
HF_DATASET_REPO: str = os.getenv("HF_DATASET_REPO", "")


# ─────────────────────────────────────────────────────────
# NVIDIA NIM
# ─────────────────────────────────────────────────────────
NVIDIA_API_KEY: str = os.getenv("NVIDIA_API_KEY", "")
NVIDIA_BASE_URL: str = "https://integrate.api.nvidia.com/v1"
NVIDIA_MODEL: str = "moonshotai/kimi-k2.5"

if NVIDIA_API_KEY:
    logger.warning("[Config] NVIDIA key loaded, prefix=%s...", NVIDIA_API_KEY[:12])
else:
    logger.warning("[Config] NVIDIA_API_KEY NOT found")

NVIDIA_RATE_LIMITS: dict[str, dict[str, int | None]] = {
    NVIDIA_MODEL: {"rpm": 40, "rpd": None, "tpm": None},
}


# ─────────────────────────────────────────────────────────
# Provider / Model Routing
# ─────────────────────────────────────────────────────────
AGENT_PROVIDER_MAP: dict[str, str] = {
    "batch_grounding": "gemini",
    "technical_agent": "nvidia",
    "fundamental_agent": "nvidia",
    "chips_agent": "nvidia",
    "event_agent": "nvidia",
    "macro_agent": "nvidia",
    "sentiment_agent": "nvidia",
    "arbitrator": "gemini",
    "chief_analyst": "gemini",
    "scanner": "gemini",
    "prompt_evolver": "nvidia",
    "backtester": "nvidia",
    "memory_agent": "nvidia",
}


# ─────────────────────────────────────────────────────────
# 預算守門
# ─────────────────────────────────────────────────────────
_analysis_rpd_per_project = sum(
    int(GEMINI_RATE_LIMITS[model]["rpd"])
    for model in ANALYSIS_GEMINI_MODELS
)
_default_grounding_budget = max(
    60,
    int(_analysis_rpd_per_project * max(1, len(GEMINI_API_KEYS_LIST)) * 0.75),
)
_budget_env_value = (
    os.getenv("DAILY_GEMINI_RPD_BUDGET")
    or os.getenv("DAILY_GROUNDING_RPD_BUDGET")
    or str(_default_grounding_budget)
)
DAILY_GROUNDING_RPD_BUDGET: int = int(_budget_env_value)
SUPABASE_WARN_MB: int = int(os.getenv("SUPABASE_WARN_MB", "350"))
SUPABASE_CRITICAL_MB: int = int(os.getenv("SUPABASE_CRITICAL_MB", "425"))
DEFAULT_SCHEDULED_ANALYSIS_GROUNDING_MODE: str = os.getenv(
    "DEFAULT_SCHEDULED_ANALYSIS_GROUNDING_MODE",
    "cache_only",
).strip().lower()
HEARTBEAT_QUEUE_MAX_JOBS: int = int(os.getenv("HEARTBEAT_QUEUE_MAX_JOBS", "8"))
