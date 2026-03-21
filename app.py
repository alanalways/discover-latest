import subprocess
import sys
import warnings

# 抑制 yfinance 內部 Pandas 棄用警告（無法升級 yfinance，鎖定 <0.2.59）
warnings.filterwarnings("ignore", category=FutureWarning, module="yfinance")
warnings.filterwarnings("ignore", message=".*Timestamp.utcnow.*")
warnings.filterwarnings("ignore", message=".*Pandas4Warning.*")

subprocess.run([
    sys.executable, "-m", "uvicorn",
    "backend.main:app",
    "--host", "0.0.0.0",
    "--port", "7860",
    "--workers", "1",
])
