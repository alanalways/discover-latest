# CLAUDE.md — DiscoverLatest 2.0 完整重建指令
> 版本：2.2.0 | 日期：2026-03-20（已更新加速 Pipeline + 缺陷評估）
> 本檔案是給 Claude Code 的最高指令。所有開發行為以此為準。

---

## ⚡ 專案現況快照（Claude Code 開始前必讀）

**已完成：**
- A1 ✅：舊版程式碼已全部移入 `_legacy/`，根目錄乾淨

**立即需要你做的事（在跑任何程式碼之前）：**

```
❗ 重要：.env 目前只有 Gmail key，缺少以下必要 key，
   請提示使用者補齊後再繼續：

   GEMINI_API_KEY      → Google AI Studio 取得
   SUPABASE_URL        → Supabase 專案設定頁
   SUPABASE_SERVICE_KEY → Supabase API 設定頁
   SUPABASE_ANON_KEY   → Supabase API 設定頁
```

**從舊版繼承的關鍵技術資訊：**

| 項目 | 舊版用法 | 新版處理方式 |
|------|---------|------------|
| Gemini SDK | `google-genai>=1.0.0`（新版 SDK） | **繼續用新版 SDK**，不是 `google-generativeai` |
| 台股資料 | FinMind API（`finmind` 套件） | 繼承 `_legacy/adapters/finmind.py` 邏輯 |
| 美股資料 | `yfinance>=0.2.0,<0.2.59`（有版本限制） | **鎖定 `yfinance>=0.2.0,<0.2.59`，新版有 bug** |
| 資料庫 | Supabase（`_legacy/adapters/supabase*.py`） | 參考舊版 adapter 邏輯搬移 |
| 後端框架 | FastAPI（舊版已有完整結構） | 繼續用 FastAPI |
| 前端 | Next.js（`_legacy/frontend/`） | **改為 Vite + React + TypeScript**（全新） |

**可以直接參考的舊版檔案（`_legacy/` 中）：**
- `adapters/supabase_client.py` → 參考搬移為新的 `backend/data/storage/supabase_client.py`
- `adapters/yahoo.py` → 參考搬移為新的 `backend/data/sources/yahoo.py`
- `adapters/finmind.py` → 參考搬移為新的 `backend/data/sources/finmind.py`
- `services/gemini_service.py` → 參考 Gemini 呼叫邏輯（但架構全部重寫）
- `services/rate_limiter.py` → 參考 rate limit 邏輯

---

## 0. 最重要的兩件事（先讀這裡）

### 事情一：AI 分析判斷 vs 程式碼撰寫 完全分開

```
Gemini API  → 負責所有「AI 投資分析判斷」（分析股票、判斷訊號、生成報告）
Claude Code → 負責「撰寫程式碼」（你現在做的事）
```

**Gemini 是這個平台的 AI 大腦，Claude Code 是建造這個平台的工程師。**
不要把這兩件事混淆。

### 事情二：Claude Code 撰寫程式碼的模型分工

```
Opus 4.6   (claude-opus-4-6)  → 撰寫「架構設計、複雜邏輯、Agent 協調」的程式碼
Sonnet 4.6 (claude-sonnet-4-6)→ 撰寫「API 路由、資料庫操作、工具函式」的程式碼
```

Claude Code 在每個任務開始前，自行判斷複雜度決定用哪個模型撰寫。
判斷標準見 Section 1。

---

## 1. Claude Code 模型選擇標準

**用 Opus 4.6 撰寫以下類型的程式碼：**

| 程式碼類型 | 範例 |
|-----------|------|
| Paperclip 多 Agent 協調邏輯 | `ceo_agent.py`、`heartbeat.py`、`task_queue.py` |
| 矛盾仲裁流程 | `arbitrator.py`（判斷哪個 Gemini 輸出可信） |
| 自我演進引擎 | `prompt_evolver.py`、`backtester.py` |
| 資料庫 Schema 設計 | `migrations/001_initial_schema.sql` |
| 核心 Pipeline 整合 | 把五個 Agent 輸出合併的主流程 |
| 任何需要複雜條件邏輯 | 超過 3 層 if/else 或複雜狀態機 |

**用 Sonnet 4.6 撰寫以下類型的程式碼：**

| 程式碼類型 | 範例 |
|-----------|------|
| FastAPI 路由 | `routes/analysis.py`、`routes/scanner.py` |
| Supabase CRUD | `supabase_client.py` |
| Gemini API 呼叫封裝 | `gemini_client.py` |
| 前端 React 元件 | 所有 `.tsx` 檔案 |
| 環境設定、工具函式 | `config.py`、`utils.py` |
| 排程設定 | `heartbeat.py` 中的時間設定部分 |
| 儲存操作 | `storage_curator.py`、`cold_storage.py` |

---

## 2. Gemini 模型使用策略（AI 分析判斷用）

這是給 Python 程式碼在 runtime 呼叫 Gemini 的設定，不是給 Claude Code 自己用的。

### Free Tier 可用模型（2026-03 現況）

```python
# 免費可用，穩定版本
GEMINI_FLASH      = "gemini-2.5-flash"        # 快速、grounding 支援、主力用途
GEMINI_PRO        = "gemini-2.5-pro"           # 深度分析，免費但 RPM 較低
GEMINI_FLASH_LITE = "gemini-2.5-flash-lite"    # 最便宜，批次掃描用

# 免費 Preview（功能最強，rate limit 較嚴）
GEMINI_3_FLASH    = "gemini-3-flash-preview"   # 有免費 tier，推理最強
# 注意：gemini-3.1-pro-preview 沒有免費 API tier，不要使用
```

### 各 Agent 的 Gemini 模型分配

在 `backend/config.py` 中定義：

