import os
import sys
import warnings

# 抑制 yfinance 內部 Pandas 棄用警告（無法升級 yfinance，鎖定 <0.2.59）
warnings.filterwarnings("ignore", category=FutureWarning, module="yfinance")
warnings.filterwarnings("ignore", message=".*Timestamp.utcnow.*")
warnings.filterwarnings("ignore", message=".*Pandas4Warning.*")

# 確保 Python stdout/stderr 不被 buffered（Docker 環境必要）
os.environ.setdefault("PYTHONUNBUFFERED", "1")

# 用 os.execv 取代 subprocess.run：
# - 讓 uvicorn 直接成為主 process（正確接收 Docker SIGTERM）
# - 避免 subprocess wrapper 導致的 exit code / signal 問題
# - 避免 stdout buffering 造成 container log 看不到輸出
os.execv(sys.executable, [
    sys.executable, "-m", "uvicorn",
    "backend.main:app",
    "--host", "0.0.0.0",
    "--port", "7860",
    "--workers", "1",
    "--log-level", "info",
])
