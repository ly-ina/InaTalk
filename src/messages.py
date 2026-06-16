"""
消息管理：保存、查询、裁剪
"""
import time
from typing import Any

from .config import MAX_MSG_PER_ROOM, REST_URL, get_client


async def get_room_messages(room_id: str, limit: int = 200) -> list[dict[str, object]]:
    """获取房间历史消息"""
    client = get_client()
    url = (
        f"{REST_URL}/messages?select=username,content,msg_type,created_at"
        f"&room_id=eq.{room_id}&order=created_at.desc&limit={limit}"
    )
    resp = await client.get(url)
    rows = resp.json()
    return list(reversed(rows))


async def get_room_files(room_id: str, limit: int = 50) -> list[dict[str, object]]:
    """获取房间历史文件记录"""
    client = get_client()
    url = (
        f"{REST_URL}/files?select=*"
        f"&room_id=eq.{room_id}&order=created_at.desc&limit={limit}"
    )
    resp = await client.get(url)
    rows = resp.json()
    if not isinstance(rows, list):
        return []
    return list(reversed(rows))


async def save_message(room_id: str, username: str, content: str, msg_type: str = "text") -> dict[str, object]:
    """保存消息到数据库"""
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
    await _trim_room_messages(room_id)

    await client.patch(
        f"{REST_URL}/rooms?id=eq.{room_id}",
        json={"last_activity": now},
    )
    return dict(saved)


async def _trim_room_messages(room_id: str):
    """删除超出限制的旧消息"""
    client = get_client()
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