```python
AGENT_MODEL_MAP = {
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
    "prompt_evolver":     "gemini-2.5-pro",    # 需要深度推理
    "backtester":         "gemini-2.5-flash",
    "memory_agent":       "gemini-2.5-flash",
}

# Rate limit 超出時的自動降級鏈
FALLBACK_MODEL = {
    "gemini-3-flash-preview":  "gemini-2.5-pro",
    "gemini-2.5-pro":          "gemini-2.5-flash",
    "gemini-2.5-flash":        "gemini-2.5-flash-lite",
}

# Free tier 安全 rate limit（留 buffer）
RATE_LIMITS = {
    "gemini-2.5-flash":        {"rpm": 12, "rpd": 900},
    "gemini-2.5-pro":          {"rpm": 4,  "rpd": 90},
    "gemini-2.5-flash-lite":   {"rpm": 14, "rpd": 900},
    "gemini-3-flash-preview":  {"rpm": 8,  "rpd": 400},
}
```

---

## 3. 保留 vs 重建 清單

### 保留（完全不動）
- 使用者登入系統（Google / LINE OAuth）
- 外部資料來源串接（TWSE、Yahoo Finance 所有抓取邏輯）
- 現有 Gemini grounding 呼叫邏輯（封裝進新架構，不改邏輯）

### 全部重建
- 後端架構（FastAPI）
- 資料庫 Schema（Supabase 全新設計）
- 所有 Agent Pipeline（Paperclip 架構）
- 前端 UI/UX（React + TypeScript）
- 部署設定（Dockerfile + HuggingFace）
- 報告格式與輸出風格
- 品牌視覺（類彭博終端深色系）

---

## 4. 專案目錄結構

建立以下結構。現有程式碼全部移至 `_legacy/` 備份，不要刪除：

```
discoverlatest/
├── CLAUDE.md
├── .env                             # 不 commit
├── .env.example                     # commit
├── .gitignore
├── Dockerfile
├── app.py                           # HuggingFace Spaces 入口
├── requirements.txt
├── _legacy/                         # 舊版程式碼備份
│
├── backend/
│   ├── config.py                    # 全域設定（含 AGENT_MODEL_MAP）
│   ├── main.py                      # FastAPI 主程式
│   │
│   ├── gemini/
│   │   ├── client.py                # 統一 Gemini 呼叫入口
│   │   ├── grounding.py             # Google Search grounding
│   │   └── rate_limiter.py          # Rate limit + 自動降級
│   │
│   ├── agents/
│   │   ├── base_agent.py
│   │   ├── ceo_agent.py             # CEO 調度官（Opus 撰寫）
│   │   ├── departments/
│   │   │   ├── technical.py         # (Sonnet 撰寫)
│   │   │   ├── fundamental.py       # (Sonnet 撰寫)
│   │   │   ├── chips.py             # (Sonnet 撰寫)
│   │   │   ├── event.py             # (Sonnet 撰寫)
│   │   │   ├── macro.py             # (Sonnet 撰寫)
│   │   │   └── sentiment.py         # (Sonnet 撰寫)
│   │   ├── arbitrator.py            # 矛盾仲裁（Opus 撰寫）
│   │   ├── chief_analyst.py         # Chief Analyst（Opus 撰寫）
│   │   ├── evolution/
│   │   │   ├── backtester.py        # 準確率回測（Opus 撰寫）
│   │   │   ├── prompt_evolver.py    # Prompt 進化（Opus 撰寫）
│   │   │   └── memory_agent.py      # RAG 記憶（Sonnet 撰寫）
│   │   └── infra/
│   │       ├── storage_curator.py   # 儲存管理（Sonnet 撰寫）
│   │       └── cost_monitor.py      # 成本監控（Sonnet 撰寫）
│   │
│   ├── core/
│   │   ├── heartbeat.py             # APScheduler（Sonnet 撰寫）
│   │   ├── task_queue.py            # job_queue 管理（Opus 撰寫）
│   │   ├── audit_log.py             # 行為留痕（Sonnet 撰寫）
│   │   └── budget_guard.py          # API 預算守門（Sonnet 撰寫）
│   │
│   ├── data/
│   │   ├── sources/                 # 保留現有邏輯，只封裝介面
│   │   │   ├── twse.py
│   │   │   ├── yahoo.py
│   │   │   └── grounding.py
│   │   └── storage/
│   │       ├── supabase_client.py
│   │       ├── vector_store.py      # Pinecone
│   │       └── cold_storage.py      # HuggingFace Dataset
│   │
│   ├── api/
│   │   └── routes/
│   │       ├── analysis.py
│   │       ├── scanner.py
│   │       ├── watchlist.py
│   │       ├── accuracy.py          # 無需登入，公開
│   │       └── auth.py              # 保留現有登入邏輯
│   │
│   └── prompts/                     # Gemini Prompt 版本控制
│       ├── v1/
│       │   ├── technical.py
│       │   ├── fundamental.py
│       │   ├── chips.py
│       │   ├── event.py
│       │   ├── macro.py
│       │   ├── sentiment.py
│       │   ├── arbitrator.py
│       │   └── chief_analyst.py
│       └── registry.py
│
└── frontend/
    ├── package.json
    ├── vite.config.ts
    └── src/
        ├── pages/
        │   ├── Dashboard.tsx
        │   ├── Analysis.tsx
        │   ├── Scanner.tsx
        │   ├── Accuracy.tsx         # 公開，不需登入
        │   └── Watchlist.tsx
        ├── components/
        └── lib/
            ├── api.ts
            └── supabase.ts
```

---

## 5. 環境變數

```bash
# .env.example
# ⚠️ 目前 .env 只有 Gmail key，以下全部需要補齊才能執行

# Gemini（AI 分析大腦）— Google AI Studio 取得
GEMINI_API_KEY=your_google_ai_studio_key

# Supabase — 專案設定頁取得
SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_SERVICE_KEY=eyJ...
SUPABASE_ANON_KEY=eyJ...

# Pinecone（知識庫 RAG）
PINECONE_API_KEY=your_key
PINECONE_INDEX_NAME=discoverlatest-knowledge

# HuggingFace（冷層封存）
HF_TOKEN=hf_xxx
HF_DATASET_REPO=your_username/discoverlatest-archive

# FinMind（台股資料）— 舊版已有，繼承
FINMIND_TOKEN=your_finmind_token

# Gmail（舊版已有，繼承）
GMAIL_SMTP_USER=your_email
GMAIL_SMTP_APP_PASSWORD=your_app_password

# 應用設定
APP_ENV=production
SECRET_KEY=32字元隨機字串
DAILY_GEMINI_RPD_BUDGET=800
SUPABASE_WARN_MB=350
SUPABASE_CRITICAL_MB=425
```

