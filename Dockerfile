# ── Stage 1：Build Next.js 前端 ──
FROM node:20-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit
COPY frontend/ .
RUN npm run build

# ── Stage 2：Python 後端 + 靜態前端 ──
FROM python:3.10.13-slim

RUN useradd -m -u 1000 user
WORKDIR /home/user/app

# Python 依賴
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 複製後端程式碼
COPY --chown=user:user main.py .
COPY --chown=user:user routes/ routes/
COPY --chown=user:user services/ services/
COPY --chown=user:user adapters/ adapters/
COPY --chown=user:user config/ config/
COPY --chown=user:user pages/ pages/
COPY --chown=user:user components/ components/
COPY --chown=user:user locales/ locales/
COPY --chown=user:user static/ static/
COPY --chown=user:user utils/ utils/

# 複製前端 build 靜態檔案
COPY --from=frontend --chown=user:user /app/frontend/out ./frontend_out

USER user

ENV PORT=7860
EXPOSE 7860

CMD ["python", "main.py"]
