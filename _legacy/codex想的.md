# codex想的：Discover Latest 詳細執行規格

## 0. 目標與限制

### 0.1 產品目標
- 讓新手也能看懂「上漲機率、下跌風險、持倉健康」。
- 讓進階用戶可自訂規則、權重、風險預算。
- 在免費額度下維持穩定可用、可擴充、可驗證成效。

### 0.2 已知資源限制（依你提供）
- Hugging Face: free tier。
- Gemini API: free tier。
- Supabase: free tier。
- Tavily: 每月 `4000 credits`。
- FinMind: 每小時 `1200`（雙 key）。

---

## 1. 先決修復（先做，不然後續功能會失真）

### F01. 修正 FinMind 搜尋快取變數未定義
- 要做什麼:
  1. 在 `adapters/finmind_adapter.py` 定義 `_stock_info_cache`、`_STOCK_INFO_CACHE_TTL`。
  2. `search_tw_stocks()` 讀寫快取時加鎖（或最少保證 dict 結構固定）。
  3. 失敗時回傳空陣列，不要讓 NameError 吞掉整個流程。
- 放在哪:
  - `adapters/finmind_adapter.py`
- 驗收標準:
  - `stock_service.search_symbols("2330")` 不再出現 NameError。

### F02. 修正 Supabase API 呼叫介面不一致（`from_` -> `table`）
- 要做什麼:
  1. 將 `services/stock_service.py` 的 `get_client().from_(...)` 改為 `get_client().table(...)`。
  2. 檢查 chained query 是否可對應（`select/eq/gte/order/limit/upsert`）。
  3. 補上失敗 log（symbol + query）避免靜默失敗。
- 放在哪:
  - `services/stock_service.py`
  - `adapters/supabase_adapter.py`（必要時補 query builder）
- 驗收標準:
  - DB fallback 可以查到 `symbol_index`、`stock_daily`。

### F03. 修正 `rpc_call` 方法不存在
- 要做什麼:
  1. `supabase_data.py` 改用 `supabase_adapter._rpc(...)` 或新增公開 `rpc_call()` 包裝。
  2. 統一 adapter 對外 API 命名，避免 `_` 私有方法外漏。
- 放在哪:
  - `adapters/supabase_data.py`
  - `adapters/supabase_adapter.py`
- 驗收標準:
  - `get_investor_profile(user_id)` 可正常命中 RPC。

### F04. 配額流程改成原子操作
- 要做什麼:
  1. `routes/analysis.py`、`routes/crypto.py`、`routes/dexter.py` 由 `can_make_request()+record_request()` 改成 `acquire_request()`。
  2. 失敗回傳統一 429 結構（`code`, `message`, `retry_hint`）。
  3. 只在「成功產出可用結果」時扣點。
- 放在哪:
  - `routes/analysis.py`
  - `routes/crypto.py`
  - `routes/dexter.py`
  - `services/rate_limiter.py`
- 驗收標準:
  - 壓測下同帳號不會超扣。

### F05. `portfolio/health?include_ai=1` 先檢查配額再扣點
- 要做什麼:
  1. include AI 前先做 tier gate + quota gate。
  2. 回傳內含 `ai_skipped_reason`（超限時給可讀提示）。
- 放在哪:
  - `routes/watchlist.py`
- 驗收標準:
  - include_ai 超限時不扣點、且有清楚提示。

### F06. OAuth `redirect_to` allowlist
- 要做什麼:
  1. 只允許 `SPACE_URL` 與本地測試白名單域名。
  2. 不在白名單就 fallback 到預設 callback。
  3. `auth/diagnose` 顯示當前有效 allowlist。
- 放在哪:
  - `routes/auth.py`
- 驗收標準:
  - 任意第三方 URL 無法帶入 OAuth redirect。

### F07. 修正前端 lint blocker（FullScreenLoader）
- 要做什麼:
  1. 避免 effect 內同步 setState 的模式，改成 derived state 或 transition callback。
  2. 確保 `npm run lint` 無 error。