---

## 6. Supabase Schema（第一步，不可跳過）

**Claude Code 使用 Opus 4.6 設計此 Schema。**
建立 `backend/migrations/001_initial_schema.sql` 並在 Supabase SQL Editor 執行：

```sql
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 1. 使用者偏好
CREATE TABLE IF NOT EXISTS user_prefs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id TEXT NOT NULL UNIQUE,
    risk_tolerance TEXT DEFAULT 'moderate',
    preferred_timeframe TEXT DEFAULT 'swing',
    watchlist JSONB DEFAULT '[]',
    notification_line BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 2. 報告主表
CREATE TABLE IF NOT EXISTS reports (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    symbol TEXT NOT NULL,
    market TEXT NOT NULL,
    report_type TEXT NOT NULL,
    tier TEXT NOT NULL,
    technical_output JSONB,
    fundamental_output JSONB,
    chips_output JSONB,
    event_output JSONB,
    macro_output JSONB,
    sentiment_output JSONB,
    arbitration_log JSONB,
    final_report TEXT NOT NULL,
    rating TEXT,
    target_price_low NUMERIC,
    target_price_high NUMERIC,
    confidence_score NUMERIC,
    total_gemini_calls INTEGER DEFAULT 0,
    total_tokens INTEGER DEFAULT 0,
    generation_time_ms INTEGER,
    triggered_by TEXT DEFAULT 'user',
    user_id TEXT,
    is_archived BOOLEAN DEFAULT FALSE,
    archived_at TIMESTAMPTZ,
    archive_path TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_reports_symbol ON reports(symbol);
CREATE INDEX idx_reports_created ON reports(created_at DESC);
CREATE INDEX idx_reports_not_archived ON reports(is_archived) WHERE is_archived = FALSE;

-- 3. 預測記錄（演進引擎核心，禁止改欄位結構）
CREATE TABLE IF NOT EXISTS predictions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    report_id UUID NOT NULL REFERENCES reports(id) ON DELETE CASCADE,
    symbol TEXT NOT NULL,
    market TEXT NOT NULL,
    predicted_direction TEXT NOT NULL,
    predicted_target_low NUMERIC,
    predicted_target_high NUMERIC,
    timeframe TEXT NOT NULL,
    prediction_date DATE NOT NULL DEFAULT CURRENT_DATE,
    verify_date DATE NOT NULL,
    is_verified BOOLEAN DEFAULT FALSE,
    verified_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_predictions_to_verify ON predictions(verify_date, is_verified)
    WHERE is_verified = FALSE;

-- 4. 實際結果（準確率回測官填入）
CREATE TABLE IF NOT EXISTS outcomes (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    prediction_id UUID NOT NULL REFERENCES predictions(id) ON DELETE CASCADE,
    symbol TEXT NOT NULL,
    actual_price_at_prediction NUMERIC NOT NULL,
    actual_price_at_verify NUMERIC NOT NULL,
    actual_direction TEXT NOT NULL,
    actual_change_pct NUMERIC,
    direction_correct BOOLEAN NOT NULL,
    target_hit BOOLEAN,
    score NUMERIC,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 5. Prompt 版本控制
CREATE TABLE IF NOT EXISTS prompt_versions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    agent_name TEXT NOT NULL,
    version INTEGER NOT NULL,
    prompt_content TEXT NOT NULL,
    model_assigned TEXT NOT NULL,
    accuracy_score NUMERIC,
    usage_count INTEGER DEFAULT 0,
    is_active BOOLEAN DEFAULT FALSE,
    evolved_from_version INTEGER,
    evolution_reason TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(agent_name, version)
);

-- 6. 工作佇列
CREATE TABLE IF NOT EXISTS job_queue (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    job_type TEXT NOT NULL,
    priority INTEGER DEFAULT 5,
    status TEXT DEFAULT 'pending',
    payload JSONB NOT NULL,
    result JSONB,
    error_message TEXT,
    assigned_agent TEXT,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,
    scheduled_for TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_job_queue_runnable ON job_queue(status, priority, scheduled_for)
    WHERE status = 'pending';

-- 7. Agent 行為日誌
CREATE TABLE IF NOT EXISTS agent_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    agent_name TEXT NOT NULL,
    job_id UUID,
    report_id UUID,
    action TEXT NOT NULL,
    gemini_model_used TEXT,
    tokens_used INTEGER DEFAULT 0,
    duration_ms INTEGER,
    status TEXT NOT NULL,
    error_detail TEXT,
    metadata JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_agent_logs_recent ON agent_logs(created_at DESC);

-- 8. 封存索引
CREATE TABLE IF NOT EXISTS archive_index (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source_table TEXT NOT NULL,
    source_ids UUID[] NOT NULL,
    archive_path TEXT NOT NULL,
    archive_tier TEXT NOT NULL,
    file_size_bytes BIGINT,
    checksum TEXT,
    record_count INTEGER,
    date_range_start DATE,
    date_range_end DATE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 9. 公開準確率視圖（績效儀表板用，無需登入可查）
CREATE OR REPLACE VIEW public_accuracy_stats AS
SELECT
    p.symbol,
    p.market,
    p.timeframe,
    COUNT(*) AS total_predictions,
    SUM(CASE WHEN o.direction_correct THEN 1 ELSE 0 END) AS correct_count,
    ROUND(AVG(CASE WHEN o.direction_correct THEN 1.0 ELSE 0.0 END) * 100, 1) AS accuracy_pct,
    MIN(p.prediction_date) AS tracking_since
FROM predictions p
JOIN outcomes o ON p.id = o.prediction_id
WHERE p.is_verified = TRUE
GROUP BY p.symbol, p.market, p.timeframe;
```

