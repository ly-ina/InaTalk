"""
轻量化临时 IM 系统 - 服务端
WebSocket + Supabase (PostgreSQL) + 文件上传
"""
import asyncio
import json
import hashlib
import mimetypes
import os
import secrets
import shutil
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
from aiohttp import web, WSMsgType
from dotenv import load_dotenv

_ = load_dotenv()

# ============ 配置 ============
HOST = "0.0.0.0"
PORT = int(os.environ.get("PORT", "8766"))
ROOM_EXPIRE_DAYS = 7
CLEANUP_HOUR = 3
CLEANUP_MINUTE = 0
MAX_MSG_PER_ROOM = 200
MAX_FILE_SIZE = 4 * 1024 * 1024 * 1024  # 4GB
UPLOAD_DIR = Path(__file__).parent / "uploads"

# 文件保留时长映射（秒）
FILE_RETENTION: dict[str, int | None] = {
    "3h": 3 * 3600,
    "1d": 86400,
    "7d": 7 * 86400,
    "30d": 30 * 86400,
    "forever": None,
}

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


# ============ 密码 ============
def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    if salt is None:
        salt = secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100000)
    return h.hex(), salt


def verify_password(password: str, salt: str, stored_hash: str) -> bool:
    h, _ = hash_password(password, salt)
    return h == stored_hash


# ============ 用户 ============
async def create_or_login_user(username: str, password: str) -> dict[str, object]:
    client = get_client()
    # 查用户
    url = f"{REST_URL}/users?select=password_hash,salt&username=eq.{username}"
    resp = await client.get(url)
    rows = resp.json()
    if rows:
        row = rows[0]
        if verify_password(password, row["salt"], row["password_hash"]):
            return {"success": True, "message": "登录成功", "is_new": False}
        else:
            return {"success": False, "message": "密钥错误"}
    else:
        pw_hash, salt = hash_password(password)
        await client.post(
            f"{REST_URL}/users",
            json={
                "username": username,
                "password_hash": pw_hash,
                "salt": salt,
                "created_at": time.time(),
            },
        )  # type: ignore[func-returns-value]
        return {"success": True, "message": "账号已创建并登录", "is_new": True}


async def change_username(old_username: str, password: str, new_username: str) -> dict[str, object]:
    client = get_client()
    # 验证
    url = f"{REST_URL}/users?select=password_hash,salt&username=eq.{old_username}"
    resp = await client.get(url)
    rows = resp.json()
    if not rows:
        return {"success": False, "message": "用户不存在"}
    row = rows[0]
    if not verify_password(password, row["salt"], row["password_hash"]):
        return {"success": False, "message": "密钥错误"}
    if old_username == new_username:
        return {"success": False, "message": "新用户名与当前相同"}

    # 检查新名字
    url = f"{REST_URL}/users?select=id&username=eq.{new_username}"
    resp = await client.get(url)
    if resp.json():
        return {"success": False, "message": "该用户名已被占用"}

    # 更新三张表
    await client.patch(
        f"{REST_URL}/users?username=eq.{old_username}",
        json={"username": new_username},
    )
    await client.patch(
        f"{REST_URL}/messages?username=eq.{old_username}",
        json={"username": new_username},
    )
    await client.patch(
        f"{REST_URL}/rooms?creator=eq.{old_username}",
        json={"creator": new_username},
    )
    return {
        "success": True,
        "message": f"用户名已从 {old_username} 改为 {new_username}",
    }


async def reset_password(username: str, old_password: str, new_password: str) -> dict[str, object]:
    client = get_client()
    url = f"{REST_URL}/users?select=password_hash,salt&username=eq.{username}"
    resp = await client.get(url)
    rows = resp.json()
    if not rows:
        return {"success": False, "message": "用户不存在"}
    row = rows[0]
    if not verify_password(old_password, row["salt"], row["password_hash"]):
        return {"success": False, "message": "当前密钥错误"}

    pw_hash, salt = hash_password(new_password)
    await client.patch(
        f"{REST_URL}/users?username=eq.{username}",
        json={"password_hash": pw_hash, "salt": salt},
    )
    return {"success": True, "message": "密钥已更新"}


