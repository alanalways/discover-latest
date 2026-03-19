FROM python:3.11-slim

WORKDIR /app

# 安裝 Node.js（前端 build 用）
RUN apt-get update && apt-get install -y curl && \
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# 安裝 Python 依賴
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 複製專案
COPY . .

# 建立前端
RUN cd frontend && npm install && npm run build

EXPOSE 7860

CMD ["python", "app.py"]