---

## 7. Gemini 客戶端封裝（Sonnet 撰寫）

**Claude Code 任務：建立 `backend/gemini/client.py`**

所有 Gemini 呼叫必須經過此模組。
⚠️ 使用新版 SDK `google-genai`（舊版 `_legacy/` 已在用），不是 `google-generativeai`：

```python
# backend/gemini/client.py
# Claude Code 使用 Sonnet 4.6 撰寫
# 參考 _legacy/services/gemini_service.py 的呼叫邏輯

import time, os
from google import genai
from google.genai import types
from backend.gemini.rate_limiter import RateLimiter
from backend.core.audit_log import log_gemini_call
from backend.config import AGENT_MODEL_MAP, FALLBACK_MODEL

_client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
_rate_limiter = RateLimiter()

def call_gemini(
    agent_name: str,
    prompt: str,
    use_grounding: bool = False,
    report_id: str = None
) -> dict:
    model_name = AGENT_MODEL_MAP.get(agent_name, "gemini-2.5-flash")

    # Rate limit 檢查，超出則自動降級
    if not _rate_limiter.can_call(model_name):
        fallback = FALLBACK_MODEL.get(model_name)
        if fallback and _rate_limiter.can_call(fallback):
            model_name = fallback
        else:
            return {"status": "rate_limited", "output": None}

    start = time.time()
    try:
        # 新版 SDK 寫法（google-genai>=1.0.0）
        config = types.GenerateContentConfig(temperature=1.0)
        if use_grounding:
            config = types.GenerateContentConfig(
                temperature=1.0,
                tools=[types.Tool(google_search=types.GoogleSearch())]
            )

        response = _client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=config
        )
        duration_ms = int((time.time() - start) * 1000)
        _rate_limiter.record_call(model_name)

        log_gemini_call(agent_name, model_name, report_id,
                        "success", duration_ms, use_grounding)

        return {
            "status": "success",
            "output": response.text,
            "model_used": model_name,
            "duration_ms": duration_ms
        }
    except Exception as e:
        log_gemini_call(agent_name, model_name, report_id,
                        "failed", error=str(e))
        return {"status": "failed", "error": str(e), "output": None}
```

---

## 8. Base Agent（Sonnet 撰寫）

**Claude Code 任務：建立 `backend/agents/base_agent.py`**

```python
# backend/agents/base_agent.py
# Claude Code 使用 Sonnet 4.6 撰寫

from abc import ABC, abstractmethod
from backend.gemini.client import call_gemini
from backend.core.audit_log import log_agent_action
from backend.prompts.registry import get_active_prompt

class BaseAgent(ABC):

    @property
    @abstractmethod
    def agent_name(self) -> str:
        pass

    @property
    def use_grounding(self) -> bool:
        return False

    def get_prompt(self, **kwargs) -> str:
        template = get_active_prompt(self.agent_name)
        return template.format(**kwargs)

    def run(self, report_id: str = None, **kwargs) -> dict:
        prompt = self.get_prompt(**kwargs)
        result = call_gemini(
            agent_name=self.agent_name,
            prompt=prompt,
            use_grounding=self.use_grounding,
            report_id=report_id
        )
        log_agent_action(self.agent_name, report_id, result["status"])
        return result
```

---

## 9. 六大研究部門 Agent（Sonnet 撰寫）

**Claude Code 任務：在 `backend/agents/departments/` 建立六個檔案**

每個 Agent 的固定結構：

```python
# 範例：technical.py
from backend.agents.base_agent import BaseAgent
import json

class TechnicalAgent(BaseAgent):

    @property
    def agent_name(self) -> str:
        return "technical_agent"

    # event/macro/sentiment 的 use_grounding 設為 True
    # technical/fundamental/chips 設為 False（使用傳入的資料）

    def analyze(self, symbol: str, market: str,
                price_data: dict, report_id: str = None) -> dict:
        result = self.run(
            report_id=report_id,
            symbol=symbol, market=market,
            price_data=json.dumps(price_data, ensure_ascii=False)
        )
        if result["status"] == "success":
            try:
                return json.loads(result["output"])
            except json.JSONDecodeError:
                return {"raw": result["output"], "parse_failed": True}
        return result
```

### Gemini Prompt 內容（`backend/prompts/v1/` 中）

**技術分析官 Prompt** 涵蓋：SMC（BOS/CHoCH/OB/FVG）、RSI(14)、MACD、KDJ(9,3,3)、EMA20/50/200、布林通道(20,2)、多週期對齊。輸出嚴格 JSON，包含 trend/strength/momentum/ma_alignment/support_levels/resistance_levels/summary/confidence。

**基本面研究官 Prompt** 涵蓋：EPS 年增率、本益比、本淨比、ROE、ROA、毛利率、負債比率、護城河評估、DCF 估值區間。

**籌碼分析官 Prompt** 涵蓋：三大法人（外資/投信/自營商）買賣超天數及總量、融資融券餘額趨勢、主力進出推估、籌碼集中度。

**事件驅動官 Prompt**（use_grounding=True）涵蓋：最近財報摘要、法說會重點、重大訊息公告、分析師評級變動、政策衝擊。

**宏觀策略官 Prompt**（use_grounding=True）涵蓋：美股三大指數傳導、VIX、Fed 利率預期、美元指數/台幣匯率、板塊輪動。

**情緒雷達官 Prompt**（use_grounding=True）涵蓋：社群媒體情緒、Google Trends、散戶信心、恐慌貪婪指數。

---

## 10. 矛盾仲裁官（Opus 撰寫邏輯，Gemini 3 Flash 執行分析）

**Claude Code 任務：建立 `backend/agents/arbitrator.py`**
**此檔案邏輯複雜，Claude Code 使用 Opus 4.6 撰寫程式碼**

功能：接收六部門 JSON 輸出 → 識別矛盾 → 對每個矛盾寫書面仲裁理由 → 輸出最終立場。