# ============ 房间 ============
async def create_room(name: str, password: str, creator: str) -> dict[str, object]:
    room_id = uuid.uuid4().hex[:8].upper()
    client = get_client()
    pw_hash = None
    salt = None
    if password:
        pw_hash, salt = hash_password(password)
    now = time.time()
    try:
        await client.post(
            f"{REST_URL}/rooms",
            json={
                "id": room_id,
                "name": name,
                "password_hash": pw_hash,
                "salt": salt,
                "creator": creator,
                "created_at": now,
                "last_activity": now,
            },
        )
        return {
            "success": True,
            "room": {"id": room_id, "name": name, "has_password": bool(password), "creator": creator},
        }
    except Exception as e:
        return {"success": False, "message": str(e)}


async def join_room(room_id: str, password: str, _username: str) -> dict[str, object]:
    client = get_client()
    url = f"{REST_URL}/rooms?select=*&id=eq.{room_id}"
    resp = await client.get(url)
    rows = resp.json()
    if not rows:
        return {"success": False, "message": "房间不存在"}
    row = rows[0]
    if row["password_hash"]:
        if not password:
            return {"success": False, "message": "需要房间密码"}
        if not verify_password(password, row["salt"], row["password_hash"]):
            return {"success": False, "message": "房间密码错误"}

    await client.patch(
        f"{REST_URL}/rooms?id=eq.{room_id}",
        json={"last_activity": time.time()},
    )
    return {
        "success": True,
        "room": {
            "id": row["id"],
            "name": row["name"],
            "has_password": bool(row["password_hash"]),
            "creator": row["creator"],
        },
    }


async def get_all_rooms() -> list[dict[str, object]]:
    client = get_client()
    url = f"{REST_URL}/rooms?select=id,name,password_hash,creator&order=last_activity.desc"
    resp = await client.get(url)
    return [
        {
            "id": r["id"],
            "name": r["name"],
            "has_password": bool(r.get("password_hash")),
            "creator": r["creator"],
        }
        for r in resp.json()
    ]


async def get_room_messages(room_id: str, limit: int = 200) -> list[dict[str, object]]:
    client = get_client()
    url = f"{REST_URL}/messages?select=username,content,msg_type,created_at&room_id=eq.{room_id}&order=created_at.desc&limit={limit}"
    resp = await client.get(url)
    rows = resp.json()
    return list(reversed(rows))


async def save_message(room_id: str, username: str, content: str, msg_type: str = "text") -> dict[str, object]:
    client = get_client()
    now = time.time()
    resp = await client.post(
        f"{REST_URL}/messages",
        json={
            "room_id": room_id,
            "username": username,
            "content": content,
            "msg_type": msg_type,
            "created_at": now,
        },
    )
    if resp.status_code >= 400:
        detail = resp.text[:200]
        print(f"[消息] 保存失败 ({resp.status_code}): {detail}")
        raise RuntimeError(f"消息保存失败: {detail}")
    data = resp.json()
    if not isinstance(data, list) or not data:
        print(f"[消息] 返回异常: {data}")
        raise RuntimeError(f"消息保存失败: 返回格式异常")
    saved = data[0]

    # 每房间只保留最近 MAX_MSG_PER_ROOM 条消息
    await trim_room_messages(room_id)

    await client.patch(
        f"{REST_URL}/rooms?id=eq.{room_id}",
        json={"last_activity": now},
    )
    return dict(saved)


async def trim_room_messages(room_id: str):
    """删除超出限制的旧消息，每房间最多保留 MAX_MSG_PER_ROOM 条"""
    client = get_client()
    # 获取第 MAX_MSG_PER_ROOM 条之后的消息ID
    url = (
        f"{REST_URL}/messages?select=id&room_id=eq.{room_id}"
        f"&order=created_at.desc&offset={MAX_MSG_PER_ROOM}"
    )
    resp = await client.get(url)
    rows = resp.json()
    if isinstance(rows, list) and rows:
        ids = ",".join(f"({r['id']})" for r in rows if isinstance(r, dict) and "id" in r)
        if ids:
            await client.delete(f"{REST_URL}/messages?id=in.({ids})")