- 放在哪:
  - `frontend/components/layout/FullScreenLoader.tsx`
- 驗收標準:
  - `npm run lint --prefix frontend` 無 error。

### F08. 統一 admin email 預設值
- 要做什麼:
  1. 後端與前端共用一個 env key（例如 `ADMIN_EMAILS`）。
  2. 移除硬編碼 gmail 預設。
- 放在哪:
  - `routes/admin.py`
  - `routes/auth.py`
  - `frontend/lib/admin.ts`
- 驗收標準:
  - 同一帳號在前後端 admin 判斷一致。

---

## 2. 核心 20 項（股票分析、持倉分析、上漲潛力、下跌風險）

### C01. 固定預測地平線（5/20/60 日）
- 要做:
  1. label 分離：`ret_5d`, `ret_20d`, `ret_60d`。
  2. API 增加 `horizon` 參數。
  3. UI 清楚標示「此訊號對應幾天」。
- 驗收:
  - 每個 horizon 各自有回測報告。

### C02. 上漲機率模型 + 下跌風險模型雙軌
- 要做:
  1. 模型 A 預測 `P(up)`。
  2. 模型 B 預測 `P(drawdown > X%)`。
  3. 合成訊號時同時顯示兩者。
- 驗收:
  - 每支股票頁都有上漲/下跌雙機率。

### C03. 輸出機率而非單一分數
- 要做:
  1. API 回傳 `prob_up`, `prob_down`, `confidence`。
  2. 前端加入可信度條與資料完整度標記。
- 驗收:
  - 使用者可看到「機率 + 信心」而非黑箱分數。

### C04. 市場狀態辨識（Regime）
- 要做:
  1. 定義 regime：bull/bear/sideways。
  2. 每日計算市場 regime 後寫入快取。
  3. 不同 regime 套不同權重。
- 驗收:
  - 訊號 payload 包含 `market_regime`。

### C05. 多因子動態權重
- 要做:
  1. 因子群：成長、估值、動能、品質、風險。
  2. 可依 regime 或用戶偏好動態調整權重。
  3. 分數拆解可視化（看得到每因子貢獻）。
- 驗收:
  - 股票詳情頁可看到因子貢獻比例。

### C06. 事件風險特徵
- 要做:
  1. 事件表：財報、法說、除息、政策、重大新聞。
  2. 事件前後波動特徵納入模型。
  3. 事件視窗內提高風險提醒等級。
- 驗收:
  - 事件日前後策略有不同風險建議。

### C07. Point-in-time 特徵存放
- 要做:
  1. 每個特徵記錄 `as_of_time`。
  2. 禁止回測使用未來資料。
  3. 建立資料快照版本。
- 驗收:
  - 回測與線上結果時間一致性可追溯。

### C08. Walk-forward 驗證
- 要做:
  1. 時序切分訓練/驗證，不使用隨機切分。
  2. 每個窗格產生報告與平均結果。
- 驗收:
  - 模型頁可查看多窗格績效穩定性。

### C09. 機率校準（Calibration）
- 要做:
  1. 對分類輸出做 Platt/Isotonic 校準。
  2. 存 calibration curve 與 Brier score。
- 驗收:
  - 70% 訊號的實際命中率接近 70%。

### C10. 回測納入真實成本
- 要做:
  1. 交易成本、滑價、最小成交量過濾。
  2. 加入不可交易條件（停牌、流動性低）。
- 驗收:
  - 回測收益較保守且與實盤更接近。

### C11. 投組層最佳化
- 要做:
  1. 不只挑高分股，還考慮相關性。
  2. 有持倉上下限與產業上限。
- 驗收:
  - 建議投組有權重且總和 100%。

### C12. 風險約束（MDD / VaR / ES）
- 要做:
  1. 每日更新風險指標。
  2. 違反風險預算時觸發降風險建議。
