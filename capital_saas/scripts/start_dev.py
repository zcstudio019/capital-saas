import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

print("Capital SaaS 本地开发启动")
print("1) pip install -r requirements.txt")
print("2) python -m db.init_db")
print("3) uvicorn main:app --reload")
print("访问：http://127.0.0.1:8001")

if "--run" in sys.argv:
    subprocess.call([sys.executable, "-m", "uvicorn", "main:app", "--reload"], cwd=ROOT)