# ============ 文件管理 ============
async def ensure_files_table():
    """确保 files 表存在（通过 Supabase REST 试探）"""
    client = get_client()
    url = f"{REST_URL}/files?limit=1"
    resp = await client.get(url)
    # 如果表不存在会返回错误，这里仅尝试
    if resp.status_code >= 400:
        print(f"[文件] 请先在 Supabase 中创建 files 表，SQL 见 README.md")
    else:
        print(f"[文件] files 表已就绪")


async def save_file_metadata(
    room_id: str,
    filename: str,
    file_size: int,
    file_type: str,
    uploaded_by: str,
    retention: str,
    storage_path: str,
) -> dict[str, object]:
    client = get_client()
    file_id = uuid.uuid4().hex[:12]
    now = time.time()
    retention_seconds = FILE_RETENTION.get(retention)
    expires_at = (now + retention_seconds) if retention_seconds else None

    resp = await client.post(
        f"{REST_URL}/files",
        json={
            "id": file_id,
            "room_id": room_id,
            "filename": filename,
            "file_size": file_size,
            "file_type": file_type,
            "uploaded_by": uploaded_by,
            "retention": retention,
            "expires_at": expires_at,
            "created_at": now,
            "storage_path": storage_path,
        },
    )
    if resp.status_code >= 400:
        detail = resp.text[:300]
        print(f"[文件] 元数据保存失败 ({resp.status_code}): {detail}")
        raise RuntimeError(f"文件元数据保存失败: {detail}")
    return {
        "id": file_id,
        "room_id": room_id,
        "filename": filename,
        "file_size": file_size,
        "file_type": file_type,
        "uploaded_by": uploaded_by,
        "retention": retention,
        "expires_at": expires_at,
        "created_at": now,
    }


async def get_room_files(room_id: str) -> list[dict[str, object]]:
    client = get_client()
    url = (
        f"{REST_URL}/files?select=*&room_id=eq.{room_id}"
        f"&order=created_at.desc&limit=100"
    )
    resp = await client.get(url)
    rows = resp.json()
    if not isinstance(rows, list):
        return []
    return list(rows)


async def delete_file_record(file_id: str) -> bool:
    """删除文件记录和磁盘文件"""
    client = get_client()
    # 先查询文件路径
    url = f"{REST_URL}/files?select=storage_path&id=eq.{file_id}"
    resp = await client.get(url)
    rows = resp.json()
    if isinstance(rows, list) and rows:
        row = rows[0]
        storage_path = row.get("storage_path", "")
        if storage_path:
            file_path = Path(storage_path)
            if file_path.exists():
                file_path.unlink()
    await client.delete(f"{REST_URL}/files?id=eq.{file_id}")
    return True


async def delete_room_files(room_id: str):
    """删除房间的所有文件（磁盘 + 数据库记录）"""
    client = get_client()
    url = f"{REST_URL}/files?select=storage_path&room_id=eq.{room_id}"
    resp = await client.get(url)
    rows = resp.json()
    if isinstance(rows, list):
        for row in rows:
            storage_path = row.get("storage_path", "")
            if storage_path:
                file_path = Path(storage_path)
                if file_path.exists():
                    file_path.unlink()
    # 删除房间上传目录
    room_dir = UPLOAD_DIR / room_id
    if room_dir.exists():
        shutil.rmtree(room_dir, ignore_errors=True)
    await client.delete(f"{REST_URL}/files?room_id=eq.{room_id}")


async def cleanup_expired_files():
    """清理过期的文件"""
    now = time.time()
    client = get_client()
    # 查询所有有过期时间且已过期的文件
    url = f"{REST_URL}/files?select=id,storage_path&expires_at=lt.{now}&expires_at=not.is.null"
    resp = await client.get(url)
    rows = resp.json()
    if isinstance(rows, list):
        for row in rows:
            storage_path = row.get("storage_path", "")
            if storage_path:
                file_path = Path(storage_path)
                if file_path.exists():
                    file_path.unlink()
            await client.delete(f"{REST_URL}/files?id=eq.{row['id']}")
            print(f"[文件清理] 已删除过期文件: {row.get('id')}")
        if rows:
            print(f"[文件清理] 共清理 {len(rows)} 个过期文件")