- 驗收:
  - 投組頁有即時風險燈號。

### C13. 波動度目標倉位
- 要做:
  1. 以近期年化波動反推建議倉位。
  2. 高波動自動降倉，低波動放寬倉位。
- 驗收:
  - 每檔顯示 `recommended_position_size`。

### C14. 風險歸因
- 要做:
  1. 拆解回撤來源（個股/產業/因子）。
  2. 顯示「哪一檔最拖累」。
- 驗收:
  - 投組診斷能列出 top 3 風險來源。

### C15. 情境壓力測試
- 要做:
  1. 內建情境：大盤 -5/-10、升息、單產業衝擊。
  2. 顯示各情境損益與最大回撤。
- 驗收:
  - 用戶可一鍵跑至少 3 種情境。

### C16. 可執行交易框架
- 要做:
  1. 每檔輸出進場區、停損位、減碼位、失效條件。
  2. 所有建議都附理由與風險。
- 驗收:
  - 訊號卡片不只「看多/看空」，有具體行動。

### C17. 警報按期望值排序
- 要做:
  1. `priority = edge * confidence * liquidity`。
  2. 高優先通知先推播。
- 驗收:
  - 每日通知量下降，但有效訊號比例提升。

### C18. 訊號事後評分（7/30/90）
- 要做:
  1. 訊號建立後自動排程評估結果。
  2. 回寫命中、報酬、最大不利波動。
- 驗收:
  - 每個策略有真實 hit rate dashboard。

### C19. Champion-Challenger
- 要做:
  1. 新舊模型並行，部分流量試跑 challenger。
  2. 只在統計顯著優於舊模型時切換。
- 驗收:
  - 模型切版有可追溯決策紀錄。

### C20. SLO + Error Budget
- 要做:
  1. 定義 SLO：分析成功率、P95 延遲、資料新鮮度。
  2. 超出錯誤預算時暫停新功能上線。
- 驗收:
  - 每週固定輸出 SLO 報告。

---

## 3. 客製化 14 項（做出差異化）

### P01. 自訂投資人格檔案
- 要做:
  1. `risk_level`, `horizon`, `goal_return`, `max_drawdown`。
  2. 初次導引問答建立 profile。
- 驗收:
  - 同一股票，不同人格得到不同建議。

### P02. 自訂選股配方模板
- 要做:
  1. 儲存權重與篩選條件（可多模板）。
  2. 支援一鍵套用與分享模板。
- 驗收:
  - 至少可儲存 3 組個人模板。

### P03. 自訂進出場守則
- 要做:
  1. 停損%、停利%、移動停損、分批規則。
  2. 訊號與守則衝突時顯示警告。
- 驗收:
  - 交易前檢查可攔截違規操作。

### P04. 自訂風險預算
- 要做:
  1. 單檔上限、產業上限、總風險上限。
  2. 超標自動產生再平衡建議。
- 驗收:
  - 投組頁可視化風險預算使用率。

### P05. 自訂警報等級與頻率
- 要做:
  1. 即時、日報、週報 + 安靜時段。
  2. 支援不同事件類型不同頻率。
- 驗收:
  - 通知可控，且不漏重大事件。

### P06. 自訂持倉健康分數公式
- 要做:
  1. 用戶可調集中度/波動/回撤權重。
  2. 立即重算健康分數。
- 驗收:
  - UI 變更權重後分數即時更新。

### P07. 倉位建議器（依信心與風險）
- 要做:
  1. 根據 `prob_up`, `prob_down`, `volatility` 給倉位倍數。
  2. 可設定上限與最小倉位。
- 驗收:
  - 每次建議附建議倉位百分比。

### P08. 持倉體檢報告
- 要做:
  1. 顯示績效貢獻、風險貢獻、低效率資產。
  2. 提供調整建議與預期效果。
- 驗收:
  - 一頁可看到「該減碼/加碼」名單。

### P09. 回撤救援模式
- 要做:
  1. 達到預設回撤門檻啟動防守策略。
  2. 自動降低高風險部位。
