"""
HTTP 路由：文件上传/下载、健康检查、静态资源、CORS 中间件
"""
import mimetypes
from pathlib import Path
from typing import Any

from aiohttp import web

from .logger import get_logger

log = get_logger("routes")

from .config import (
    FILE_RETENTION, MAX_BG_SIZE, MAX_FILE_SIZE, REST_URL,
    STATIC_DIR, get_client,
)
from .files_manager import (
    delete_background_by_url,
    download_file_content,
    save_file_metadata,
    upload_background_to_storage,
    upload_file_to_storage,
)
from .websocket import broadcast_to_room, ws_handler


# ============ CORS 中间件 ============
@web.middleware
async def cors_middleware(request: web.Request, handler: Any) -> web.Response:
    if request.method == "OPTIONS":
        response = web.Response()
    else:
        response = await handler(request)
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, DELETE, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "*"
    return response


# ============ 文件上传 ============
async def handle_upload(request: web.Request) -> web.Response:
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
    resp = await client.get(f"{REST_URL}/rooms?select=id&id=eq.{room_id}")
    if not resp.json():
        return web.json_response({"success": False, "message": "房间不存在"}, status=404)

    # 读取文件到内存
    _read_chunk = getattr(field, "read_chunk")
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await _read_chunk(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > MAX_FILE_SIZE:
            return web.json_response(
                {"success": False, "message": f"文件超过最大限制 {MAX_FILE_SIZE // (1024**2)}MB"},
                status=413,
            )
        chunks.append(chunk)
    data = b"".join(chunks)

    # 获取 MIME 类型
    file_type, _ = mimetypes.guess_type(filename)
    file_type = file_type or "application/octet-stream"

    try:
        # 上传到 Supabase Storage
        storage_key = await upload_file_to_storage(room_id, filename, data, file_type)
        # 保存元数据
        meta = await save_file_metadata(
            room_id=room_id,
            filename=filename,
            file_size=total,
            file_type=file_type,
            uploaded_by=uploader,
            retention=retention,
            storage_key=storage_key,
        )
    except Exception as e:
        log.error(f"上传失败: {e}")
        return web.json_response({"success": False, "message": f"文件上传失败: {e}"}, status=500)

    log.info(f"上传成功: {filename} ({total} bytes) -> 房间 {room_id}")

    # 通过 WebSocket 广播
    await broadcast_to_room(room_id, {"type": "new_file", "file": meta})

    return web.json_response({"success": True, "file": meta})


# ============ 文件下载 ============
async def handle_download(request: web.Request) -> web.Response:
    """通过 authenticated 端点代理下载私有桶文件"""
    file_id = request.match_info.get("file_id", "")

    client = get_client()
    resp = await client.get(f"{REST_URL}/files?select=*&id=eq.{file_id}")
    rows = resp.json()
    if not isinstance(rows, list) or not rows:
        return web.json_response({"success": False, "message": "文件不存在"}, status=404)

    file_info = rows[0]
    storage_key = file_info.get("storage_path", "")
    original_name = file_info.get("original_name", file_info.get("filename", "download"))
    if not storage_key:
        return web.json_response({"success": False, "message": "文件路径无效"}, status=404)

    try:
        content, content_type = await download_file_content(storage_key)
    except Exception as e:
        return web.json_response({"success": False, "message": f"下载失败: {e}"}, status=500)

    # 直接返回文件内容（正确 MIME + 原始文件名）
    return web.Response(
        body=content,
        content_type=content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{original_name}"',
        },
    )


# ============ 文件预览（图片/视频/动图内联显示）============
async def handle_file_view(request: web.Request) -> web.Response:
    """返回文件内容，不带 attachment 头，浏览器直接渲染"""
    file_id = request.match_info.get("file_id", "")

    client = get_client()
    resp = await client.get(f"{REST_URL}/files?select=*&id=eq.{file_id}")
    rows = resp.json()
    if not isinstance(rows, list) or not rows:
        return web.json_response({"success": False, "message": "文件不存在"}, status=404)

    file_info = rows[0]
    storage_key = file_info.get("storage_path", "")
    if not storage_key:
        return web.json_response({"success": False, "message": "文件路径无效"}, status=404)

    try:
        content, content_type = await download_file_content(storage_key)
    except Exception as e:
        return web.json_response({"success": False, "message": f"加载失败: {e}"}, status=500)

    return web.Response(
        body=content,
        content_type=content_type,
    )


