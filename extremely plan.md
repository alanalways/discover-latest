# DiscoverLatest Codex 46 項全面實施計劃

## Context
將完整計劃存為 `extremely plan.md` 於專案根目錄，然後繼續完成 Phase 1 剩餘項目。

Phase 1 當前進度：
- ✅ F02, F05, F06, F07, F08 — 修復項全部完成
- ✅ B01 Budget Manager — 已建立 + 整合 finmind/gemini
- ✅ B12 降級策略 — 已建立 + 整合 analysis route
- ✅ B02+B03 Tavily 統一管理 — 已建立
- ✅ C01 預測地平線 — 已加 horizon 參數
- ✅ C02+C03 機率模型 — 已建立 + 整合 analysis route
- ✅ C04 Regime 辨識 — 已建立
- ✅ C05 動態權重 — 已整合 market_scanner
- ✅ C16 交易框架 — JSON schema 已更新
- ✅ B09 統一 JSON 輸出 — 已完成
- ✅ N01 新手引導 — 已完成
- ✅ N02 測驗隱藏 — 已完成

### 已完成項目（跳過）
F01, F03, F04, B04, B05, B07 — 共 6 項

### 部分完成（需補強）
F08（前端 admin.ts 硬編碼）、B06（缺 Supabase L2 層）、P01（quiz 未存 DB）

---

## Phase 1（第 1-2 週）：穩定基礎 + 免費額度保命

### F02：Supabase API `from_` → `table` [S]
- `services/stock_service.py` — 全文搜 `from_(` 改 `table(`，補失敗 log

### F05：portfolio/health quota gate [S]
- `routes/watchlist.py` — `include_ai=1` 前加 `acquire_request()` 判斷，超限回 `ai_skipped_reason`

### F06：OAuth redirect_to allowlist [S]
- `routes/auth.py` — 建 `_ALLOWED_REDIRECT_HOSTS`（SPACE_URL + localhost），不通過 fallback 預設

### F07：Frontend lint FullScreenLoader [S]
- `frontend/components/layout/FullScreenLoader.tsx` — render-phase setState 改 useLayoutEffect

### F08：統一 admin email（補完）[S]
- `frontend/lib/admin.ts` — 移除硬編碼，只讀 `NEXT_PUBLIC_ADMIN_EMAILS`

### B01：Budget Manager [M] ⭐ 最重要
- **新建** `services/budget_manager.py`
  - 記憶體 dict 管理 finmind/tavily/gemini 每日預算
  - `check_budget(provider)` / `consume(provider)` / `get_status()`
  - 每 5 分鐘批次寫回 Supabase `api_usage_daily` 表
- 修改 `adapters/finmind_adapter.py` — `_request()` 前 check
- 修改 `services/gemini_service.py` — 呼叫後 consume

### B12：降級策略矩陣 [M]
- **新建** `services/degradation.py`
  - `get_rule_based_verdict(snapshot)` — 純 RSI/EMA 規則引擎
  - `get_degraded_analysis(symbol)` — 讀 SQLite 本地歷史組簡版摘要
- 修改 `routes/analysis.py` — Budget 超限時走降級路徑，前端顯示「基礎模式」

### B02+B03：Tavily 統一管理 [M]
- **新建** `services/tavily_service.py`
  - `search(query, symbol, force=False)` — 快取 6h TTL
  - 事件觸發制：異常波動 >3%、財報日前後才打 API
  - 日預算 110 次（保留 20 緊急）
- 修改 `routes/analysis.py`、`routes/news.py` — 統一入口

---

## Phase 2（第 3-4 週）：核心訊號品質（可量化差異化）

### C01：固定預測地平線 5/20/60d [S]
- `routes/analysis.py` — `AnalysisRequest` 新增 `horizon: int = 20`
- `services/analysis_service.py` — snapshot 加入 horizon 說明

### C02+C03：雙軌機率模型 + 機率輸出 [M]
- **新建** `services/probability_model.py`
  - `compute_prob_up(closes, horizon)` — 歷史同期上漲率 × RSI 位置 × EMA 排列 × 成交量
  - `compute_prob_down(closes, horizon, vol)` — 最大回撤歷史分位 + 波動率
  - `compute_confidence(data_days, vol_consistency)` — 資料完整性 × 指標一致性
  - 純 Python 統計，零 API 消耗