# ============ 清理 ============
async def cleanup_expired_rooms():
    cutoff = int(time.time() - ROOM_EXPIRE_DAYS * 86400)
    client = get_client()
    url = f"{REST_URL}/rooms?last_activity=lt.{cutoff}"
    resp = await client.get(url)
    data = resp.json()
    if isinstance(data, dict):
        if "message" in data:
            print(f"[清理] API 错误: {data.get('message')}")
            return
        if "id" in data:
            data = [data]
        else:
            return
    if not isinstance(data, list):
        return
    for r in data:
        if isinstance(r, dict) and "id" in r:
            # 先删除房间关联的文件
            await delete_room_files(r["id"])
            await client.delete(f"{REST_URL}/rooms?id=eq.{r['id']}")
            print(f"[清理] 已删除过期房间: {r['name']} ({r['id']})")
    if data:
        print(f"[清理] 共清理 {len(data)} 个过期房间")


async def cleanup_scheduler():
    while True:
        now = datetime.now()
        next_run = now.replace(hour=CLEANUP_HOUR, minute=CLEANUP_MINUTE, second=0, microsecond=0)
        if now >= next_run:
            next_run += timedelta(days=1)
        wait_seconds = (next_run - now).total_seconds()
        print(f"[清理] 下次清理时间: {next_run.strftime('%Y-%m-%d %H:%M:%S')} (等待 {wait_seconds:.0f} 秒)")
        await asyncio.sleep(wait_seconds)
        await cleanup_expired_rooms()
        await cleanup_expired_files()


# ============ WebSocket 服务 ============
online_users: dict[str, set[Any]] = {}
room_members: dict[str, set[str]] = {}


async def broadcast_to_room(room_id: str, message: dict[str, object], exclude: Any = None):
    members = room_members.get(room_id, set())
    for username in members:
        for ws in online_users.get(username, set()):
            if ws != exclude:
                try:
                    await ws.send_str(json.dumps(message, ensure_ascii=False))
                except Exception:
                    pass


async def send_online_users(room_id: str):
    members = room_members.get(room_id, set())
    msg = {"type": "online_users", "users": list(members)}
    for username in members:
        for ws in online_users.get(username, set()):
            try:
                await ws.send_str(json.dumps(msg, ensure_ascii=False))
            except Exception:
                pass


