---
title: DiscoverLatest
emoji: 📊
colorFrom: blue
colorTo: indigo
sdk: docker
pinned: false
app_port: 7860
---

# DiscoverLatest 2.0 — AI 智慧投資分析平台

六大研究部門 × AI 矛盾仲裁 × 首席分析師報告

## 架構

### AI 分析引擎（混合架構）

| 用途 | 提供者 | 模型 | 限制 |
|------|--------|------|------|
| Batch Search Grounding（新聞/宏觀/情緒資料蒐集） | Google Gemini | gemini-2.5-flash | 20 RPD（免費） |
| 技術/基本面/籌碼/事件/宏觀/情緒分析 | NVIDIA NIM | kimi-k2.5 | 40 RPM，無日限制 |
| 矛盾仲裁 | NVIDIA NIM | kimi-k2.5 | 同上 |
| 首席分析師報告（串流） | NVIDIA NIM | kimi-k2.5 | 同上 |

**每次分析消耗：1 次 Gemini RPD + 8 次 NVIDIA RPM**

### 全市場掃描（兩階段，無 Gemini 消耗）
1. **本地規則過濾**（0 API）：RSI/爆量/漲跌/均線突破/籌碼 → ~500 支縮減至 50-150 支
2. **NVIDIA 快速評分**：每支候選 1 次呼叫取得 score 1-10 → 取 Top 20
3. **Top 20 進入完整分析管線**

### 技術棧
- **後端**：FastAPI + Python 3.11
- **前端**：Vite + React + TypeScript + Tailwind CSS
- **資料庫**：Supabase（PostgreSQL）
- **部署**：HuggingFace Spaces（Docker）