Gemini Prompt 輸出格式：
```json
{
  "conflicts_detected": [
    {
      "between": ["technical_agent", "chips_agent"],
      "conflict": "技術面多頭結構，但外資連續賣超",
      "adopted": "chips_agent",
      "reason": "籌碼面是實際交易行為，比型態更可信",
      "confidence": 0.75
    }
  ],
  "aligned_signals": ["macro_agent", "sentiment_agent"],
  "final_stance": "bullish|bearish|neutral|cautious_bullish|cautious_bearish",
  "stance_confidence": 0.0~1.0,
  "key_risks": ["風險一", "風險二"],
  "arbitration_summary": "200字內邏輯鏈說明，繁體中文"
}
```

---

## 11. Chief Analyst 最終報告（Opus 撰寫邏輯，Gemini 3 Flash 執行）

**Claude Code 任務：建立 `backend/agents/chief_analyst.py`**
**此檔案最複雜，Claude Code 使用 Opus 4.6 撰寫程式碼**

功能：
1. 接收仲裁結果 + 六部門輸出 + 股票基本資訊
2. 透過 Gemini 生成完整繁中投行研報
3. 同時生成 predictions 資料（方向/目標價/驗證日期）寫入 DB
4. 末尾附「可解釋 AI 說明」

固定報告章節順序（不可改）：
```
1. 市場快報
2. 技術面分析
3. 基本面解讀
4. 籌碼動向
5. 事件催化
6. 宏觀環境
7. 進出場計畫（短期1-5日/中期2-6週/長期2-4季，各含 SL/TP/R:R）
8. 風險提示
9. 結論
10. 情境地圖（偏多/偏空/震盪三情境）
11. 可解釋 AI（採信了哪些部門、仲裁理由摘要）
```

---

## 12. CEO Agent + 心跳引擎（CEO Opus 撰寫，心跳 Sonnet 撰寫）

**Claude Code 任務：建立 `backend/agents/ceo_agent.py` 和 `backend/core/heartbeat.py`**

心跳排程（`heartbeat.py`，Sonnet 撰寫）：

```python
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

def start_heartbeat():
    scheduler = BackgroundScheduler(timezone="Asia/Taipei")
    from backend.agents.ceo_agent import CEOAgent
    ceo = CEOAgent()

    scheduler.add_job(ceo.hourly_watchlist_scan,
        CronTrigger(minute=0), id="hourly")           # 每小時整點
    scheduler.add_job(ceo.premarket_scan,
        CronTrigger(hour=8, minute=25), id="premarket")  # 台股盤前
    scheduler.add_job(ceo.postmarket_summary,
        CronTrigger(hour=15, minute=5), id="postmarket") # 收盤後
    scheduler.add_job(ceo.weekly_backtest,
        CronTrigger(day_of_week="mon", hour=7), id="backtest") # 週一
    scheduler.add_job(ceo.storage_check,
        CronTrigger(hour="0,6,12,18"), id="storage")  # 每6小時

    scheduler.start()
    return scheduler
```

---

## 13. 儲存管理官（Sonnet 撰寫）

**Claude Code 任務：建立 `backend/agents/infra/storage_curator.py`**

完整邏輯：
1. 查詢 `SELECT pg_database_size(current_database()) / 1024 / 1024 AS used_mb`
2. 計算使用率
3. 依閾值處理：
   - `< 70%`：記錄健康日誌，結束
   - `70~85%`：封存 30 天前 reports → Parquet → 上傳 HuggingFace Dataset → 驗證 checksum → **確認可讀取後才刪除** → 更新 archive_index
   - `85~95%`：擴大至 15 天前，記錄 WARNING
   - `> 95%`：緊急封存 7 天前，暫停新報告寫入，記錄 CRITICAL

**核心防呆**：上傳後必須重新讀取一筆資料驗證，才可執行 DELETE。

---

## 14. 準確率回測官（Opus 撰寫，邏輯較複雜）

**Claude Code 任務：建立 `backend/agents/evolution/backtester.py`**
**Claude Code 使用 Opus 4.6 撰寫（涉及複雜金融計算邏輯）**

流程：
1. 查 `predictions` 表，找 `is_verified=FALSE` 且 `verify_date <= TODAY`
2. 從 Yahoo Finance 或 TWSE 抓取 `verify_date` 當天收盤價
3. 計算 `actual_direction`（vs prediction_date 收盤價）
4. 計算 `direction_correct`（vs predicted_direction）
5. 計算 `score`（方向正確 0.6 + 目標價命中 0.4）
6. 寫入 `outcomes` 表
7. 更新 `predictions.is_verified = TRUE`

---

## 15. 前端設計語言

**全部用 Tailwind CSS。**

```css
/* 色彩系統 */
--bg-base: #0D1117;        /* 主背景 */
--bg-card: #161B22;        /* 卡片 */
--bg-hover: #21262D;       /* hover */
--border: #30363D;         /* 邊框 */
--text-primary: #E6EDF3;
--text-secondary: #8B949E;
--accent: #1B9AAA;

/* 訊號色 */
--bullish: #3FB950;
--bearish: #F85149;
--neutral: #8B949E;
--warning: #D29922;
```

**字體：**
- 數字/代號：`font-mono`（JetBrains Mono）
- 中文內文：Noto Sans TC

**四個頁面：**

`Dashboard.tsx`：市場概覽條 → 自選股清單（即時評級）→ 快報 feed → 今日掃描 Top 10

`Analysis.tsx`：代號搜尋 → 完整分析 → 評級 badge / 目標價 / 各部門信號 / 仲裁理由 / 報告全文 → PDF 匯出

`Scanner.tsx`：篩選器 → 多因子評分排名表格

`Accuracy.tsx`：**完全公開，無需登入** → 整體準確率 % → 週趨勢圖 → 歷史記錄表

---

## 16. HuggingFace 部署