- 驗收:
  - 觸發後有清楚的防守動作清單。

### P10. 交易前檢查清單
- 要做:
  1. 檢查是否違反個人規則與平台風控。
  2. 未通過時顯示修正建議。
- 驗收:
  - 所有操作前都能執行 pre-trade check。

### P11. 新聞衝擊卡
- 要做:
  1. 將新聞轉為結構化：事件、影響方向、受影響標的。
  2. 顯示可驗證觀察指標。
- 驗收:
  - 每則重大新聞都有「可觀察條件」。

### P12. 觀察股升級機制
- 要做:
  1. watchlist 分層：觀察中 -> 候選 -> 行動中。
  2. 達條件自動升級。
- 驗收:
  - 用戶可看到升級原因與歷史。

### P13. 交易日誌 + 復盤中心
- 要做:
  1. 每次決策記錄當時訊號與理由。
  2. 事後比較「有無照建議執行」差異。
- 驗收:
  - 至少可回看最近 90 天復盤。

### P14. 新手/專業雙語氣模式
- 要做:
  1. 新手版：白話 + 少指標。
  2. 專業版：完整因子與風險數據。
- 驗收:
  - 同一內容可切換兩種呈現深度。

---

## 4. 免費額度最佳化 12 項（你目前環境最重要）

### B01. Budget Manager（全 API 統一控額）
- 要做:
  1. 建 `api_usage_daily`（provider, date, used, limit, reserved）。
  2. 每次外部請求先經 budget 檢查。
  3. 不足時走降級策略。
- 驗收:
  - 月底不會突然全平台失效。

### B02. Tavily 配額日切分
- 要做:
  1. `4000/月` 切成約 `110/日`，保留 `20-25/日` 緊急預算。
  2. 非必要查詢改讀快取摘要。
- 驗收:
  - 任一天用量超限時仍有保底可用量。

### B03. Tavily 事件觸發制
- 要做:
  1. 只有「重大事件/異常波動/使用者手動深查」才打 Tavily。
  2. 一般行情不查外部新聞。
- 驗收:
  - Tavily 消耗下降，關鍵查詢命中率上升。

### B04. FinMind 令牌桶限流
- 要做:
  1. 每小時上限設定 `1000`，保留 `200` 應急。
  2. 以 symbol + date range 做去重查詢。
- 驗收:
  - 不觸發 FinMind 429/封鎖。

### B05. FinMind 雙 key 輪替
- 要做:
  1. key A/B 輪流發送。
  2. 某 key 失敗自動切換 + 指數退避。
- 驗收:
  - 單 key 異常不影響整體可用性。

### B06. 多層快取（記憶體 + Supabase）
- 要做:
  1. 短 TTL（1-10 分鐘）放記憶體。
  2. 長 TTL（1-24 小時）放 Supabase 表。
  3. 熱門標的預先暖快取。
- 驗收:
  - 尖峰時段外部 API 請求量顯著下降。

### B07. Gemini 結果快取
- 要做:
  1. cache key: `symbol + horizon + regime + prompt_version`。
  2. 相同請求直接回快取結果。
- 驗收:
  - 重複請求 token 消耗顯著降低。

### B08. Gemini 分級生成
- 要做:
  1. 先產出短版（結論 + 風險）。
  2. 使用者點開才產長版（完整解釋）。
- 驗收:
  - 平均每次 token 成本下降。

### B09. 統一 JSON 輸出格式
- 要做:
  1. prompt 嚴格要求 JSON schema。
  2. parse 失敗才 fallback 自然語言解析。
- 驗收:
  - 解析失敗率下降，重試次數下降。

### B10. Supabase 寫入降頻
- 要做:
  1. 高頻事件先聚合後批次寫入。
  2. 非必要 log 不落 DB，改本地/快取指標。
- 驗收:
  - DB 寫入次數下降，響應更穩定。

