import subprocess
import sys

subprocess.run([
    sys.executable, "-m", "uvicorn",
    "backend.main:app",
    "--host", "0.0.0.0",
    "--port", "7860",
    "--workers", "1",
])