### `Dockerfile`
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN cd frontend && npm install && npm run build
EXPOSE 7860
CMD ["python", "app.py"]
```

### `app.py`
```python
import subprocess, sys
subprocess.run([
    sys.executable, "-m", "uvicorn",
    "backend.main:app",
    "--host", "0.0.0.0", "--port", "7860", "--workers", "1"
])
```

### `README.md` 開頭
```yaml
---
title: DiscoverLatest
emoji: 📊
colorFrom: blue
colorTo: indigo
sdk: docker
pinned: false
app_port: 7860
---
```

---

## 17. 完整執行順序（按步驟來，每步驗證通過才繼續）

### 階段 A：地基
```
A1  ✅ 已完成：舊版程式碼已移至 _legacy/

A2  建立完整目錄結構（Section 4）
    mkdir -p backend/gemini backend/agents/departments backend/agents/evolution
    mkdir -p backend/agents/infra backend/core backend/data/sources
    mkdir -p backend/data/storage backend/api/routes backend/prompts/v1
    mkdir -p backend/migrations frontend/src

A3  建立 .env.example（Section 5）和更新 .gitignore
    .gitignore 必須包含：.env, __pycache__, .pytest_cache, node_modules,
    .next, frontend/.next, *.pyc, .ruff_cache

A4  建立 requirements.txt（根目錄，新版）：

    # Gemini（新版 SDK，與 _legacy/ 一致）
    google-genai>=1.0.0

    # 資料來源（繼承 _legacy/，注意版本鎖定）
    yfinance>=0.2.0,<0.2.59    # ⚠️ 新版有 bug，不可升級
    pandas>=2.0.0
    numpy>=1.24.0
    requests>=2.28.0
    httpx>=0.24.0
    finmind>=1.6.0              # 台股資料（_legacy/ 已有）

    # 後端
    fastapi>=0.115.0
    uvicorn[standard]>=0.30.0
    pydantic>=2.0.0
    python-dotenv>=1.0.0
    pytz>=2024.1

    # 資料庫與儲存
    supabase>=2.9.0
    pinecone-client>=5.0.0
    pyarrow>=17.0.0             # Parquet 封存用
    datasets>=3.0.0             # HuggingFace Dataset 冷層

    # 排程
    apscheduler>=3.10.4

    # 認證（參考 _legacy/utils/auth.py）
    python-jose[cryptography]>=3.3.0
    passlib[bcrypt]>=1.7.4

A5  在 Supabase SQL Editor 執行 Section 6 的完整 SQL
    ⚠️ 這步需要手動操作，提示使用者去 Supabase Dashboard 執行

A6  建立 backend/config.py
    參考 _legacy/config/ 的設定邏輯，加入 AGENT_MODEL_MAP

A7  建立 backend/gemini/rate_limiter.py
    參考 _legacy/services/rate_limiter.py 的邏輯

A8  建立 backend/gemini/client.py（Section 7）
    ⚠️ 使用新版 SDK（google-genai），參考 _legacy/services/gemini_service.py

A9  建立 backend/core/audit_log.py

A10 建立 backend/data/storage/supabase_client.py
    參考 _legacy/adapters/supabase_client.py 搬移

A11 建立 backend/data/sources/finmind.py
    直接從 _legacy/adapters/finmind.py 複製並調整介面

A12 建立 backend/data/sources/yahoo.py
    直接從 _legacy/adapters/yahoo.py 複製並調整介面

✓ 驗證A：
  python -c "from google import genai; print('SDK OK')"
  python -c "from backend.gemini.client import call_gemini; print('Client OK')"
  python -c "from backend.data.storage.supabase_client import get_client; print('DB OK')"
```

### 階段 B：Agent 建立
```
B1  建立 backend/prompts/v1/ 八個 Prompt 檔案（6部門+仲裁+Chief Analyst）
B2  建立 backend/prompts/registry.py
B3  建立 backend/agents/base_agent.py（Section 8）
B4  建立 departments/ 六個部門 Agent（Sonnet 撰寫，Section 9）
B5  建立 backend/agents/arbitrator.py（Opus 撰寫，Section 10）
B6  建立 backend/agents/chief_analyst.py（Opus 撰寫，Section 11）

✓ 驗證B：輸入 symbol="2330" market="TW" 跑完整分析一次，確認有 final_report 輸出
```

### 階段 C：Paperclip 核心
```
C1  建立 backend/core/task_queue.py（Opus 撰寫）
C2  建立 backend/core/budget_guard.py（Sonnet 撰寫）
C3  建立 backend/agents/ceo_agent.py（Opus 撰寫）
C4  建立 backend/core/heartbeat.py（Sonnet 撰寫，Section 12）
C5  建立 backend/agents/infra/storage_curator.py（Sonnet 撰寫，Section 13）
C6  建立 backend/agents/infra/cost_monitor.py（Sonnet 撰寫）

✓ 驗證C：手動呼叫 ceo.hourly_watchlist_scan()，確認 job_queue 有寫入記錄
```

### 階段 D：演進引擎
```
D1  建立 backend/agents/evolution/backtester.py（Opus 撰寫，Section 14）
D2  建立 backend/data/storage/vector_store.py（Sonnet 撰寫）
D3  建立 backend/agents/evolution/memory_agent.py（Sonnet 撰寫）
D4  建立 backend/agents/evolution/prompt_evolver.py（Opus 撰寫）
D5  建立 backend/data/storage/cold_storage.py（Sonnet 撰寫）

✓ 驗證D：手動執行 backtester 一次，確認正確寫入 outcomes 表
```

### 階段 E：API 整合
```
E1  建立 backend/api/routes/analysis.py（Sonnet 撰寫）
E2  建立 backend/api/routes/scanner.py（Sonnet 撰寫）
E3  建立 backend/api/routes/accuracy.py（Sonnet 撰寫，無需登入）
E4  建立 backend/api/routes/watchlist.py（Sonnet 撰寫）
E5  將現有登入邏輯遷移至 backend/api/routes/auth.py
E6  建立 backend/main.py（含 lifespan 啟動 heartbeat）

✓ 驗證E：uvicorn backend.main:app，呼叫 GET /health 回傳 200
         呼叫 GET /api/accuracy 回傳資料（無需 token）