async def ws_handler(request: web.Request) -> web.WebSocketResponse:
    ws = web.WebSocketResponse()
    await ws.prepare(request)

    current_user: str | None = None
    current_room: str | None = None

    async def send(data: dict[str, object]):
        try:
            await ws.send_str(json.dumps(data, ensure_ascii=False))
        except Exception:
            pass

    try:
        async for raw_msg in ws:
            if raw_msg.type != WSMsgType.TEXT:
                continue
            try:
                msg = json.loads(raw_msg.data)
            except json.JSONDecodeError:
                await send({"type": "error", "message": "无效的消息格式"})
                continue

            msg_type = msg.get("type", "")

            # --- 登录 ---
            if msg_type == "login":
                username = (msg.get("username") or "").strip()
                password = (msg.get("password") or "").strip()
                if not username or not password:
                    await send({"type": "login_result", "success": False, "message": "用户名和密钥不能为空"})
                    continue
                if len(username) > 30:
                    await send({"type": "login_result", "success": False, "message": "用户名最长30个字符"})
                    continue
                result = await create_or_login_user(username, password)
                if result["success"]:
                    current_user = username
                    online_users.setdefault(username, set()).add(ws)
                await send({"type": "login_result", **result})

            # --- 获取房间列表 ---
            elif msg_type == "get_rooms":
                if not current_user:
                    await send({"type": "error", "message": "请先登录"})
                    continue
                rooms = await get_all_rooms()
                await send({"type": "room_list", "rooms": rooms})

            # --- 创建房间 ---
            elif msg_type == "create_room":
                if not current_user:
                    await send({"type": "error", "message": "请先登录"})
                    continue
                name = (msg.get("name") or "").strip()
                password = (msg.get("password") or "").strip()
                if not name:
                    await send({"type": "error", "message": "房间名不能为空"})
                    continue
                if len(name) > 50:
                    await send({"type": "error", "message": "房间名最长50个字符"})
                    continue
                result = await create_room(name, password, current_user)
                await send({"type": "create_room_result", **result})

            # --- 加入房间 ---
            elif msg_type == "join_room":
                if not current_user:
                    await send({"type": "error", "message": "请先登录"})
                    continue
                room_id = (msg.get("room_id") or "").strip().upper()
                password = (msg.get("password") or "").strip()
                if not room_id:
                    await send({"type": "error", "message": "房间ID不能为空"})
                    continue
                result = await join_room(room_id, password, current_user)
                if result["success"]:
                    if current_room and current_room in room_members:
                        assert current_user is not None
                        room_members[current_room].discard(current_user)
                        await broadcast_to_room(current_room, {
                            "type": "system",
                            "content": f"{current_user} 离开了房间",
                        }, exclude=ws)
                        await send_online_users(current_room)

                    current_room = room_id
                    room_members.setdefault(room_id, set[str]()).add(current_user)

                    messages = await get_room_messages(room_id)
                    await send({"type": "room_joined", "room": result["room"], "messages": messages})
                    await broadcast_to_room(room_id, {
                        "type": "system",
                        "content": f"{current_user} 加入了房间",
                    }, exclude=ws)
                    await send_online_users(room_id)
                else:
                    await send({"type": "join_room_result", **result})

            # --- 离开房间 ---
            elif msg_type == "leave_room":
                if current_room and current_room in room_members:
                    assert current_user is not None
                    room_members[current_room].discard(current_user)
                    await broadcast_to_room(current_room, {
                        "type": "system",
                        "content": f"{current_user} 离开了房间",
                    })
                    await send_online_users(current_room)
                current_room = None
                await send({"type": "room_left"})

            # --- 发送消息 ---
            elif msg_type == "send_message":
                if not current_user or not current_room:
                    await send({"type": "error", "message": "请先加入房间"})
                    continue
                content = (msg.get("content") or "").strip()
                if not content:
                    continue
                if len(content) > 5000:
                    await send({"type": "error", "message": "消息过长"})
                    continue
                msg_subtype = msg.get("msg_type", "text")
                if msg_subtype not in ("text", "emoji"):
                    msg_subtype = "text"
                saved = await save_message(current_room, current_user, content, msg_subtype)
                await broadcast_to_room(current_room, {"type": "new_message", **saved})

            # --- 修改用户名 ---
            elif msg_type == "change_username":
                if not current_user:
                    await send({"type": "error", "message": "请先登录"})
                    continue
                old_user = current_user
                password = (msg.get("password") or "").strip()
                new_username = (msg.get("new_username") or "").strip()
                if not password or not new_username:
                    await send({"type": "change_username_result", "success": False, "message": "密钥和新用户名不能为空"})
                    continue
                if len(new_username) > 30:
                    await send({"type": "change_username_result", "success": False, "message": "用户名最长30个字符"})
                    continue
                result = await change_username(old_user, password, new_username)
                if result["success"]:
                    if old_user in online_users:
                        online_users[new_username] = online_users.pop(old_user)
                    for rid, members in room_members.items():
                        if old_user in members:
                            members.discard(old_user)
                            members.add(new_username)
                            await broadcast_to_room(rid, {
                                "type": "system",
                                "content": f"{old_user} 改名为 {new_username}",
                            })
                            await send_online_users(rid)
                    current_user = new_username
                await send({"type": "change_username_result", **result})

            # --- 重置密钥 ---
            elif msg_type == "reset_password":
                if not current_user:
                    await send({"type": "error", "message": "请先登录"})
                    continue
                old_pw = (msg.get("old_password") or "").strip()
                new_pw = (msg.get("new_password") or "").strip()
                if not old_pw or not new_pw:
                    await send({"type": "reset_password_result", "success": False, "message": "新旧密钥不能为空"})
                    continue
                result = await reset_password(current_user, old_pw, new_pw)
                await send({"type": "reset_password_result", **result})

            # --- 获取文件列表 ---
            elif msg_type == "get_files":
                if not current_room:
                    await send({"type": "error", "message": "请先加入房间"})
                    continue
                files = await get_room_files(current_room)
                await send({"type": "file_list", "files": files, "http_port": PORT})

            # --- 删除文件 ---
            elif msg_type == "delete_file":
                if not current_user or not current_room:
                    await send({"type": "error", "message": "请先加入房间"})
                    continue
                file_id = (msg.get("file_id") or "").strip()
                if not file_id:
                    continue
                await delete_file_record(file_id)
                await broadcast_to_room(current_room, {
                    "type": "file_deleted",
                    "file_id": file_id,
                })
                await send({"type": "delete_file_result", "success": True, "file_id": file_id})

            # --- 退出登录 ---
            elif msg_type == "logout":
                if current_user:
                    if current_room and current_room in room_members:
                        room_members[current_room].discard(current_user)
                        await broadcast_to_room(current_room, {
                            "type": "system",
                            "content": f"{current_user} 离开了房间",
                        })
                        await send_online_users(current_room)
                    s = online_users.get(current_user, set())
                    s.discard(ws)
                    if not s:
                        _ = online_users.pop(current_user, None)
                current_user = None
                current_room = None
                await send({"type": "logout_result", "success": True})

    except Exception as e:
        print(f"[连接异常] {e}")
    finally:
        if current_user:
            if current_room and current_room in room_members:
                room_members[current_room].discard(current_user)
                await broadcast_to_room(current_room, {
                    "type": "system",
                    "content": f"{current_user} 断开了连接",
                })
                await send_online_users(current_room)
            s = online_users.get(current_user, set())
            s.discard(ws)
            if not s:
                _ = online_users.pop(current_user, None)
    return ws


