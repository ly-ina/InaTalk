"""
HTTP 路由：文件上传/下载、健康检查、静态资源、CORS 中间件
"""
import mimetypes
from pathlib import Path
from typing import Any

from aiohttp import web

from .config import (
    FILE_RETENTION, MAX_BG_SIZE, MAX_FILE_SIZE, REST_URL,
    STATIC_DIR, get_client,
)
from .files_manager import (
    delete_background_by_url,
    get_file_download_url,
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
        print(f"[文件] 上传失败: {e}")
        return web.json_response({"success": False, "message": f"文件上传失败: {e}"}, status=500)

    print(f"[文件] 上传成功: {filename} ({total} bytes) -> 房间 {room_id}")

    # 通过 WebSocket 广播
    await broadcast_to_room(room_id, {"type": "new_file", "file": meta})

    return web.json_response({"success": True, "file": meta})


# ============ 文件下载 ============
async def handle_download(request: web.Request) -> web.Response:
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
        signed_url = await get_file_download_url(storage_key)
    except Exception as e:
        return web.json_response({"success": False, "message": f"获取下载链接失败: {e}"}, status=500)

    # 重定向到签名 URL
    raise web.HTTPFound(signed_url)


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

    print(f"[背景] 房间 {room_id} 背景已更新")

    return web.json_response({
        "success": True,
        "message": "背景上传成功",
        "room_id": room_id,
        "background": bg_url,
    })


# ============ 健康检查 ============
async def handle_health(_request: web.Request) -> web.Response:
    return web.json_response({"status": "ok"})


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
    app.router.add_route("GET", "/api/health", handle_health)

    # 静态文件
    app.router.add_route("GET", "/", _serve_static(STATIC_DIR / "index.html"))
    app.router.add_static("/css", STATIC_DIR / "css", show_index=False)
    app.router.add_static("/js", STATIC_DIR / "js", show_index=False)
    return app


def _serve_static(path: Path) -> Any:
    async def handler(_request: web.Request) -> web.StreamResponse:
        return web.FileResponse(path)
    return handler
