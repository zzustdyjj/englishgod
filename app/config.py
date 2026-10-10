import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

DATA_DIR = Path(os.getenv("DATA_DIR") or BASE_DIR / "data")
UPLOAD_DIR = DATA_DIR / "uploads"
DB_PATH = DATA_DIR / "app.db"

# LiteLLM 格式的模型名，如 anthropic/claude-sonnet-5-5；mock 为演示模式
LLM_MODEL = os.getenv("LLM_MODEL") or "mock"
LLM_API_KEY = os.getenv("LLM_API_KEY") or None
LLM_API_BASE = os.getenv("LLM_API_BASE") or None

# 访问密码；为空则不需要登录（仅限本机使用）。通过公网地址访问时必须设置
ACCESS_PASSWORD = os.getenv("ACCESS_PASSWORD") or None