# ============ CORS 中间件 ============
@web.middleware
async def cors_middleware(request: web.Request, handler: Any) -> web.Response:
    """处理 CORS 预检和添加跨域头"""
    if request.method == "OPTIONS":
        response = web.Response()
    else:
        response = await handler(request)
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, DELETE, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "*"
    return response


# ============ HTTP 文件服务 ============


async def handle_upload(request: web.Request) -> web.Response:
    """处理文件上传"""
    reader = await request.multipart()
    field = await reader.next()
    if field is None or getattr(field, "name", None) != "file":
        return web.json_response({"success": False, "message": "缺少文件字段"}, status=400)

    filename = getattr(field, "filename", None) or "unnamed"
    room_id = request.query.get("room_id", "").strip().upper()
    retention = request.query.get("retention", "7d").strip()
    uploader = request.query.get("uploader", "").strip()

    if not room_id:
        return web.json_response({"success": False, "message": "缺少 room_id"}, status=400)
    if retention not in FILE_RETENTION:
        return web.json_response({"success": False, "message": f"无效的保留时长: {retention}"}, status=400)
    if not uploader:
        return web.json_response({"success": False, "message": "缺少 uploader"}, status=400)

    # 检查房间是否存在
    client = get_client()
    url = f"{REST_URL}/rooms?select=id&id=eq.{room_id}"
    resp = await client.get(url)
    if not resp.json():
        return web.json_response({"success": False, "message": "房间不存在"}, status=404)

    # 准备存储
    room_dir = UPLOAD_DIR / room_id
    room_dir.mkdir(parents=True, exist_ok=True)

    file_uuid = uuid.uuid4().hex[:8]
    safe_filename = f"{file_uuid}_{filename}"
    file_path = room_dir / safe_filename

    # 读取文件内容
    size = 0
    _read_chunk = getattr(field, "read_chunk")
    with open(file_path, "wb") as f:
        while True:
            chunk = await _read_chunk(1024 * 1024)  # 1MB chunks
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_FILE_SIZE:
                f.close()
                file_path.unlink()
                return web.json_response(
                    {"success": False, "message": f"文件超过最大限制 {MAX_FILE_SIZE // (1024**3)}GB"},
                    status=413,
                )
            f.write(chunk)

    # 获取 MIME 类型
    file_type, _ = mimetypes.guess_type(filename)
    file_type = file_type or "application/octet-stream"

    # 保存元数据到 Supabase
    try:
        meta = await save_file_metadata(
            room_id=room_id,
            filename=filename,
            file_size=size,
            file_type=file_type,
            uploaded_by=uploader,
            retention=retention,
            storage_path=str(file_path),
        )
    except Exception as e:
        file_path.unlink(missing_ok=True)
        print(f"[文件] 元数据保存失败，已清理磁盘文件: {e}")
        return web.json_response(
            {"success": False, "message": f"文件元数据保存失败，请确认 Supabase 中已创建 files 表"},
            status=500,
        )

    print(f"[文件] 上传成功: {filename} ({size} bytes) -> 房间 {room_id}")

    # 通过 WebSocket 广播文件消息到房间
    file_msg: dict[str, object] = {
        "type": "new_file",
        "file": meta,
    }
    await broadcast_to_room(room_id, file_msg)

    return web.json_response({"success": True, "file": meta})


