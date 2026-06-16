"""
用户认证：密码哈希、登录、改名、重置密钥
"""
import hashlib
import secrets
import time

from .config import REST_URL, get_client


# ============ 密码 ============
def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    if salt is None:
        salt = secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100000)
    return h.hex(), salt


def verify_password(password: str, salt: str, stored_hash: str) -> bool:
    h, _ = hash_password(password, salt)
    return h == stored_hash


# ============ 用户操作 ============
async def create_or_login_user(username: str, password: str) -> dict[str, object]:
    """登录或自动创建账号"""
    client = get_client()
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
        )
        return {"success": True, "message": "账号已创建并登录", "is_new": True}


async def change_username(old_username: str, password: str, new_username: str) -> dict[str, object]:
    """修改用户名（同步更新三张表）"""
    client = get_client()
    # 验证旧用户
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

    # 检查新名字是否被占用
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
    """重置密钥"""
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


# ============ Session Token（内存态，重启即失效）============
_sessions: dict[str, str] = {}  # token → username


def create_session(username: str) -> str:
    """生成 session token，用于快速重连跳过 Supabase 验证"""
    token = secrets.token_hex(32)
    _sessions[token] = username
    return token


def validate_session(token: str) -> str | None:
    """验证 token，返回 username 或 None"""
    return _sessions.get(token)


def invalidate_session(token: str):
    """销毁 session（logout 时调用）"""
    _sessions.pop(token, None)
