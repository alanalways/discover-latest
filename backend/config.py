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
# 相容 HuggingFace 上可能的命名（GEMINI_API_KEY6 等舊版名稱）
GEMINI_API_KEY: str = (
    os.getenv("GEMINI_API_KEY")
    or os.getenv("GEMINI_API_KEY6")
    or ""
)

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
DAILY_GEMINI_RPD_BUDGET: int = int(os.getenv("DAILY_GEMINI_RPD_BUDGET", "800"))
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
# Free tier 安全 rate limit（留 buffer）
# ─────────────────────────────────────────────────────────
RATE_LIMITS: dict[str, dict[str, int]] = {
    "gemini-2.5-flash":        {"rpm": 12, "rpd": 900},
    "gemini-2.5-pro":          {"rpm": 4,  "rpd": 90},
    "gemini-2.5-flash-lite":   {"rpm": 14, "rpd": 900},
    "gemini-3-flash-preview":  {"rpm": 8,  "rpd": 400},
}