- 修改 `routes/analysis.py` — 回傳 `prob_up/prob_down/confidence`
- 修改 `services/gemini_service.py` — 注入機率到 prompt

### C04：市場 Regime 辨識 [S]
- **新建** `services/regime_detector.py`
  - `detect_regime(index_closes)` → bull/bear/sideways
  - 大盤 vs EMA200 + 20日波動率，快取 24h

### C05：多因子動態權重 [S]
- `services/market_scanner.py` — `SCORING_WEIGHTS` 改為 `get_dynamic_weights(regime)`
  - bull: 動能 0.45 / bear: 防禦 0.40 / sideways: 均衡

### C16：可執行交易框架 [S]
- `services/gemini_service.py` — 強化 JSON schema 要求 `entry_zone/stop_loss/reduce_at/invalidation`
- `routes/analysis.py` — 解析輸出新增 `trade_framework` 欄位

### B09：統一 JSON 輸出格式 [S]
- `services/gemini_service.py` — 用 `response_schema` 參數強制結構化輸出，失敗才 fallback

### N01：新手引導教學提示系統 [M]
- **新建** `frontend/components/onboarding/OnboardingProvider.tsx`
  - React Context 管理 onboarding 狀態
  - `localStorage` 記錄 `dl_onboarding_completed` 和 `dl_onboarding_step`
  - 首次登入的用戶（localStorage 無記錄）自動啟動引導流程
- **新建** `frontend/components/onboarding/FeatureTooltip.tsx`
  - 浮動提示元件（spotlight overlay + tooltip card）
  - Props: `target`（DOM selector）、`title`、`description`、`step`、`totalSteps`
  - 按鈕：「下一步」/「跳過全部」
  - 引導順序（共 7 步）：
    1. 儀表板 — 市場總覽與熱門股票
    2. 自選清單 — 追蹤你關注的股票
    3. 深度分析 — AI 深度分析個股
    4. 回測模擬 — 驗證你的策略
    5. 投資健檢 — 檢視投組風險
    6. AI 次數顯示 — sidebar 的用量卡片
    7. 投資風格測驗 — 引導前往測驗（最後一步，CTA 按鈕直接跳轉 `/quiz`）
- 修改 `frontend/components/layout/ClientLayout.tsx` — 包裹 `<OnboardingProvider>`
- 修改各頁面 — 在關鍵元素加上 `data-onboarding="step-N"` 屬性供 tooltip 定位

### N02：測驗完成後隱藏導覽列測驗項目 [S]
- **後端**：
  - `GET /api/auth/me` 回傳已包含 `user_metadata`，確認 `personality_type` 欄位存在即代表已完成測驗
  - 或 `GET /api/user/profile` 回傳 `quiz_completed: true`
- **前端**：
  - `frontend/components/layout/Sidebar.tsx` — `NAV_ITEMS` 改為動態過濾：
    ```tsx
    const navItems = useMemo(() => {
        return NAV_ITEMS.filter(item => {
            if (item.href === '/quiz' && user?.personality_type) return false;
            return true;
        });
    }, [user]);
    ```
  - 當 `user.personality_type` 有值時（已做過測驗），隱藏「投資風格測驗」項目
  - 測驗入口仍可透過 `/settings` 頁面的「重新測驗」按鈕進入

---

## Phase 3（第 5-6 週）：持倉風險 + 個人化基礎

### C11：投組最佳化 [M]
- **新建** `services/portfolio_optimizer.py`
  - 貪婪算法（<20 檔夠用），考慮相關性、單檔上限 30%、產業上限 40%

### C12：風險約束 MDD/VaR/ES [M]
- **新建** `services/risk_metrics.py`
  - `compute_portfolio_risk()` → MDD 滑動窗口、VaR95% 歷史法、ES 尾部平均
  - 回傳 `risk_traffic_light` (red/yellow/green)

### C13：波動度目標倉位 [S]
- `services/probability_model.py` — `suggest_position_size()` quarter Kelly