async def handle_download(request: web.Request) -> web.Response:
    """处理文件下载"""
    file_id = request.match_info.get("file_id", "")

    # 查询文件元数据
    client = get_client()
    url = f"{REST_URL}/files?select=*&id=eq.{file_id}"
    resp = await client.get(url)
    rows = resp.json()
    if not isinstance(rows, list) or not rows:
        return web.json_response({"success": False, "message": "文件不存在"}, status=404)

    file_info = rows[0]
    storage_path = file_info.get("storage_path", "")
    file_path = Path(storage_path)

    if not file_path.exists():
        return web.json_response({"success": False, "message": "文件已被删除"}, status=404)

    return web.FileResponse(  # pyright: ignore[reportReturnType]
        path=file_path,
        headers={
            "Content-Disposition": f'attachment; filename="{file_info["filename"]}"',
            "Content-Type": file_info.get("file_type", "application/octet-stream"),
        },
    )


async def handle_health(_request: web.Request) -> web.Response:
    return web.json_response({"status": "ok"})


async def http_factory() -> web.Application:
    app = web.Application(client_max_size=MAX_FILE_SIZE, middlewares=[cors_middleware])
    app.router.add_route("GET",  "/ws",            ws_handler)
    app.router.add_route("POST", "/api/upload",    handle_upload)
    app.router.add_route("GET",  "/api/files/{file_id}", handle_download)
    app.router.add_route("GET",  "/api/health",    handle_health)

    # 前端静态文件（显式注册，避免与 API 路由冲突）
    root = Path(__file__).parent
    app.router.add_route("GET", "/",          _serve_static(root / "index.html"))
    app.router.add_route("GET", "/app.js",    _serve_static(root / "app.js"))
    app.router.add_route("GET", "/style.css", _serve_static(root / "style.css"))
    return app


def _serve_static(path: Path) -> Any:
    async def handler(_request: web.Request) -> web.StreamResponse:
        return web.FileResponse(path)
    return handler


async def main():
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    print(f"[服务] 数据库: Supabase ({SUPABASE_URL})")
    print(f"[服务] 房间过期时间: {ROOM_EXPIRE_DAYS} 天")
    print(f"[服务] 每房间消息上限: {MAX_MSG_PER_ROOM} 条")
    print(f"[服务] 文件大小限制: {MAX_FILE_SIZE // (1024**3)}GB")
    print(f"[服务] 文件保留选项: {', '.join(FILE_RETENTION.keys())}")

    await ensure_files_table()
    await cleanup_expired_rooms()
    await cleanup_expired_files()
    _ = asyncio.create_task(cleanup_scheduler())

    # 一体化服务：HTTP + WebSocket 在同一端口
    app = await http_factory()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, HOST, PORT)
    await site.start()
    print(f"[服务] 启动成功 → http://{HOST}:{PORT}")
    print(f"[服务] WebSocket → ws://{HOST}:{PORT}/ws")
    print(f"[服务] 在浏览器打开 http://localhost:{PORT} 即可使用")

    await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
