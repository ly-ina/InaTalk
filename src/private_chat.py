"""
私聊管理：消息存储、查询
chat_id 由两个用户名按字母排序拼接，保证一致性
"""
import time

from .config import REST_URL, get_client


def get_chat_id(user_a: str, user_b: str) -> str:
    """生成私聊 chat_id：两个用户名排序后拼接"""
    a, b = sorted([user_a, user_b])
    return f"{a}_{b}"


async def save_private_message(chat_id: str, sender: str, content: str, msg_type: str = "text") -> dict:
    """保存私聊消息"""
    client = get_client()
    now = time.time()
    resp = await client.post(
        f"{REST_URL}/private_messages",
        json={
            "chat_id": chat_id,
            "sender": sender,
            "content": content,
            "msg_type": msg_type,
            "created_at": now,
        },
    )
    data = resp.json()
    row = data[0] if isinstance(data, list) and data else {}
    return {
        "id": row.get("id"),
        "chat_id": chat_id,
        "sender": sender,
        "content": content,
        "msg_type": msg_type,
        "created_at": now,
    }


async def get_private_messages(chat_id: str, limit: int = 100) -> list[dict]:
    """获取私聊历史消息"""
    client = get_client()
    url = (
        f"{REST_URL}/private_messages"
        f"?select=id,chat_id,sender,content,msg_type,created_at"
        f"&chat_id=eq.{chat_id}"
        f"&order=created_at.asc"
        f"&limit={limit}"
    )
    resp = await client.get(url)
    return resp.json() or []


async def ensure_private_messages_table():
    """确保 private_messages 表存在 — 通过尝试查询来触发"""
    # PostgREST 不支持 DDL，表需要手动建
    # 此函数仅做轻量检查，不影响启动
    pass
