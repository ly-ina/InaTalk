"""
房间管理：创建、加入、列表、删除
"""
import time
import uuid
from typing import Any

from .auth import hash_password, verify_password
from .config import REST_URL, get_client
from .files_manager import delete_room_files


async def create_room(name: str, password: str, creator: str) -> dict[str, Any]:
    """创建新房间（房间名唯一）"""
    client = get_client()

    # 检查房间名是否已存在
    check_url = f"{REST_URL}/rooms?select=id&name=eq.{name}"
    resp = await client.get(check_url)
    if resp.json():
        return {"success": False, "message": "该房间名已被占用"}

    room_id = uuid.uuid4().hex[:8].upper()
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


async def join_room(room_id: str, password: str, _username: str) -> dict[str, Any]:
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
            "background": row.get("background"),
            "announcement": row.get("announcement"),
        },
    }


async def get_all_rooms() -> list[dict[str, Any]]:
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


async def delete_room(room_id: str, username: str) -> dict[str, Any]:
    """删除房间（仅创建者可操作）"""
    client = get_client()
    url = f"{REST_URL}/rooms?select=id,name,creator,background&id=eq.{room_id}"
    resp = await client.get(url)
    rows = resp.json()
    if not rows:
        return {"success": False, "message": "房间不存在"}
    row = rows[0]
    if row["creator"] != username:
        return {"success": False, "message": "只有房间创建者才能删除房间"}

    # 删除房间背景文件（Storage）
    bg = row.get("background")
    if bg:
        from .files_manager import delete_background_by_url
        await delete_background_by_url(bg)

    # 删除房间所有聊天文件
    await delete_room_files(room_id)
    # 删除房间关联的消息
    await client.delete(f"{REST_URL}/messages?room_id=eq.{room_id}")
    # 删除房间本身
    await client.delete(f"{REST_URL}/rooms?id=eq.{room_id}")
    return {"success": True, "message": f"房间 '{row['name']}' 已删除", "room_id": room_id}


async def change_room_password(
    room_id: str, username: str, old_password: str, new_password: str
) -> dict[str, Any]:
    """修改/添加房间密码（仅创建者可操作）"""
    client = get_client()
    url = f"{REST_URL}/rooms?select=id,name,creator,password_hash,salt&id=eq.{room_id}"
    resp = await client.get(url)
    rows = resp.json()
    if not rows:
        return {"success": False, "message": "房间不存在"}
    row = rows[0]
    if row["creator"] != username:
        return {"success": False, "message": "只有房间创建者才能管理房间"}

    # 如果房间已有密码，需要验证旧密码
    if row["password_hash"]:
        if not old_password:
            return {"success": False, "message": "请输入当前房间密码"}
        if not verify_password(old_password, row["salt"], row["password_hash"]):
            return {"success": False, "message": "当前房间密码错误"}

    # 设置新密码
    if not new_password:
        return {"success": False, "message": "新密码不能为空"}

    pw_hash, salt = hash_password(new_password)
    await client.patch(
        f"{REST_URL}/rooms?id=eq.{room_id}",
        json={"password_hash": pw_hash, "salt": salt},
    )
    status = "已更新" if row["password_hash"] else "已设置"
    return {
        "success": True,
        "message": f"房间密码{status}",
        "room_id": room_id,
        "has_password": True,
    }


async def remove_room_password(
    room_id: str, username: str, old_password: str
) -> dict[str, Any]:
    """移除房间密码（仅创建者可操作）"""
    client = get_client()
    url = f"{REST_URL}/rooms?select=id,name,creator,password_hash,salt&id=eq.{room_id}"
    resp = await client.get(url)
    rows = resp.json()
    if not rows:
        return {"success": False, "message": "房间不存在"}
    row = rows[0]
    if row["creator"] != username:
        return {"success": False, "message": "只有房间创建者才能管理房间"}
    if not row["password_hash"]:
        return {"success": False, "message": "房间没有密码"}
    if not old_password:
        return {"success": False, "message": "请输入当前房间密码"}
    if not verify_password(old_password, row["salt"], row["password_hash"]):
        return {"success": False, "message": "当前房间密码错误"}

    await client.patch(
        f"{REST_URL}/rooms?id=eq.{room_id}",
        json={"password_hash": None, "salt": None},
    )
    return {
        "success": True,
        "message": "房间密码已移除",
        "room_id": room_id,
        "has_password": False,
    }


async def set_announcement(
    room_id: str, username: str, content: str | None
) -> dict[str, Any]:
    """设置/更新/清除房间公告（仅创建者可操作），公告最长500字符"""
    client = get_client()
    url = f"{REST_URL}/rooms?select=id,name,creator&id=eq.{room_id}"
    resp = await client.get(url)
    rows = resp.json()
    if not rows:
        return {"success": False, "message": "房间不存在"}
    row = rows[0]
    if row["creator"] != username:
        return {"success": False, "message": "只有房间创建者才能管理公告"}

    if content is not None and len(content) > 500:
        return {"success": False, "message": "公告最长500个字符"}

    announcement = content.strip() if content and content.strip() else None
    await client.patch(
        f"{REST_URL}/rooms?id=eq.{room_id}",
        json={"announcement": announcement},
    )
    return {
        "success": True,
        "message": "公告已更新" if announcement else "公告已清除",
        "room_id": room_id,
        "announcement": announcement,
    }


async def update_room_background(
    room_id: str, username: str, background_url: str | None
) -> dict[str, Any]:
    """更新房间背景（仅创建者可操作）"""
    client = get_client()
    url = f"{REST_URL}/rooms?select=id,name,creator,background&id=eq.{room_id}"
    resp = await client.get(url)
    rows = resp.json()
    if not rows:
        return {"success": False, "message": "房间不存在"}
    row = rows[0]
    if row["creator"] != username:
        return {"success": False, "message": "只有房间创建者才能管理房间"}

    # 如果有旧背景文件，清理掉
    old_bg = row.get("background")
    if old_bg and old_bg != background_url:
        from .files_manager import delete_background_by_url
        await delete_background_by_url(old_bg)

    await client.patch(
        f"{REST_URL}/rooms?id=eq.{room_id}",
        json={"background": background_url},
    )
    return {
        "success": True,
        "message": "房间背景已更新" if background_url else "房间背景已清除",
        "room_id": room_id,
        "background": background_url,
    }


async def get_my_rooms_detail(username: str) -> list[dict[str, Any]]:
    """获取用户创建的房间（含详细信息）"""
    client = get_client()
    url = (
        f"{REST_URL}/rooms"
        f"?select=id,name,password_hash,creator,background,last_activity"
        f"&creator=eq.{username}"
        f"&order=last_activity.desc"
    )
    resp = await client.get(url)
    return [
        {
            "id": r["id"],
            "name": r["name"],
            "has_password": bool(r.get("password_hash")),
            "creator": r["creator"],
            "background": r.get("background"),
            "last_activity": r.get("last_activity"),
        }
        for r in (resp.json() or [])
    ]