# ============ 房间背景上传 ============
async def handle_background_upload(request: web.Request) -> web.Response:
    """上传房间背景图片 → Supabase Storage"""
    reader = await request.multipart()
    field = await reader.next()
    if field is None or getattr(field, "name", None) != "file":
        return web.json_response({"success": False, "message": "缺少文件字段"}, status=400)

    filename = getattr(field, "filename", None) or "background"
    room_id = request.query.get("room_id", "").strip().upper()
    username = request.query.get("username", "").strip()

    if not room_id:
        return web.json_response({"success": False, "message": "缺少 room_id"}, status=400)
    if not username:
        return web.json_response({"success": False, "message": "缺少 username"}, status=400)

    # 验证房间存在且操作者是创建者
    client = get_client()
    resp = await client.get(f"{REST_URL}/rooms?select=id,creator,background&id=eq.{room_id}")
    rows = resp.json()
    if not rows:
        return web.json_response({"success": False, "message": "房间不存在"}, status=404)
    if rows[0]["creator"] != username:
        return web.json_response({"success": False, "message": "只有房间创建者才能管理背景"}, status=403)

    # 检查文件类型
    ext = Path(filename).suffix.lower()
    allowed_exts = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}
    if ext not in allowed_exts:
        return web.json_response(
            {"success": False, "message": f"不支持的图片格式，支持: {', '.join(allowed_exts)}"},
            status=400,
        )

    # 读取文件到内存
    _read_chunk = getattr(field, "read_chunk")
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await _read_chunk(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > MAX_BG_SIZE:
            return web.json_response({"success": False, "message": "背景图片不能超过 10MB"}, status=413)
        chunks.append(chunk)
    data = b"".join(chunks)

    try:
        # 清理旧背景
        old_bg = rows[0].get("background")
        if old_bg:
            await delete_background_by_url(old_bg)

        # 上传新背景到 Storage
        bg_url = await upload_background_to_storage(room_id, data, ext)

        # 更新数据库
        await client.patch(
            f"{REST_URL}/rooms?id=eq.{room_id}",
            json={"background": bg_url},
        )
    except Exception as e:
        return web.json_response({"success": False, "message": f"背景上传失败: {e}"}, status=500)

    log.info(f"房间 {room_id} 背景已更新")

    return web.json_response({
        "success": True,
        "message": "背景上传成功",
        "room_id": room_id,
        "background": bg_url,
    })


# ============ 健康检查 ============
async def handle_health(_request: web.Request) -> web.Response:
    return web.json_response({"status": "ok"})


# ============ 表情包管理 ============
async def handle_sticker_list(request: web.Request) -> web.Response:
    """获取房间表情包列表"""
    room_id = request.match_info.get("room_id", "")
    client = get_client()
    resp = await client.get(
        f"{REST_URL}/stickers?select=id,storage_key,uploaded_by,created_at"
        f"&room_id=eq.{room_id}&order=created_at.asc"
    )
    rows = resp.json()
    if not isinstance(rows, list):
        return web.json_response({"success": True, "stickers": []})
    return web.json_response({"success": True, "stickers": rows})


async def handle_sticker_upload(request: web.Request) -> web.Response:
    """上传表情包：multipart file → Storage + stickers表（不走 files 表，不广播）"""
    reader = await request.multipart()
    field = await reader.next()
    if field is None or getattr(field, "name", None) != "file":
        return web.json_response({"success": False, "message": "缺少文件"}, status=400)

    filename = getattr(field, "filename", "sticker.png")
    room_id = request.query.get("room_id", "").strip().upper()
    uploader = request.query.get("uploader", "").strip()
    if not room_id or not uploader:
        return web.json_response({"success": False, "message": "缺少参数"}, status=400)

    _read_chunk = getattr(field, "read_chunk")
    chunks = []
    total = 0
    while True:
        chunk = await _read_chunk(1024 * 1024)
        if not chunk: break
        total += len(chunk)
        if total > MAX_FILE_SIZE:
            return web.json_response({"success": False, "message": "文件过大"}, status=413)
        chunks.append(chunk)
    data = b"".join(chunks)
    file_type, _ = mimetypes.guess_type(filename)
    file_type = file_type or "image/png"

    try:
        import re, time as _time
        file_uuid = __import__("uuid").uuid4().hex[:8]
        safe_name = filename.encode("ascii", "ignore").decode("ascii") or "file"
        ext = safe_name.rsplit(".", 1)[-1] if "." in safe_name else ""
        safe_key = f"{file_uuid}.{ext}" if ext else file_uuid
        storage_key = await upload_file_to_storage(room_id, safe_key, data, file_type)

        now = _time.time()
        client = get_client()
        sresp = await client.post(f"{REST_URL}/stickers", json={
            "room_id": room_id,
            "file_id": file_uuid,
            "storage_key": storage_key,
            "uploaded_by": uploader,
            "created_at": now,
        })
        if sresp.status_code >= 400:
            detail = sresp.text[:200]
            log.error(f"表情包入库失败: {detail}")
            return web.json_response({"success": False, "message": f"入库失败: {detail}"}, status=500)
        sticker_data = sresp.json()
        sid = sticker_data[0]["id"] if isinstance(sticker_data, list) and sticker_data else None
        return web.json_response({"success": True, "sticker": {
            "id": sid, "storage_key": storage_key, "filename": filename,
        }})
    except Exception as e:
        log.error(f"表情包异常: {e}")
        return web.json_response({"success": False, "message": str(e)}, status=500)


async def handle_sticker_view(request: web.Request) -> web.Response:
    """预览表情包图片（不经过 files 表）"""
    sticker_id = request.match_info.get("sticker_id", "")
    client = get_client()
    resp = await client.get(f"{REST_URL}/stickers?select=storage_key&id=eq.{sticker_id}")
    rows = resp.json()
    if not isinstance(rows, list) or not rows:
        return web.json_response({"success": False, "message": "不存在"}, status=404)
    storage_key = rows[0].get("storage_key", "")
    if not storage_key:
        return web.json_response({"success": False, "message": "路径无效"}, status=404)
    try:
        content, content_type = await download_file_content(storage_key)
    except Exception as e:
        return web.json_response({"success": False, "message": str(e)}, status=500)
    return web.Response(body=content, content_type=content_type)


async def handle_sticker_delete(request: web.Request) -> web.Response:
    """删除表情包记录"""
    sticker_id = request.match_info.get("sticker_id", "")
    client = get_client()
    await client.delete(f"{REST_URL}/stickers?id=eq.{sticker_id}")
    return web.json_response({"success": True})


# ============ 应用工厂 ============
def create_app() -> web.Application:
    """创建并配置 aiohttp Application"""
    app = web.Application(client_max_size=MAX_FILE_SIZE * 2, middlewares=[cors_middleware])

    # WebSocket
    app.router.add_route("GET", "/ws", ws_handler)

    # API
    app.router.add_route("POST", "/api/upload", handle_upload)
    app.router.add_route("POST", "/api/upload_background", handle_background_upload)
    app.router.add_route("GET", "/api/files/{file_id}", handle_download)
    app.router.add_route("GET", "/api/files/{file_id}/view", handle_file_view)
    app.router.add_route("GET", "/api/health", handle_health)
    # 表情包
    app.router.add_route("GET", "/api/stickers/{room_id}", handle_sticker_list)
    app.router.add_route("GET", "/api/stickers/view/{sticker_id}", handle_sticker_view)
    app.router.add_route("POST", "/api/stickers", handle_sticker_upload)
    app.router.add_route("DELETE", "/api/stickers/{sticker_id}", handle_sticker_delete)

    # 静态文件
    app.router.add_route("GET", "/", _serve_static(STATIC_DIR / "index.html"))
    app.router.add_static("/css", STATIC_DIR / "css", show_index=False)
    app.router.add_static("/js", STATIC_DIR / "js", show_index=False)
    return app


def _serve_static(path: Path) -> Any:
    async def handler(_request: web.Request) -> web.StreamResponse:
        return web.FileResponse(path)
    return handler
