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
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB (Supabase 免费层限制)
MAX_BG_SIZE = 10 * 1024 * 1024     # 10MB 背景图限制

# 项目根目录（src/config.py → src → 项目根）
ROOT_DIR = Path(__file__).parent.parent
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
STORAGE_URL = f"{SUPABASE_URL}/storage/v1"

# Storage bucket 名称
FILES_BUCKET = "room-files"           # 聊天文件（私有）
BACKGROUNDS_BUCKET = "room-backgrounds"  # 房间背景（公开）

# ============ 共享 httpx clients ============
_rest_client: httpx.AsyncClient | None = None
_storage_client: httpx.AsyncClient | None = None


def get_client() -> httpx.AsyncClient:
    """REST API 客户端（JSON 请求）"""
    global _rest_client
    if _rest_client is None or _rest_client.is_closed:
        _rest_client = httpx.AsyncClient(
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
                "Content-Type": "application/json",
                "Prefer": "return=representation",
            },
            timeout=30.0,
        )
    return _rest_client


def get_storage_client() -> httpx.AsyncClient:
    """Storage API 客户端（二进制/表单 请求，无 JSON Content-Type）"""
    global _storage_client
    if _storage_client is None or _storage_client.is_closed:
        _storage_client = httpx.AsyncClient(
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
            },
            timeout=60.0,
        )
    return _storage_client
