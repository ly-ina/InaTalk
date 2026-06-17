"""
WebSocket 处理：连接管理、消息路由、广播
"""
import json
from typing import Any

from aiohttp import web, WSMsgType

from .auth import change_username, create_or_login_user, create_session, reset_password, validate_session
from .config import PORT, REST_URL, get_client
from .files_manager import delete_file_record, get_room_files
from .logger import get_logger
from .messages import get_room_messages, save_message
from .rooms import create_room, delete_room, get_all_rooms, join_room, change_room_password, remove_room_password, update_room_background, get_my_rooms_detail, set_announcement
from .private_chat import get_chat_id, save_private_message, get_private_messages

log = get_logger("ws")

# ============ 在线状态 ============
online_users: dict[str, set[Any]] = {}
room_members: dict[str, set[str]] = {}
# 私聊会话：{username: target_username}，记录当前正在和谁私聊
private_sessions: dict[str, str] = {}


async def broadcast_to_room(room_id: str, message: dict[str, Any], exclude: Any = None):
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

    async def send(data: dict[str, Any]):
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
                token = (msg.get("token") or "").strip()
                # 优先走 session token（秒过，跳过 Supabase 查询）
                if token:
                    cached_user = validate_session(token)
                    if cached_user:
                        current_user = cached_user
                        online_users.setdefault(cached_user, set()).add(ws)
                        await send({"type": "login_result", "success": True, "token": token, "is_new": False,
                                     "message": "已恢复会话"})
                        continue
                # 降级为密码登录
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
                    new_token = create_session(username)
                    result["token"] = new_token
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
                    files = await get_room_files(room_id)

                    # 合并消息和文件，按 created_at 统一排序
                    timeline = []
                    for m in messages:
                        timeline.append({"type": "message", "data": m, "ts": m.get("created_at", 0)})
                    for f in files:
                        timeline.append({"type": "file", "data": f, "ts": f.get("created_at", 0)})
                    timeline.sort(key=lambda x: x["ts"])

                    await send({"type": "room_joined", "room": result["room"], "timeline": [
                        {"type": t["type"], **t["data"]} for t in timeline
                    ]})
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
                if msg_subtype not in ("text", "emoji", "sticker"):
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

            # --- 获取用户创建的房间（管理用）---
            elif msg_type == "get_my_rooms":
                if not current_user:
                    await send({"type": "error", "message": "请先登录"})
                    continue
                rooms = await get_my_rooms_detail(current_user)
                await send({"type": "my_rooms_list", "rooms": rooms})

            # --- 删除房间 ---
            elif msg_type == "delete_room":
                if not current_user:
                    await send({"type": "error", "message": "请先登录"})
                    continue
                room_id = (msg.get("room_id") or "").strip().upper()
                if not room_id:
                    await send({"type": "delete_room_result", "success": False, "message": "房间ID不能为空"})
                    continue
                result = await delete_room(room_id, current_user)
                if result["success"]:
                    # 清理在线状态
                    room_members.pop(room_id, None)
                    await broadcast_to_room(room_id, {
                        "type": "system",
                        "content": "⚠️ 房间已被创建者删除",
                    })
                    # 如果当前用户在该房间中，清除 current_room
                    if current_room == room_id:
                        current_room = None
                await send({"type": "delete_room_result", **result})

            # --- 修改房间密码 ---
            elif msg_type == "change_room_password":
                if not current_user:
                    await send({"type": "error", "message": "请先登录"})
                    continue
                room_id = (msg.get("room_id") or "").strip().upper()
                old_pw = (msg.get("old_password") or "").strip()
                new_pw = (msg.get("new_password") or "").strip()
                if not room_id:
                    await send({"type": "change_room_password_result", "success": False, "message": "房间ID不能为空"})
                    continue
                result = await change_room_password(room_id, current_user, old_pw, new_pw)
                await send({"type": "change_room_password_result", **result})

            # --- 移除房间密码 ---
            elif msg_type == "remove_room_password":
                if not current_user:
                    await send({"type": "error", "message": "请先登录"})
                    continue
                room_id = (msg.get("room_id") or "").strip().upper()
                old_pw = (msg.get("old_password") or "").strip()
                if not room_id:
                    await send({"type": "remove_room_password_result", "success": False, "message": "房间ID不能为空"})
                    continue
                result = await remove_room_password(room_id, current_user, old_pw)
                await send({"type": "remove_room_password_result", **result})

            # --- 更新房间背景 ---
            elif msg_type == "update_room_background":
                if not current_user:
                    await send({"type": "error", "message": "请先登录"})
                    continue
                room_id = (msg.get("room_id") or "").strip().upper()
                bg_url = msg.get("background", None)
                if not room_id:
                    await send({"type": "update_room_background_result", "success": False, "message": "房间ID不能为空"})
                    continue
                result = await update_room_background(room_id, current_user, bg_url)
                await send({"type": "update_room_background_result", **result})

            # --- 设置房间公告 ---
            elif msg_type == "set_announcement":
                if not current_user:
                    await send({"type": "error", "message": "请先登录"})
                    continue
                room_id = (msg.get("room_id") or "").strip().upper()
                content = msg.get("content", None)  # None=清除, ""=清除, "text"=设置
                if not room_id:
                    await send({"type": "set_announcement_result", "success": False, "message": "房间ID不能为空"})
                    continue
                result = await set_announcement(room_id, current_user, content)
                if result["success"]:
                    # 广播公告更新给房间内所有成员
                    await broadcast_to_room(room_id, {
                        "type": "announcement_updated",
                        "room_id": room_id,
                        "announcement": result["announcement"],
                    })
                await send({"type": "set_announcement_result", **result})

            # --- 开始私聊 ---
            elif msg_type == "start_private_chat":
                if not current_user:
                    await send({"type": "error", "message": "请先登录"})
                    continue
                target = (msg.get("target") or "").strip()
                if not target or target == current_user:
                    await send({"type": "error", "message": "无效的私聊目标"})
                    continue
                # 允许离线留言，不检查在线状态
                chat_id = get_chat_id(current_user, target)
                messages = await get_private_messages(chat_id)
                private_sessions[current_user] = target
                await send({
                    "type": "private_chat_opened",
                    "target": target,
                    "chat_id": chat_id,
                    "messages": messages,
                    "is_online": target in online_users,
                })

            # --- 搜索用户 ---
            elif msg_type == "search_users":
                if not current_user:
                    await send({"type": "error", "message": "请先登录"})
                    continue
                query = (msg.get("query") or "").strip()
                if not query or len(query) < 1:
                    await send({"type": "user_search_result", "users": []})
                    continue
                client = get_client()
                url = f"{REST_URL}/users?select=username&username=ilike.*{query}*&limit=20"
                resp = await client.get(url)
                rows = resp.json() or []
                users = [
                    {"username": r["username"], "online": r["username"] in online_users}
                    for r in rows if isinstance(r, dict) and r.get("username") != current_user
                ]
                await send({"type": "user_search_result", "users": users})

            # --- 私信列表 ---
            elif msg_type == "get_chat_list":
                if not current_user:
                    continue
                client = get_client()
                url = f"{REST_URL}/private_messages?select=chat_id,sender,content,msg_type,created_at&chat_id=ilike.*{current_user}*&order=created_at.desc&limit=500"
                resp = await client.get(url)
                rows = resp.json() or []
                seen = {}
                for r in rows:
                    cid = r["chat_id"]
                    if cid not in seen:
                        parts = cid.split("_")
                        partner = parts[0] if len(parts) > 1 and parts[1] == current_user else (parts[1] if len(parts) > 1 else parts[0])
                        seen[cid] = {
                            "partner": partner,
                            "last_msg": r["content"][:50] if len(r.get("content", "")) > 50 else r.get("content", ""),
                            "last_time": r["created_at"],
                            "last_sender": r["sender"],
                            "online": partner in online_users,
                        }
                await send({"type": "chat_list", "chats": list(seen.values())})

            # --- 发送私聊消息 ---
            elif msg_type == "send_private_message":
                if not current_user:
                    await send({"type": "error", "message": "请先登录"})
                    continue
                target = private_sessions.get(current_user, "")
                if not target:
                    await send({"type": "error", "message": "请先选择私聊对象"})
                    continue
                content = (msg.get("content") or "").strip()
                if not content or len(content) > 5000:
                    continue
                msg_subtype = msg.get("msg_type", "text")
                if msg_subtype not in ("text", "emoji", "sticker", "file"):
                    msg_subtype = "text"
                chat_id = get_chat_id(current_user, target)
                saved = await save_private_message(chat_id, current_user, content, msg_subtype)
                payload = {"type": "private_message", **saved}
                # 发给对方
                for ws_target in online_users.get(target, set()):
                    try:
                        await ws_target.send_str(json.dumps(payload, ensure_ascii=False))
                    except Exception:
                        pass
                # 发给自己（回显）
                await send(payload)

            # --- 关闭私聊 ---
            elif msg_type == "close_private_chat":
                _ = private_sessions.pop(current_user, None) if current_user else None
                await send({"type": "private_chat_closed"})

            # --- 退出登录 ---
            elif msg_type == "logout":
                _ = private_sessions.pop(current_user, None) if current_user else None
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
        log.error(f"连接异常: {e}")
    finally:
        _ = private_sessions.pop(current_user, None) if current_user else None
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
