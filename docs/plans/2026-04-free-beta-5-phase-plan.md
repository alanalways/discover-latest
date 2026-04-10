# DiscoverLatest 免費 Beta 五階段執行計畫

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** 先把 DiscoverLatest 做成穩定、好看、好懂、可持續收集使用者回饋的免費版，暫緩收費與正式商業化功能。

**Architecture:** 先優先修使用者會直接接觸到的體驗面（首頁、分析頁、掃描頁、後台總覽），同步補穩定性基礎（錯誤處理、測試、CI、資料展示一致性）。商業化相關功能先保留設定，但不再往付款、訂閱、付費牆前進。

**Tech Stack:** FastAPI、React、TypeScript、Vite、Supabase、HuggingFace Spaces

---

## 總原則
- 先免費版，先穩定，再談收費。
- 投資建議功能保留，但表達方式維持「白話研究助理」。
- 每個 phase 結束都要能上線驗收，不做半套。
- 優先處理會影響使用者第一印象與實際留存的地方。
- 商業化只保留文案與未來擴充空間，不做付款與訂閱流程。

---

## Phase 1：產品定位回正 + 免費 Beta 入口整理

**Objective:** 把目前偏商業化／付費導向的訊息收斂成免費 Beta 版本，避免前後端訊息不一致。

**Files:**
- Modify: `backend/config.py`
- Modify: `backend/api/routes/market.py`
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/pages/Dashboard.tsx`
- Modify: `frontend/src/pages/Profile.tsx`
- Modify: `docs/plans/2026-04-student-beta-commercialization.md`
- Create: `docs/plans/2026-04-free-beta-5-phase-plan.md`

**Deliverables:**
- 首頁明確改成「免費 Beta 測試中」
- 拿掉過度強調定價、升級、付費導向的主視覺
- Profile 頁改成 Beta 權限說明，不再強推升級
- product-config API 改成以免費版訊息為主
- 文件更新：現階段暫緩收費

**Verification:**
- 前端首頁與會員頁不再出現主動催付費文案
- `/api/market/product-config` 回傳免費 Beta 定位資訊
- `npm run build` 成功

---

## Phase 2：前台體驗大修（首頁 / Analysis / Scanner）

**Objective:** 把使用者真正會停留的三個頁面做得更有質感、更流暢、更像產品，而不是工程介面。

**Files:**
- Modify: `frontend/src/pages/Dashboard.tsx`
- Modify: `frontend/src/pages/Analysis.tsx`
- Modify: `frontend/src/pages/Scanner.tsx`
- Modify: `frontend/src/index.css`
- Modify: `frontend/src/components/ui.tsx`（若需要抽共用卡片/按鈕）

**Deliverables:**
- Dashboard：更像產品首頁，資訊層級清楚
- Analysis：輸入流程、分析進行中、結果區塊重新排版
- Scanner：標的列表、推薦理由、狀態標籤更清楚
- 整體 UI 統一：按鈕、卡片、tag、區塊留白一致
- 手機與桌面至少都不會破版

**Verification:**
- `npm run build` 成功
- 本地靜態預覽時，首頁 / 分析頁 / 掃描頁視覺一致
- browser snapshot / vision 檢查頁面沒有明顯醜亂或資訊堆疊問題

---

## Phase 3：後台管理總控台重做

**Objective:** 讓你一進後台就看得懂產品狀態、使用狀況與資料分布，不用自己猜。

**Files:**
- Modify: `backend/api/routes/admin.py`
- Modify: `backend/api/routes/user.py`（若需補統計欄位）
- Modify: `backend/data/storage/supabase_client.py`（若需補聚合查詢）
- Modify: `frontend/src/pages/Admin.tsx`
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/index.css`

**Deliverables:**
- 後台首頁 KPI 卡片：用戶、報告、分析任務、提醒、自選股、近期活躍
- 方案/權限資訊改成 Beta 使用狀況，而不是收費管理
- 補搜尋 / 篩選 / 快速查看使用者狀態
- 補資料表格與摘要區塊的一致視覺
- 把重要系統狀態集中在第一屏看完

**Verification:**
- `/api/admin/system` 回傳欄位完整且前端能吃到
- 後台第一屏能看懂核心數據，不需要切來切去
- `python3 -m py_compile ...` 成功
- `npm run build` 成功

---

## Phase 4：穩定性補強（錯誤處理 / 測試 / CI）

**Objective:** 把「看起來能用」提升成「改版比較不容易炸」。

**Files:**
- Modify: `backend/api/routes/analysis.py`
- Modify: `backend/api/routes/scanner.py`
- Modify: `backend/api/routes/admin.py`
- Modify: `frontend/src/lib/api.ts`
- Modify/Create: `tests/` 或 `backend/tests/`（依現有結構）
- Create: `.github/workflows/frontend-backend-check.yml`
- Modify: `frontend/package.json`

**Deliverables:**
- 核心 API 的錯誤訊息統一
- 前端 API 失敗時不會整頁空白或卡死
- 至少補這些測試：
  - product-config
  - admin system stats
  - user rate limiter beta logic
  - analysis / scanner 基本 API smoke tests
- GitHub Actions：至少跑 Python compile + 前端 build + 測試

**Verification:**
- 本地測試可跑
- GitHub Actions 檔存在且內容合理
- API 失敗時前端有 fallback 提示

---

## Phase 5：免費 Beta 營運化（回饋、留存、觀察指標）

**Objective:** 讓免費版不是放著而已，而是能收回饋、看使用情況、知道下一步要改什麼。

**Files:**
- Modify: `backend/api/routes/market.py`
- Modify: `backend/api/routes/user.py`
- Modify/Create: `backend/api/routes/feedback.py`（若需要）
- Modify/Create: `backend/data/storage/supabase_client.py`
- Modify: `frontend/src/pages/Dashboard.tsx`
- Modify: `frontend/src/pages/Profile.tsx`
- Modify: `frontend/src/pages/Admin.tsx`
- Modify/Create: `frontend/src/pages/Feedback.tsx`

**Deliverables:**
- Beta 回饋入口（簡單表單即可）
- 後台可看回饋數量與常見問題
- 基本留存觀察指標：註冊數、活躍數、分析次數、掃描使用次數
- 首頁 / Profile 可引導用戶回報體驗
- 形成「用戶用了 -> 留下意見 -> 我們知道怎麼改」的閉環

**Verification:**
- 至少能成功送出一筆 feedback
- 後台看得到 feedback / usage summary
- 主要免費版關鍵指標可視化

---

## 目前暫緩，不做
- 正式金流
- 訂閱狀態機
- 自動續費
- 發票 / 對帳
- 正式 paywall
- 付費方案 A/B test

---

## 建議執行順序
1. 先完成 Phase 1，避免產品訊息混亂
2. 再做 Phase 2，把前台體驗拉起來
3. 接著做 Phase 3，讓後台可管理
4. 然後做 Phase 4，補穩定性
5. 最後做 Phase 5，開始收集真實使用者回饋

---

## 驗收標準
- 使用者看到的是「免費 Beta 產品」，不是半套付費 SaaS
- 前台三大頁面（首頁 / 分析 / 掃描）看起來有產品質感
- 後台可以一眼看懂整體數據
- 每次改版至少有基本檢查，不靠運氣
- 能開始收免費版使用者回饋，為未來商業化做準備
