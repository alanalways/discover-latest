"""
backend/config.py
DiscoverLatest 2.0 — 全域設定

架構說明：
  Gemini 2.5 Flash  → 唯一保留，僅用於 Batch Search Grounding（Search Grounding 1.5K RPD 獨立配額）
  NVIDIA NIM        → 所有分析工作（kimi-k2-instruct，40 RPM，無日限制）

Rate Limits 來源：Google AI Studio > Rate Limit 頁面實測（2026-03-22）
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ─────────────────────────────────────────────────────────
# 環境設定
# ─────────────────────────────────────────────────────────
APP_ENV: str = os.getenv("APP_ENV", "development")
SECRET_KEY: str = os.getenv("SECRET_KEY", "change-me-in-production")

# ─────────────────────────────────────────────────────────
# Gemini API（Runtime AI 大腦）
# ─────────────────────────────────────────────────────────
# 相容 HuggingFace 上的命名（GEMINI_API_KEYS 複數，逗號分隔多把 key）
_raw_keys: str = (
    os.getenv("GEMINI_API_KEYS")
    or os.getenv("GEMINI_API_KEY")
    or ""
)

# 解析為 key pool（支援逗號分隔的多把 key）
GEMINI_API_KEYS_LIST: list[str] = [
    k.strip() for k in _raw_keys.split(",") if k.strip()
]

# 向下相容：單一 key（取第一把）
GEMINI_API_KEY: str = GEMINI_API_KEYS_LIST[0] if GEMINI_API_KEYS_LIST else ""

# Startup debug（不印全 key，只印來源和數量）
import logging as _logging
_cfg_logger = _logging.getLogger("backend.config")
if GEMINI_API_KEYS_LIST:
    _src = "GEMINI_API_KEYS" if os.getenv("GEMINI_API_KEYS") else "GEMINI_API_KEY"
    _cfg_logger.warning(
        f"[Config] Gemini key pool loaded from {_src}, "
        f"count={len(GEMINI_API_KEYS_LIST)}, "
        f"prefixes={[k[:8]+'...' for k in GEMINI_API_KEYS_LIST]}"
    )
else:
    _cfg_logger.warning("[Config] Gemini key NOT found in any env var")

# ─────────────────────────────────────────────────────────
# Supabase
# ─────────────────────────────────────────────────────────
SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
# 相容 HuggingFace Spaces 慣用名稱 SUPABASE_SERVICE_ROLE_KEY
SUPABASE_SERVICE_KEY: str = (
    os.getenv("SUPABASE_SERVICE_KEY")
    or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    or ""
)
SUPABASE_ANON_KEY: str = os.getenv("SUPABASE_ANON_KEY", "")

# ─────────────────────────────────────────────────────────
# Google OAuth
# ─────────────────────────────────────────────────────────
GOOGLE_CLIENT_ID: str = os.getenv("GOOGLE_CLIENT_ID", "")

# ─────────────────────────────────────────────────────────
# Admin
# ─────────────────────────────────────────────────────────
DEFAULT_ADMIN_EMAIL: str = os.getenv("DEFAULT_ADMIN_EMAIL", "cmshj30326@gmail.com")

# ─────────────────────────────────────────────────────────
# Gmail SMTP
# ─────────────────────────────────────────────────────────
GMAIL_SMTP_USER: str = os.getenv("GMAIL_SMTP_USER", "cmshj30326@gmail.com")
GMAIL_SMTP_APP_PASSWORD: str = os.getenv("GMAIL_SMTP_APP_PASSWORD", "")

# ─────────────────────────────────────────────────────────
# 使用者方案等級限制
# ─────────────────────────────────────────────────────────
TIER_LIMITS: dict[str, dict[str, int]] = {
    "free":    {"daily_limit": 5,   "per_minute": 2},
    "pro":     {"daily_limit": 30,  "per_minute": 5},
    "premium": {"daily_limit": 200, "per_minute": 15},
}

# ─────────────────────────────────────────────────────────
# Space URL（OAuth redirect）
# ─────────────────────────────────────────────────────────
SPACE_URL: str = os.getenv("SPACE_URL", "https://alanalways-discover-latest-v2.hf.space")

# ─────────────────────────────────────────────────────────
# FinMind（台股+美股 主要資料來源）
# ─────────────────────────────────────────────────────────
# 雙 Token 系統：各 600 req/hr，合計 1200 req/hr
_finmind_raw: str = os.getenv("FINMIND_TOKENS", "")  # 逗號分隔多把
FINMIND_TOKENS_LIST: list[str] = [
    k.strip() for k in _finmind_raw.split(",") if k.strip()
] if _finmind_raw else []

# 向下相容：個別環境變數
if not FINMIND_TOKENS_LIST:
    _fm_singles = []
    for _fk in ["FINMIND_TOKEN", "FINMIND_TOKEN_2", "FINMIND_TOKEN_3", "FINMIND_TOKEN_4"]:
        _v = os.getenv(_fk, "")
        if _v:
            _fm_singles.append(_v)
    FINMIND_TOKENS_LIST = _fm_singles

if FINMIND_TOKENS_LIST:
    _cfg_logger.warning(
        f"[Config] FinMind token pool: count={len(FINMIND_TOKENS_LIST)}, "
        f"prefixes={[k[:8]+'...' for k in FINMIND_TOKENS_LIST]}"
    )
else:
    _cfg_logger.warning("[Config] FinMind token NOT found — will use 300 req/hr anonymous")

# FinMind Rate Limit（per token，留 buffer）
FINMIND_RATE_LIMITS: dict[str, int] = {
    "rpm_per_token": 10,     # 每分鐘安全上限
    "rph_per_token": 550,    # 每小時安全上限（600 扣 buffer）
}

# FinMind 快取 TTL（秒）
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
# Pinecone（RAG 知識庫）
# ─────────────────────────────────────────────────────────
PINECONE_API_KEY: str = os.getenv("PINECONE_API_KEY", "")
PINECONE_INDEX_NAME: str = os.getenv("PINECONE_INDEX_NAME", "discoverlatest-knowledge")

# ─────────────────────────────────────────────────────────
# HuggingFace（冷層封存）
# ─────────────────────────────────────────────────────────
HF_TOKEN: str = os.getenv("HF_TOKEN", "")
HF_DATASET_REPO: str = os.getenv("HF_DATASET_REPO", "")

# ─────────────────────────────────────────────────────────
# NVIDIA NIM（所有分析工作的主力）
# ─────────────────────────────────────────────────────────
NVIDIA_API_KEY: str = os.getenv("NVIDIA_API_KEY", "")
NVIDIA_BASE_URL: str = "https://integrate.api.nvidia.com/v1"

# 分析用模型：kimi-k2.5
NVIDIA_MODEL: str = "moonshotai/kimi-k2.5"

# ─────────────────────────────────────────────────────────
# Gemini（僅保留 Batch Search Grounding 用途）
# ─────────────────────────────────────────────────────────
# 使用模型：gemini-2.5-flash（唯一有免費 Search Grounding 的主力模型）
GEMINI_GROUNDING_MODEL: str = "gemini-2.5-flash"

# ─────────────────────────────────────────────────────────
# 各 Agent 的 Provider 分配
# ─────────────────────────────────────────────────────────
# "gemini" → 只做 Batch Search Grounding，呼叫 backend/gemini/grounding.py
# "nvidia" → 所有分析推理，呼叫 backend/nvidia/client.py
AGENT_PROVIDER_MAP: dict[str, str] = {
    # Grounding（唯一留在 Gemini 的）
    "batch_grounding":   "gemini",

    # 六大研究部門（全部 NVIDIA）
    "technical_agent":   "nvidia",
    "fundamental_agent": "nvidia",
    "chips_agent":       "nvidia",
    "event_agent":       "nvidia",   # 分析 grounding 回來的資料，不自己 grounding
    "macro_agent":       "nvidia",
    "sentiment_agent":   "nvidia",

    # 仲裁 + 首席分析（NVIDIA，kimi-k2-instruct 推理足夠）
    "arbitrator":        "nvidia",
    "chief_analyst":     "nvidia",

    # 批次掃描 + 演進引擎（全部 NVIDIA）
    "scanner":           "nvidia",
    "prompt_evolver":    "nvidia",
    "backtester":        "nvidia",
    "memory_agent":      "nvidia",
}

# ─────────────────────────────────────────────────────────
# Rate Limits（實測值，來自 Google AI Studio Rate Limit 頁面，2026-03-22）
# ─────────────────────────────────────────────────────────

# Gemini Free Tier 實際限制（來源：Google AI Studio Rate Limit 頁面，2026-03-22）
# ⚠️ Search Grounding 500 RPD 是 Flash + Flash-Lite 共用的總上限，不是獨立配額
#    → 每次 grounding 呼叫同時消耗：1 text RPD + 1 shared grounding RPD
#    → 實際瓶頸 = min(text RPD, grounding RPD) = min(20, 500) = 20 次/天
GEMINI_RATE_LIMITS: dict[str, dict] = {
    "gemini-2.5-flash": {
        "rpm": 5,
        "rpd": 20,          # 文字呼叫上限（grounding 呼叫也消耗這個）
        "tpm": 250000,
    },
    "gemini-2.5-flash-lite": {
        "rpm": 10,
        "rpd": 20,
        "tpm": 250000,
    },
    "gemini-3.1-flash-lite": {
        "rpm": 15,
        "rpd": 500,         # 最高 RPD，但不支援免費 grounding
        "tpm": 250000,
    },
}

# Search Grounding 共用池（Flash + Flash-Lite 合計上限）
GEMINI_SEARCH_GROUNDING_SHARED_RPD: int = 500

# NVIDIA NIM 限制（所有模型統一 40 RPM，無日限制）
NVIDIA_RATE_LIMITS: dict[str, dict] = {
    "moonshotai/kimi-k2.5": {
        "rpm": 40,
        "rpd": None,   # 無日限制
        "tpm": None,   # 無 token 日限制
    },
}

# ─────────────────────────────────────────────────────────
# 預算守門設定
# ─────────────────────────────────────────────────────────
# Gemini grounding 每日預算
# 實際瓶頸：text RPD=20（grounding 呼叫也消耗），Grounding 池=500（Flash+Flash-Lite 共用）
# → 每天最多 20 次 batch grounding = 20 次完整分析（批次 grounding 後交 NVIDIA 分析）
DAILY_GROUNDING_RPD_BUDGET: int = int(os.getenv("DAILY_GROUNDING_RPD_BUDGET", "18"))
SUPABASE_WARN_MB: int = int(os.getenv("SUPABASE_WARN_MB", "350"))
SUPABASE_CRITICAL_MB: int = int(os.getenv("SUPABASE_CRITICAL_MB", "425"))
