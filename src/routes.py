"""
HTTP 路由：文件上传/下载、健康检查、静态资源、CORS 中间件
"""
import mimetypes
import uuid
from pathlib import Path
from typing import Any

from aiohttp import web

from .config import FILE_RETENTION, MAX_FILE_SIZE, REST_URL, STATIC_DIR, UPLOAD_DIR, get_client
from .files_manager import save_file_metadata
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
    file_msg: dict[str, object] = {"type": "new_file", "file": meta}
    await broadcast_to_room(room_id, file_msg)

    return web.json_response({"success": True, "file": meta})


# ============ 文件下载 ============
async def handle_download(request: web.Request) -> web.Response:
    file_id = request.match_info.get("file_id", "")

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

    return web.FileResponse(
        path=file_path,
        headers={
            "Content-Disposition": f'attachment; filename="{file_info["filename"]}"',
            "Content-Type": file_info.get("file_type", "application/octet-stream"),
        },
    )


# ============ 健康检查 ============
async def handle_health(_request: web.Request) -> web.Response:
    return web.json_response({"status": "ok"})


# ============ 应用工厂 ============
def create_app() -> web.Application:
    """创建并配置 aiohttp Application"""
    app = web.Application(client_max_size=MAX_FILE_SIZE, middlewares=[cors_middleware])

    # WebSocket
    app.router.add_route("GET", "/ws", ws_handler)

    # API
    app.router.add_route("POST", "/api/upload", handle_upload)
    app.router.add_route("GET", "/api/files/{file_id}", handle_download)
    app.router.add_route("GET", "/api/health", handle_health)

    # 静态文件（URL 路径保持不变，文件在 static/ 目录下）
    app.router.add_route("GET", "/", _serve_static(STATIC_DIR / "index.html"))
    app.router.add_route("GET", "/app.js", _serve_static(STATIC_DIR / "js" / "app.js"))
    app.router.add_route("GET", "/style.css", _serve_static(STATIC_DIR / "css" / "style.css"))
    return app


def _serve_static(path: Path) -> Any:
    async def handler(_request: web.Request) -> web.StreamResponse:
        return web.FileResponse(path)
    return handler