### C14：風險歸因 [S]
- `services/risk_metrics.py` — `risk_attribution()` 拆解個股/產業貢獻，top 3

### C15：情境壓力測試 [M]
- **新建** `services/stress_test.py`
  - 4 情境：大盤 -5%/-10%、升息 +1%、單產業 -15%
  - Beta 調整損益

### P01：投資人格檔案（補完）[M]
- Supabase 建 `user_profiles` 表
- `adapters/supabase_adapter.py` — upsert/get profile
- `services/gemini_service.py` — prompt 注入 user risk/horizon/goal

### P04：自訂風險預算 [S]
- `user_profiles` 表加 `single_stock_cap/sector_cap` 欄位
- `risk_metrics.py` — 接受 risk_budget，違反時 breach=true

### P14：新手/專業雙語氣 [S]
- `gemini_service.py` — prompt 加 `{tone}` 變數（beginner/professional）

---

## Phase 4（第 7-8 週）：客製化功能完善

### P02：自訂選股模板 [M]
- Supabase 建 `strategy_templates` 表
- **新建** `routes/user.py` — CRUD endpoints
- `market_scanner.py` — `scan_with_template()` 套用用戶模板

### P03：自訂進出場守則 [M]
- **新建** `services/strategy_templates.py` — 規則 schema

### P05：自訂警報等級與頻率 [M]
- `supabase_adapter.py` — watchlist 表加 `frequency/quiet_start/quiet_end`

### P06：自訂健康分數公式 [S]
- `routes/watchlist.py` — health 接受 `weight_config` 參數

### P07：倉位建議器 [S]
- `probability_model.py` — 擴充 `suggest_position_size()` min/max 參數

### P08：持倉體檢報告 [M]
- `routes/watchlist.py` — `GET /portfolio/checkup`，整合風險歸因

### P09：回撤救援模式 [M]
- `risk_metrics.py` — `check_rescue_trigger()` 比對 max_drawdown 閾值

### P10：交易前檢查清單 [M]
- **新建** `services/pretrade_checker.py` — 5 項檢查（停損/單檔上限/事件窗口/產業集中度/流動性）

### P11：新聞衝擊卡 [M]
- `routes/news.py` — `POST /news/impact-card`
- `gemini_service.py` — `analyze_news_impact()` 結構化輸出

### P12：觀察股升級機制 [M]
- watchlist 加 `status`（observing→candidate→active）+ 自動升級條件

### P13：交易日誌 + 復盤中心 [L]
- Supabase 建 `trade_journal` 表 + CRUD + 歷史查看

---

## Phase 5（第 9-10 週）：訊號閉環 + 多層快取

### C17：警報期望值排序 [S]
- `priority = edge × confidence × liquidity`，排序降序

### C18：訊號事後評分 [M]
- Supabase 建 `signal_history` + `signal_outcomes` 表
- **新建** `services/signal_evaluator.py` — 記錄 + 排程評估 + hit rate dashboard

### C19：Champion-Challenger [M]
- `probability_model.py` — 支援 `model_version`，10% 流量試跑 v2
- 透過 signal_outcomes 比較 Brier score

### C20：SLO + Error Budget [M]
- **新建** `services/slo_monitor.py` — 分析成功率 >95%、P95 延遲 <8s
- `main.py` — 全局 middleware 打點
- `routes/admin.py` — `GET /system/slo-report`

### B06：多層快取 L2 [M]
- Supabase 建 `analysis_cache` 表
- `gemini_service.py` — L1 miss → L2 Supabase 查 → L2 miss 才打 API

### B08：Gemini 分級生成 [S]
- `gemini_service.py` — `analyze_brief()` 150 字短版先回，`?mode=full` 才跑完整

### B10：Supabase 寫入降頻 [S]
- `supabase_adapter.py` — write buffer，threshold 達到才 flush

### B11：離峰預先計算 [S]
- `preloader.py` + `sync_scheduler.py` — 每日 02:00 預算熱門標的訊號

---

## Phase 6（第 11-12 週）：驗證收尾 + 前端效能

### C06：事件風險特徵 [M]
- **新建** `services/event_calendar.py` — 除息/財報日，事件窗口內降 confidence

