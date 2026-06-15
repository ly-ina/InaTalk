"""
房间管理：创建、加入、列表
"""
import time
import uuid
from typing import Any

from .auth import hash_password, verify_password
from .config import REST_URL, get_client


async def create_room(name: str, password: str, creator: str) -> dict[str, object]:
    """创建新房间"""
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
    """加入房间（验证密码）"""
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
    """获取所有房间列表"""
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