```

### 階段 F：前端
```
F1  cd frontend && npm create vite@latest . -- --template react-ts
F2  npm install @supabase/supabase-js recharts lucide-react
F3  優先建立 Accuracy.tsx（信任建立最重要）
F4  建立 Dashboard.tsx
F5  建立 Analysis.tsx
F6  建立 Scanner.tsx
F7  npm run build 確認無錯誤

✓ 驗證F：npm run dev，四個頁面都能正常顯示
```

### 階段 G：部署
```
G1  建立 Dockerfile（Section 16）
G2  建立 app.py（Section 16）
G3  更新 README.md 加入 YAML header
G4  git add . && git commit -m "feat: DiscoverLatest 2.0 complete rebuild"
G5  git push → 等待 HuggingFace 自動 redeploy

✓ 驗證G：從 HuggingFace URL 輸入 "2330" → 確認完整報告輸出，60 秒內完成
```

---

## 18. 禁止事項（絕對不能做）

1. **禁止**在 `backend/` 程式碼中引入 Anthropic SDK（runtime 只用 Gemini）
2. **禁止**使用舊版 SDK `import google.generativeai as genai`（必須用新版 `from google import genai`）
3. **禁止**直接在各 Agent 呼叫 Gemini，必須透過 `backend/gemini/client.py`
4. **禁止**在封存確認成功前刪除 Supabase 資料
5. **禁止** commit `.env` 檔案
6. **禁止**繞過 `rate_limiter` 直接呼叫 Gemini
7. **禁止**修改 `predictions` 和 `outcomes` 表的欄位結構
8. **禁止**刪除 `_legacy/` 目錄的任何檔案
9. **禁止**升級 yfinance 超過 0.2.59（新版有 bug）

---

## 19. 遇到問題的處理

- **Gemini 429**：自動降級（`FALLBACK_MODEL`），記錄 WARNING
- **Gemini 呼叫失敗**：最多重試 3 次（2s/4s/8s backoff），寫 FAILED 到 job_queue
- **json.loads 失敗**：回傳 `{"parse_failed": True, "raw": ...}`，上層繼續處理
- **Supabase 連線失敗**：記憶體暫存，30 秒後重試
- **HuggingFace 上傳失敗**：本地 Parquet 保留，下次 storage_check 重試
- **前端逾時**：60 秒後顯示「分析需要較長時間，請稍候」

---

## 20. 加速 Pipeline 架構（30-60 秒目標）

> 版本：2.2.0 | 日期：2026-03-20
> 核心改動：並行執行 + SSE Streaming + Fast/Background 雙軌分離

### 20.1 架構總覽

```
舊版 Pipeline（~90s 串行）:
  資料收集 → Stage 1 grounding → Stage 2 合成 → DB 寫入

新版 Pipeline（30-60s 並行 + streaming）:
  ┌─ 資料收集（並行）─┐
  │ Yahoo + FinMind   │ 3-5s
  └────────┬──────────┘
           │
  ┌────────┴──────────────────────┐
  │  6 Agent 全部並行              │ 10-15s（取最慢的）
  │  ├─ Technical  (flash, 無grounding)  │
  │  ├─ Fundamental(flash, 無grounding)  │
  │  ├─ Chips      (flash, 無grounding)  │
  │  ├─ Event      (flash, grounding✅)  │
  │  ├─ Macro      (flash, grounding✅)  │
  │  └─ Sentiment  (flash, grounding✅)  │
  └────────┬──────────────────────┘
           │
  ┌────────┴──────────┐
  │  Arbitrator       │ 8-10s
  └────────┬──────────┘
           │
  ┌────────┴──────────┐
  │  Chief Analyst    │ 10-15s（SSE streaming，TTFT 0.4s）
  │  (streaming 回傳) │
  └────────┬──────────┘
           │
  ── 用戶收到報告 ✅ ──  總計 ~31-45s
           │
  [背景異步] predictions 寫入、audit_log、LINE 通知
```

### 20.2 Fast Path / Background Path 分離

```python
# backend/agents/pipeline.py
async def fast_analysis(symbol: str, market: str) -> AsyncGenerator:
    """Fast Path：使用者等待，目標 30-60 秒"""

    # Step 1: 資料收集（並行）
    price_data, institutional, fundamentals = await asyncio.gather(
        fetch_price_data(symbol, market),
        fetch_institutional_data(symbol, market),
        fetch_fundamental_data(symbol, market),
    )

    # Step 2: 6 Agent 全部並行
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {
            "technical":   pool.submit(TechnicalAgent().analyze, ...),
            "fundamental": pool.submit(FundamentalAgent().analyze, ...),
            "chips":       pool.submit(ChipsAgent().analyze, ...),
            "event":       pool.submit(EventAgent().analyze, ...),
            "macro":       pool.submit(MacroAgent().analyze, ...),
            "sentiment":   pool.submit(SentimentAgent().analyze, ...),
        }
        dept_results = {k: f.result() for k, f in futures.items()}

    # Step 3: Arbitrator
    arbitration = ArbitratorAgent().arbitrate(dept_results)

    # Step 4: Chief Analyst（streaming）
    async for chunk in ChiefAnalystAgent().stream_report(
        dept_results, arbitration, symbol, market
    ):
        yield chunk  # SSE 逐段推送給前端

# 報告完成後啟動背景任務
async def background_tasks(report_data, user_id):
    """Background Path：使用者不等"""
    asyncio.create_task(save_report_to_db(report_data))
    asyncio.create_task(create_predictions(report_data))
    asyncio.create_task(log_agent_actions(report_data))
    asyncio.create_task(notify_line_if_signal(report_data, user_id))
```

### 20.3 SSE Streaming 端點

```python
# backend/api/routes/analysis.py
from fastapi.responses import StreamingResponse

@router.get("/api/analysis/{symbol}")
async def analyze_stock(symbol: str, market: str = "TW"):
    async def event_stream():
        async for chunk in fast_analysis(symbol, market):
            yield f"data: {json.dumps({'type': 'chunk', 'content': chunk})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
