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

AI 智慧投資分析平台 — 部署於 Hugging Face Spaces

## 功能一覽

| 功能 | 說明 |
|------|------|
| 市場總覽 | 台/美指數、熱門 ETF 即時看板 |
| 個股分析 | K線圖 (1M~5Y)、基本面、風險指標 |
| SMC/ICT | BOS/CHoCH/OB/FVG/Liquidity 標記與區塊 |
| 策略回測 | 均線/突破/動能/馬丁格爾（含風控） |
| 價格預測 | Naive/ARIMA/Prophet + walk-forward 驗證 |
| 投組管理 | TWD 換算、佔比、健康度、再平衡建議 |
| 產業 + Beta | 產業節點圖、Beta 值分布 |
| Admin | 用戶管理、Key Pool、操作紀錄 |

## 資料來源

- **台股主要**: FinMind
- **台股 K 線備援**: TWSE + TPEX
- **美股主要**: FinMind → 備援 Stooq
- **補強**: Yahoo/yfinance（交叉驗證、補欄位）
- **匯率**: fx_adapter.py (USD/TWD)

## AI 模型

- `gemini-2.5-flash-preview-09-2025` — Grounding 草稿 (含 Google Search)
- `gemini-3-flash-preview` — 最終輸出

## 會員分級

| Tier | 日額度 | 每分鐘 | 輸出上限 |
|------|--------|--------|----------|
| Free | 2 | 1 | 500 字 |
| Pro | 20 | 5 | 2000 字 |
| Premium | 200 | 20 | 5000 字 |

## 模組結構

```
app.py                  # 主程式入口（Multipage 組裝）
adapters/               # 資料來源 Adapter
  finmind_adapter.py    # FinMind (台/美)
  twse_adapter.py       # TWSE 日K
  tpex_adapter.py       # TPEX 日K
  yahoo_adapter.py      # Yahoo/yfinance
  stooq_adapter.py      # Stooq
  fx_adapter.py         # 匯率
  supabase_adapter.py   # Supabase REST
services/               # 業務邏輯
  stock_service.py      # 股票資料整合
  backtest_service.py   # 回測 (含馬丁格爾)
  smc_service.py        # SMC/ICT 分析
  prediction_service.py # 價格預測
  auth_service.py       # Auth + RBAC
  rate_limiter.py       # 限流 + 降級
pages/                  # 頁面
  market_overview.py
  stock_analysis.py
  backtest_page.py
  portfolio.py
  industry_beta.py
  admin_console.py
components/             # UI 元件
  chart_viewer.py       # TradingView LWC
  smc_chart.py          # SMC/ICT 圖表
  sidebar.py / topbar.py / i18n.py
config/                 # 設定
  models.py             # Gemini 模型定義
static/css/             # 樣式
locales/                # i18n (zh-TW, en)
```

## 安全

- Secrets 存放於 Supabase Vault 或 HF Space Secrets
- 任何 Key 禁止出現在 repo / commit history / log
- Admin RBAC 使用 custom claims + RLS
