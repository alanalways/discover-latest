"""
backend/config.py
DiscoverLatest 2.0 — 全域設定
包含 AGENT_MODEL_MAP、FALLBACK_MODEL、RATE_LIMITS 及所有環境變數讀取
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
# 預算守門設定
# ─────────────────────────────────────────────────────────
DAILY_GEMINI_RPD_BUDGET: int = int(os.getenv("DAILY_GEMINI_RPD_BUDGET", "5000"))
SUPABASE_WARN_MB: int = int(os.getenv("SUPABASE_WARN_MB", "350"))
SUPABASE_CRITICAL_MB: int = int(os.getenv("SUPABASE_CRITICAL_MB", "425"))

# ─────────────────────────────────────────────────────────
# 各 Agent 的 Gemini 模型分配
# ─────────────────────────────────────────────────────────
AGENT_MODEL_MAP: dict[str, str] = {
    # Stage 1：新聞 grounding（需要 Google Search 工具）
    "news_grounding":     "gemini-2.5-flash",

    # 五大研究部門（結構化分析，Flash 足夠）
    "technical_agent":    "gemini-2.5-flash",
    "fundamental_agent":  "gemini-2.5-flash",
    "chips_agent":        "gemini-2.5-flash",
    "event_agent":        "gemini-2.5-flash",
    "macro_agent":        "gemini-2.5-flash",
    "sentiment_agent":    "gemini-2.5-flash",

    # 矛盾仲裁（複雜推理，用最強免費模型）
    "arbitrator":         "gemini-3-flash-preview",

    # Chief Analyst 最終報告（最重要，用最強免費模型）
    "chief_analyst":      "gemini-3-flash-preview",

    # 批次掃描（大量呼叫，用最便宜的）
    "scanner":            "gemini-2.5-flash-lite",

    # 演進引擎
    "prompt_evolver":     "gemini-2.5-pro",
    "backtester":         "gemini-2.5-flash",
    "memory_agent":       "gemini-2.5-flash",
}

# ─────────────────────────────────────────────────────────
# Rate limit 超出時的自動降級鏈
# ─────────────────────────────────────────────────────────
FALLBACK_MODEL: dict[str, str] = {
    "gemini-3-flash-preview":  "gemini-2.5-pro",
    "gemini-2.5-pro":          "gemini-2.5-flash",
    "gemini-2.5-flash":        "gemini-2.5-flash-lite",
}

# ─────────────────────────────────────────────────────────
# Free tier 安全 rate limit（2026-03 更新，留 buffer）
# Google 於 2025-12 大幅下調免費額度
# 官方文件：https://ai.google.dev/gemini-api/docs/rate-limits
# ─────────────────────────────────────────────────────────
RATE_LIMITS: dict[str, dict[str, int]] = {
    "gemini-2.5-flash":        {"rpm": 8,   "rpd": 220},   # 實際: 10 RPM, 250 RPD
    "gemini-2.5-pro":          {"rpm": 4,   "rpd": 85},    # 實際: 5 RPM, 100 RPD
    "gemini-2.5-flash-lite":   {"rpm": 12,  "rpd": 900},   # 實際: 15 RPM, 1000 RPD
    "gemini-3-flash-preview":  {"rpm": 8,   "rpd": 200},   # 實際: ~10 RPM, ~250 RPD（預覽版）
}