```

### 20.4 Gemini Streaming 呼叫

```python
# backend/gemini/client.py 新增
async def call_gemini_streaming(agent_name, prompt, use_grounding=False):
    """Streaming 版本，用於 Chief Analyst"""
    model_name = AGENT_MODEL_MAP.get(agent_name, "gemini-2.5-flash")

    config = types.GenerateContentConfig(temperature=1.0)
    if use_grounding:
        config = types.GenerateContentConfig(
            temperature=1.0,
            tools=[types.Tool(google_search=types.GoogleSearch())]
        )

    async for chunk in _client.models.generate_content_stream(
        model=model_name, contents=prompt, config=config
    ):
        if chunk.text:
            yield chunk.text
```

### 20.5 Grounding 快取

```python
# 同一檔股票同一天的 grounding 結果快取 4 小時
# 快取 key: f"{symbol}_{date}_{agent_type}"
# TTL: 4 hours
# 命中時直接用快取，省 8-12 秒
GROUNDING_CACHE = {}  # 或用 Redis

def get_grounding_cache(symbol, agent_type):
    key = f"{symbol}_{date.today()}_{agent_type}"
    cached = GROUNDING_CACHE.get(key)
    if cached and (time.time() - cached["ts"]) < 14400:  # 4h
        return cached["data"]
    return None
```

### 20.6 時序預估

```
最佳情況（grounding 快取命中）:
  資料 3s + 6 Agent 並行 8s + 仲裁 6s + 報告 streaming 8s = ~25s ✅

一般情況（無快取）:
  資料 4s + 6 Agent 並行 12s + 仲裁 8s + 報告 streaming 12s = ~36s ✅

最差情況（rate limit 降級）:
  資料 5s + 6 Agent 並行 15s + 仲裁 10s + 報告 streaming 15s = ~45s ✅

極端情況（降級 + 重試）:
  ~55-60s ⚠️ 仍在 60s 內
```

### 20.7 需要的新檔案

| 檔案 | 用途 |
|------|------|
| `backend/agents/pipeline.py` | 並行調度器（Fast Path 主邏輯） |
| `backend/core/background_tasks.py` | 背景任務管理 |
| `backend/gemini/cache.py` | Grounding 快取層 |

### 20.8 需要修改的檔案

| 檔案 | 改動 |
|------|------|
| `backend/gemini/client.py` | 新增 `call_gemini_streaming()` |
| `backend/api/routes/analysis.py` | 改為 SSE streaming 端點 |
| `frontend/src/pages/Analysis.tsx` | EventSource 接收 + 漸進渲染 |

---

## 21. 舊系統缺陷評估摘要

> 日期：2026-03-20 | 基於三份獨立 Agent 分析報告整合

### 21.1 後端 Critical 問題

| # | 問題 | 檔案 | 影響 |
|---|------|------|------|
| 1 | `supabase_adapter.py` 是 2253 行 God Object，每次請求建新 HTTP client | adapters/ | 效能 + 可維護性 |
| 2 | `gemini_service.py` 每次呼叫建新 `genai.Client`（6 次實例化） | services/ | 記憶體 + 效能 |
| 3 | IP rate limit 可被 `X-Forwarded-For` 偽造繞過 | services/rate_limiter.py | 安全性 |
| 4 | Auth rate limit 只檢查 `Authorization` header 存在，不驗證 token | services/rate_limiter.py | 安全性 |
| 5 | Yahoo adapter 用已棄用的 `asyncio.get_event_loop()` | adapters/yahoo.py | 穩定性 |
| 6 | `increment_ai_usage` 有 230 行 5 層 fallback（FK 約束不匹配） | adapters/supabase.py | 可維護性 |
| 7 | `time.sleep()` 在 async context 中（阻塞事件迴圈） | services/gemini.py | 效能 |
| 8 | EMA/RSI/safe_num 函式跨 3+ 檔重複定義 | routes + services | 維護性 |

### 21.2 前端 Critical 問題

| # | 問題 | 影響 |
|---|------|------|
| 1 | 目前部署的是空殼 Vite 前端（4 個空頁面） | 用戶看到醜的頁面 |
| 2 | 舊版 Next.js 用 CDN Tailwind（效能災難） | 載入速度 |
| 3 | 字體 Orbitron 不能顯示中文 | 中文全 fallback |
| 4 | analysis 頁 1199 行單檔怪獸 | 不可維護 |
| 5 | api.ts 700+ 行單檔 | 不可維護 |
| 6 | 無共用元件庫（每頁重做 button/card） | 不一致 |
| 7 | 響應式不完整（無平板斷點） | 行動裝置體驗差 |

### 21.3 MiniMax 2.7 評估結論

**維持 Gemini，不切換。** 原因：
- Google Search grounding 是 Gemini 獨有殺手功能（3 個 Agent 依賴）
- MiniMax 免費試用 2026/11 到期後要付費
- Gemini Flash 速度快 3-4 倍（224 vs 48 tok/s）
- 繁中台股術語 Gemini 更精準
- 唯一可用場景：非 grounding Agent 的 fallback

### 21.4 修復策略

**新系統直接避免所有舊版問題：**
- 單例 Gemini Client（不重複建立）
- 正確的 async/await（不用 time.sleep）
- 拆分 God Object 為獨立模組
- Rate limit 用 JWT 驗證而非 header 存在
- 前端：以 Next.js 為基礎遷移至 Vite，保留設計系統
- 字體改回 Noto Sans TC + JetBrains Mono

---

*本 CLAUDE.md 由 Claude (claude-opus-4-6) 於 2026-03-20 更新，版本 2.2.0。*
*新增：加速 Pipeline 架構（Section 20）、舊系統缺陷評估（Section 21）*
*Runtime AI 分析：Gemini API（Free Tier，gemini-2.5-flash 為主力）*
*程式碼撰寫：Opus 4.6（複雜邏輯）+ Sonnet 4.6（其他）*
