"""
WebSocket 处理：连接管理、消息路由、广播
"""
import json
from typing import Any

from aiohttp import web, WSMsgType

from .auth import change_username, create_or_login_user, reset_password
from .config import PORT
from .files_manager import delete_file_record, get_room_files
from .messages import get_room_messages, save_message
from .rooms import create_room, get_all_rooms, join_room

# ============ 在线状态 ============
online_users: dict[str, set[Any]] = {}
room_members: dict[str, set[str]] = {}


async def broadcast_to_room(room_id: str, message: dict[str, object], exclude: Any = None):
    """广播消息到房间所有成员"""
    members = room_members.get(room_id, set())
    for username in members:
        for ws in online_users.get(username, set()):
            if ws != exclude:
                try:
                    await ws.send_str(json.dumps(message, ensure_ascii=False))
                except Exception:
                    pass


async def send_online_users(room_id: str):
    """发送在线用户列表"""
    members = room_members.get(room_id, set())
    msg = {"type": "online_users", "users": list(members)}
    for username in members:
        for ws in online_users.get(username, set()):
            try:
                await ws.send_str(json.dumps(msg, ensure_ascii=False))
            except Exception:
                pass


async def ws_handler(request: web.Request) -> web.WebSocketResponse:
    """WebSocket 主处理器"""
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
