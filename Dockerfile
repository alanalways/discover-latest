FROM python:3.11-slim

WORKDIR /app

# 確保 Python 輸出立即 flush（Docker log 必要）
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV NODE_OPTIONS=--max-old-space-size=2048

# 安裝 Node.js（前端 build 用）+ tzdata（zoneinfo Asia/Taipei 需要）
RUN apt-get update && apt-get install -y curl tzdata && \
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# 先安裝前端依賴，讓 Docker layer cache 可以重用
COPY frontend/package*.json frontend/
RUN cd frontend && npm ci --no-audit --no-fund

# 先建立前端
COPY frontend/ frontend/
RUN cd frontend && npm run build

# 再安裝 Python 依賴
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 最後複製整個專案，其餘內容由 .dockerignore 控制
COPY . .

EXPOSE 7860

CMD ["python", "app.py"]
