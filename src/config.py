"""
全局配置 & Supabase 客户端
"""
import os
from pathlib import Path

import httpx
from dotenv import load_dotenv

_ = load_dotenv()

# ============ 服务配置 ============
HOST = "0.0.0.0"
PORT = int(os.environ.get("PORT", "8766"))
ROOM_EXPIRE_DAYS = 7
CLEANUP_HOUR = 3
CLEANUP_MINUTE = 0
MAX_MSG_PER_ROOM = 200
MAX_FILE_SIZE = 4 * 1024 * 1024 * 1024  # 4GB

# 项目根目录（src/config.py → src → 项目根）
ROOT_DIR = Path(__file__).parent.parent
UPLOAD_DIR = ROOT_DIR / "uploads"
STATIC_DIR = ROOT_DIR / "static"

# 文件保留时长映射（秒）
FILE_RETENTION: dict[str, int | None] = {
    "3h": 3 * 3600,
    "1d": 86400,
    "7d": 7 * 86400,
    "30d": 30 * 86400,
    "forever": None,
}

# ============ Supabase ============
SUPABASE_URL = os.environ["SUPABASE_URL"].rstrip("/")
SUPABASE_KEY = os.environ["SUPABASE_ANON_KEY"]
REST_URL = f"{SUPABASE_URL}/rest/v1"

# 共享 httpx client（带认证头）
_client: httpx.AsyncClient | None = None


def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
                "Content-Type": "application/json",
                "Prefer": "return=representation",
            },
            timeout=30.0,
        )
    return _client