### B11. 離峰預先計算
- 要做:
  1. 每日固定時間預先算熱門標的特徵與摘要。
  2. 白天請求以讀取為主。
- 驗收:
  - 白天高峰延遲下降。

### B12. 降級策略矩陣
- 要做:
  1. FinMind 超限 -> 用 DB 歷史 + 技術面簡版。
  2. Tavily 超限 -> 用近期快取新聞摘要。
  3. Gemini 超限 -> 用規則引擎模板輸出。
- 驗收:
  - 任一供應商超限時服務仍有可讀結果。

---

## 5. 建議資料表（Supabase）

### 5.1 必加表
- `user_profiles`:
  - `user_id`, `risk_level`, `horizon_pref`, `max_drawdown`, `goal_return`, `updated_at`
- `strategy_templates`:
  - `id`, `user_id`, `name`, `factor_weights(jsonb)`, `entry_rules(jsonb)`, `exit_rules(jsonb)`
- `signal_history`:
  - `id`, `symbol`, `horizon`, `prob_up`, `prob_down`, `confidence`, `regime`, `created_at`
- `signal_outcomes`:
  - `signal_id`, `ret_7d`, `ret_30d`, `ret_90d`, `max_adverse_excursion`, `hit`
- `api_usage_daily`:
  - `provider`, `date`, `used`, `limit`, `reserved`, `updated_at`
- `analysis_cache`:
  - `cache_key`, `payload`, `ttl_until`, `source`, `created_at`

### 5.2 索引建議
- `signal_history(symbol, created_at desc)`
- `signal_history(horizon, created_at desc)`
- `analysis_cache(cache_key)`
- `api_usage_daily(provider, date)`

---

## 6. API 端點擴充建議

### 6.1 核心分析
- `GET /analysis/signal?symbol=2330&horizon=20`
- `GET /analysis/risk-map?symbol=2330`
- `POST /analysis/stress-test`

### 6.2 持倉分析
- `POST /portfolio/health`（保留，補 quota gate 與風險輸出）
- `POST /portfolio/rebalance-suggest`
- `GET /portfolio/risk-attribution`

### 6.3 客製化
- `GET/PUT /user/profile`
- `GET/POST/PUT /user/templates`
- `GET/PUT /user/alerts-config`

### 6.4 配額與可靠性
- `GET /system/budget-status`
- `GET /system/slo-report`

---

## 7. 8 週落地順序（務實版）

### 第 1-2 週（先穩定）
- 完成 F01~F08。
- 上線 B01, B04, B05, B12（先保命）。

### 第 3-4 週（先能看出價值）
- 完成 C01, C02, C03, C16。
- 完成 P01, P02（人格 + 模板）。

### 第 5-6 週（持倉與風險）
- 完成 C11, C12, C14, C15。
- 完成 P04, P08, P10。

### 第 7-8 週（成效閉環）
- 完成 C18, C19, C20。
- 完成 B02, B03, B06, B07, B08, B09, B10, B11。

---

## 8. KPI（你要追的成效）

### 8.1 訊號品質
- 7/30/90 日 hit rate。
- 分 horizon 的年化報酬與最大回撤。
- 機率校準誤差（Brier score）。

### 8.2 產品體驗
- 新手首日留存、7 日留存。
- 平均分析延遲（P95）。
- 訊號被採納率（點擊與執行）。

### 8.3 成本與配額
- Tavily 日均消耗與月底剩餘。
- FinMind 每小時用量峰值。
- Gemini 平均每次 token 成本。

---

## 9. 最小可行版本（MVP）清單

若你要最快看到成果，先做這 10 個:
1. F01, F02, F04, F05（修穩定與配額正確性）
2. B01, B04, B05, B12（先控成本與防中斷）
3. C01, C02（先做可量化的上漲/下跌雙機率）

這 10 個完成後，你的平台就會從「功能很多」進到「可穩定、可驗證、可持續優化」。

---

