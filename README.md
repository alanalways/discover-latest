---
title: DiscoverLatest 洞察運算 v3.0
emoji: 📈
colorFrom: blue
colorTo: purple
sdk: docker
app_file: app.py
pinned: true
license: mit
---

# DiscoverLatest 洞察運算 v3.0

AI 智慧投資分析平台 — Next.js 前端 + FastAPI 後端，部署於 Hugging Face Spaces

## 核心功能

### 市場與研究
| 功能 | 說明 |
|------|------|
| 市場總覽 | 台/美指數、熱門 ETF、Top 20 漲跌幅即時看板 |
| 個股分析 (Dexter AI) | 雙階段 AI 分析：Grounding 搜尋 → 深度研報產出 |
| AI 研究助手 | Gemini + Google Search grounding 即時對話 |
| 新聞摘要 | AI 自動彙整台股/美股重點新聞 |
| 經濟日曆 | FOMC、CPI、NFP、GDP、財報季等重要事件追蹤 |

### 工具與策略
| 功能 | 說明 |
|------|------|
| 智能選股 | PE、殖利率、漲跌幅、成交量多條件篩選（台股 30 / 美股 30） |
| 策略回測 | 均線交叉 / RSI / 突破 / 動能 / 馬丁格爾，含 DCA 與風控 |
| 策略排行榜 | 預設 8 種策略一鍵跑分，依報酬率排名 |
| 投組壓力測試 | 模擬 5 種歷史危機情境對持股的衝擊（金融海嘯、COVID、升息等） |
| 股票比較 | 多股同圖對比 + 雷達圖 + AI 比較分析 |

### 投資組合
| 功能 | 說明 |
|------|------|
| 投組管理 | TWD/USD 換算、佔比、健康度、再平衡建議 |
| 紙上交易 | 模擬買賣，追蹤持倉損益與報酬率 |
| 關注清單 | 自選股即時報價監控 |
| AI 投資報告 | 根據關注清單自動生成個人化週報/月報 |

### 進階分析
| 功能 | 說明 |
|------|------|
| SMC/ICT 分析 | BOS / CHoCH / OB / FVG / Liquidity 標記 |
| 加密貨幣 | 主流幣種行情追蹤 |
| 投資風格測驗 | 評估個人風險偏好 |
| Admin Console | 用戶管理、Key Pool 監控、操作紀錄 |

## 技術架構

```
┌─────────────────────────────────────────────────┐
│  Frontend — Next.js 16 (Static Export)          │
│  React 19 · TypeScript · Lucide Icons           │
│  TradingView Lightweight Charts v5              │
├─────────────────────────────────────────────────┤
│  Backend — FastAPI + Uvicorn                    │
│  21 API Route Modules · Async I/O               │
│  Gemini AI (google-genai SDK)                   │
├─────────────────────────────────────────────────┤
│  Data Layer                                     │
│  FinMind (台/美股) · TWSE · TPEX · Stooq        │
│  Yahoo/yfinance · Supabase (Auth + DB)          │
└─────────────────────────────────────────────────┘
```

## AI 模型

| 用途 | 模型 | 說明 |
|------|------|------|
| Grounding 搜尋 | `gemini-2.5-flash` | Google Search grounding，500 RPD free tier |
| 深度分析 / 報告 | `gemini-3-flash-preview` | 最終研報輸出、AI 週報月報 |
| Dexter 研究員 | `gemini-3-flash-preview` | 雙階段分析 agent |

所有模型名稱統一定義於 `config/models.py`，禁止散落各處。

## 資料來源

| 來源 | 用途 |
|------|------|
| FinMind | 台股/美股主要資料源（價格、基本面、法人） |
| TWSE + TPEX | 台股 K 線備援 |
| Stooq | 美股備援 |
| Yahoo/yfinance | 交叉驗證、補充欄位 |
| fx_adapter | USD/TWD 匯率 |
| Supabase | 用戶認證 (Google OAuth)、Watchlist、設定儲存 |

## 會員分級

| Tier | AI 日額度 | 每分鐘 | 輸出上限 | 回測年限 |
|------|-----------|--------|----------|----------|
| Free | 2 | 1 | 500 字 | 1 年 |
| Pro | 20 | 5 | 2000 字 | 3 年 |
| Premium | 200 | 20 | 5000 字 | 無限 |

## 專案結構

```
main.py                     # FastAPI 入口，21 route modules 組裝
Dockerfile                  # Multi-stage: Node build → Python runtime

frontend/                   # Next.js 16 前端
  app/                      # 17 頁面 (market, analysis, chat, screener, ...)
  components/               # 共用元件 (Auth, Charts, Sidebar, Onboarding)
  lib/                      # API client, auth helpers

routes/                     # FastAPI API 路由 (21 modules)
  auth.py                   # Google OAuth + Supabase session
  market.py / news.py       # 市場總覽、新聞
  stock.py / analysis.py    # 個股資料、分析
  dexter.py                 # Dexter AI 雙階段分析
  chat.py                   # AI 研究助手 (Gemini + Google Search)
  screener.py               # 智能選股篩選
  backtest.py               # 策略回測
  paper_trade.py            # 紙上交易
  stress.py                 # 壓力測試
  calendar.py               # 經濟日曆
  report.py                 # AI 投資報告
  watchlist.py              # 關注清單
  crypto.py                 # 加密貨幣
  billing.py / admin.py     # 計費、管理後台

services/                   # 業務邏輯 (30+ modules)
  gemini_service.py         # Gemini AI 統一入口 (key pool + cache + lock)
  stock_service.py          # 股票資料整合 (async, multi-source fallback)
  backtest_service.py       # 回測引擎
  smc_service.py            # SMC/ICT 技術分析
  rate_limiter.py           # 限流 + 自動降級
  auth_service.py           # 認證 + RBAC

adapters/                   # 外部資料 Adapter (14 modules)
  finmind_adapter.py        # FinMind API (台/美)
  supabase_adapter.py       # Supabase REST
  twse_adapter.py / tpex_adapter.py / stooq_adapter.py / yahoo_adapter.py

config/                     # 設定
  models.py                 # Gemini 模型名稱定義（唯一來源）
static/css/                 # 樣式
locales/                    # i18n (zh-TW, en)
```

## 部署

- **平台**: Hugging Face Spaces (Docker SDK)
- **建置**: Multi-stage Dockerfile — Stage 1 build Next.js → Stage 2 Python runtime
- **推送**: `git push hf main:main`

## 安全

- Secrets 存放於 Supabase Vault 或 HF Space Secrets
- 任何 Key 禁止出現在 repo / commit history / log
- Admin RBAC 使用 Supabase RLS + custom claims
- 所有用戶輸入經過 `html.escape` 防 XSS
