# ── Stage 1：前端 build（使用官方 Node.js image，不需要額外安裝）──
FROM node:20-slim AS frontend-builder

WORKDIR /app/frontend

# 先只複製 package 定義，讓 layer cache 可重用
COPY frontend/package*.json ./
RUN npm ci --no-audit --no-fund

# 複製源碼並 build
COPY frontend/ ./
RUN npm run build

# ── Stage 2：Python runtime ──────────────────────────────────────────
FROM python:3.11-slim

WORKDIR /app

# 確保 Python 輸出立即 flush（Docker log 必要）
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# 安裝 tzdata（Asia/Taipei 時區需要）
RUN apt-get update && apt-get install -y --no-install-recommends tzdata && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# 安裝 Python 依賴
COPY requirements.txt .
RUN pip install --no-cache-dir --prefer-binary -r requirements.txt

# 從 Stage 1 複製前端 build 產物
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

# 複製整個後端（.dockerignore 控制排除項目）
COPY . .

EXPOSE 7860

CMD ["python", "app.py"]