## 10. 系統整體瀏覽加速優化探討（你現在「感覺很慢」的主因與解法）

這一章是針對你目前架構（FastAPI + Next.js + Supabase + FinMind + Tavily + Gemini，且多為 free tier）設計的「務實加速方案」。

### 10.1 先定義「慢」到底發生在哪裡

不要只看主觀感受，先拆成可量測指標：
- `TTFB`：前端發請求到收到第一個 byte 的時間。
- `API Latency`：後端 endpoint 的處理時間（P50 / P95 / P99）。
- `Data Freshness Delay`：資料從來源更新到你平台可用的延遲。
- `Render Blocking Time`：前端主執行緒被 JS/blocking work 卡住的時間。
- `Cold Start Time`：Hugging Face free tier 休眠後喚醒時間。

建議先訂目標值：
- 主要頁面首屏可互動：`< 2.5s`
- 非 AI API（watchlist/portfolio 基礎資料）P95：`< 800ms`
- AI API 首段回應（stream start）：`< 1.2s`
- AI 完整回覆（短版）：`< 6s`

### 10.2 前端加速（體感最快見效）

#### G01. 拆掉 runtime Tailwind CDN，改 build-time CSS
- 現況風險：`frontend/app/layout.tsx` 載入 `https://cdn.tailwindcss.com`，每次首屏多一次外部阻塞。
- 解法：只用本地編譯後 CSS（你已有 `globals.css` 流程）。
- 效果：首屏阻塞下降，LCP 通常改善明顯。

#### G02. 把重元件改成 lazy load
- 目標元件：圖表、長表格、AI 分析詳情區塊。
- 解法：`dynamic import` + skeleton；首屏先顯示核心資訊。
- 效果：JS bundle 體積下降，互動時間提早。

#### G03. 請求去瀑布化（waterfall -> parallel）
- 現況常見問題：先拿 A 再打 B 再打 C。
- 解法：能平行的資料全部平行拿（`Promise.all`），可延後的延後。
- 效果：同一頁總等待時間接近最慢那支 API，而不是總和。

#### G04. 統一快取策略（SWR/React Query）
- 解法：熱門資料（watchlist、market overview）設定 `staleTime`。
- 搭配：切頁返回不重抓；手動 refresh 才強制更新。
- 效果：重複瀏覽體感提升很大。

#### G05. 降低 payload
- 解法：後端回傳列表時只給卡片必要欄位，詳情再查。
- 效果：網路與解析時間都下降。

### 10.3 後端加速（FastAPI 層）

#### G06. 全路由打點（先量測再優化）
- 每支 endpoint 記錄：`request_id`, `db_ms`, `external_ms`, `ai_ms`, `total_ms`。
- 設 `slow log`：超過 1s 就記完整細節。
- 沒打點就無法知道瓶頸真因。

#### G07. 外部 API 呼叫統一改「連線池 + 重用」
- 目標：避免每次建立新連線，減少 TLS/握手成本。
- 解法：集中 `httpx` client（含 timeout/retry/backoff）。
- 效果：外部請求延遲更穩定，尖峰下更明顯。

#### G08. 熱門查詢結果快取 + 請求合併
- 例：同時 10 人查 `2330, 20d`，只打一支外部請求，其餘等同一結果。
- 快取 key：`symbol+horizon+regime+data_version`。
- 效果：高峰時 API 速度和成本同時改善。

#### G09. 基礎版與 AI 版分離回應
- 解法：先回基礎技術面/估值摘要（快），AI 深度分析異步補上。
- 介面：前端先渲染基礎卡片，再 streaming AI 段落。
- 效果：使用者不會感覺卡住。

### 10.4 Supabase / 資料層優化

#### G10. 查詢索引補齊
- 重點索引：
  - `stock_daily(symbol, date)`
  - `symbol_index(symbol)`
  - 使用者資料表 `user_id, created_at`
- 效果：歷史資料查詢顯著加速。