### C07：Point-in-time 特徵存放 [M]
- `signal_evaluator.py` — record_signal 同存 feature_snapshot JSONB

### C08：Walk-forward 驗證 [L]
- `backtest_service.py` — `walk_forward_backtest()` 6 個月滾動窗口，3 窗格（free tier 降級版）

### C09：機率校準 [M]
- `probability_model.py` — Platt Scaling（純 Python logit 回歸），記錄 Brier score

### C10：回測真實成本 [S]
- `backtest_service.py` — 加 slippage 0.1% + 流動性過濾 + 停牌跳過

### G01：移除 Tailwind CDN [S]
- `frontend/app/layout.tsx` — 移除 Script tag，確認 build-time Tailwind

### G02：重元件 lazy load [M]
- `frontend/app/analysis/page.tsx`、`portfolio/page.tsx` — dynamic import + skeleton

### G04：React Query 快取 [S]
- `frontend/lib/` — query client + staleTime 60s

### G06：全路由打點 [S]
- `main.py` — middleware 記錄 endpoint/latency/success，超 1s 寫 slow log

---

## Supabase 建表清單

Phase 1 前執行：`api_usage_daily`
Phase 3 前執行：`user_profiles`
Phase 4 前執行：`strategy_templates`、`trade_journal`
Phase 5 前執行：`signal_history`、`signal_outcomes`、`analysis_cache`

---

## 依賴關係

```
B01 (Budget Manager) ──→ 所有 Phase 2-6 依賴
C01 ──→ C02/C03 (先有 horizon 才有機率)
C02/C03 ──→ C13/C17 (機率是後續輸入)
C04 ──→ C05 (先有 regime 才有動態權重)
C12 ──→ C14/C15 (風險指標是歸因/壓測輸入)
P01 ──→ P03/P04/P06/P07/P09 (人格先建才有客製化依據)
N01 (引導系統) ──→ N02 (測驗隱藏依賴引導最後一步指向 quiz)
N02 ──→ 依賴 user.personality_type（P01 quiz 儲存後才有值）
C18 (signal_history) ──→ C19/C09 (需歷史訊號才校準)
C07 ──→ C08 (PIT 先確保才能 walk-forward)
```

---

## 新建檔案清單（共 15 個）

| 檔案 | Phase | 用途 |
|------|-------|------|
| `services/budget_manager.py` | 1 | 全 API 統一控額 |
| `services/degradation.py` | 1 | 降級策略矩陣 |
| `services/tavily_service.py` | 1 | Tavily 統一管理 |
| `services/probability_model.py` | 2 | 雙軌機率模型 |
| `services/regime_detector.py` | 2 | 市場狀態辨識 |
| `frontend/components/onboarding/OnboardingProvider.tsx` | 2 | 新手引導狀態管理 |
| `frontend/components/onboarding/FeatureTooltip.tsx` | 2 | 浮動教學提示元件 |
| `services/portfolio_optimizer.py` | 3 | 投組最佳化 |
| `services/risk_metrics.py` | 3 | MDD/VaR/ES/歸因 |
| `services/stress_test.py` | 3 | 情境壓力測試 |
| `services/pretrade_checker.py` | 4 | 交易前檢查清單 |
| `services/strategy_templates.py` | 4 | 進出場規則管理 |
| `services/signal_evaluator.py` | 5 | 訊號記錄與事後評分 |
| `services/slo_monitor.py` | 5 | SLO 監控 |
| `routes/user.py` | 4 | 用戶個人設定路由 |

---

## 驗證方式
1. 每個 Phase 完成後：`python -c "import services.xxx; print('OK')"` 確認 import
2. 每個新 endpoint：curl 測試 + 前端整合確認
3. Budget Manager：模擬超限場景，確認降級策略觸發
4. 機率模型：用歷史資料回測 hit rate，與隨機基準比較
5. 每週跑 KPI 8 項數字，追蹤趨勢
6. N01 新手引導：清除 localStorage 後重新載入，確認 7 步引導流程完整
7. N02 測驗隱藏：完成測驗後重新載入，確認 sidebar 無「投資風格測驗」項目