#### G11. 避免 N+1 查詢
- 問題：每檔持倉都各打一支 DB/API。
- 解法：批次查（一次拿多 symbol），記憶體 join。
- 效果：持倉頁從多秒降到次秒級的常見手段。

#### G12. Materialized/預聚合資料
- 例：market overview、熱門榜、指標摘要每日/每小時預算。
- 用戶打開頁面先吃預聚合結果，背景再更新。
- 效果：首頁與總覽頁延遲大幅下降。

### 10.5 在免費額度下的速度與成本平衡（關鍵）

#### G13. FinMind：1200/h 不要用滿，控在 70~85%
- 建議內控：`1000/h` 封頂，預留突發。
- 雙 key 輪替 + 短 TTL 快取（5~15 分鐘）+ 長 TTL（1~24 小時）。
- 效果：避免超限抖動導致整體慢。

#### G14. Tavily：4000/月做事件觸發制
- 只有「重大事件」才查即時新聞，平常讀快取摘要。
- 日預算建議：`110/day` + `20/day reserve`。
- 效果：月底不會斷糧，且關鍵查詢仍可即時。

#### G15. Gemini：兩段式生成
- 第 1 段：短版結論（快速回應）。
- 第 2 段：展開分析（使用者展開才觸發）。
- 搭配固定 JSON schema，減少重試。
- 效果：速度、穩定、成本三者平衡。

### 10.6 Hugging Face free tier 的冷啟動現實

#### G16. 冷啟動處理策略
- 事實：free tier 可能休眠，首次請求會慢。
- 做法：
  1. 前端偵測初次慢啟動時顯示「喚醒中」狀態。
  2. 首次只載入必要 API，次要資料延後。
  3. 用快取資料先渲染，避免空白等待。
- 效果：把「不可避免的慢」轉成「可理解、可接受」。

### 10.7 前後端協同（最容易被忽略）

#### G17. API 分級
- A 級（<300ms）：靜態/快取資料
- B 級（<800ms）：一般查詢
- C 級（可 streaming）：AI/重運算
- UI 依級別採不同 loading 策略。

#### G18. 取消無效請求
- 使用者快速切換 symbol/horizon 時，前一個請求要 abort。
- 避免伺服器算完用不到的結果。

#### G19. 同頁資料共用
- 同一頁多元件用同一份 query cache，不要各自打 API。
- 對 watchlist / portfolio 影響很大。

### 10.8 你專案可直接執行的「兩階段加速計畫」

#### Phase A（1~2 週，先把體感拉起來）
1. 移除 Tailwind CDN runtime 注入（G01）
2. 補 API 全鏈路打點（G06）
3. 熱門查詢快取 + 請求合併（G08）
4. `portfolio/health` 批次查詢、避免 N+1（G11）
5. AI 改短版先回、長版後補（G09, G15）

#### Phase B（3~5 週，穩定且可擴）
1. 索引與預聚合（G10, G12）
2. Budget manager 全面接管（G13, G14, G15）
3. 完成 API 分級與 UI loading 規範（G17）
4. 加入 abort/cancel 與同頁 cache 共用（G18, G19）

### 10.9 驗收方式（你要看得見成果）

每週固定輸出這 8 個數字：
1. 首屏可互動時間（首頁、watchlist、analysis）
2. `/portfolio/health` P50/P95
3. `/analysis/signal` P50/P95
4. AI 首段回應時間（stream start）
5. FinMind 每小時峰值用量
6. Tavily 當月累積消耗與剩餘
7. Gemini 每請求平均 token
8. 快取命中率（memory / supabase）

只要你能把「P95、快取命中率、外部配額消耗」三條線穩定下來，體感慢的問題通常會大幅改善。

### 10.10 一句話結論

你現在的慢，多半不是單點效能不夠，而是「冷啟動 + 外部 API 串接 + 快取層不足 + 前端載入策略偏重」疊加造成。先做 Phase A，通常 1~2 週就會有明顯改善。
