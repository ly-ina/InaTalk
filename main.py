"""
轻聊 - 临时 IM 系统 入口
启动方法：python main.py              （普通模式）
         python main.py --dev         （热更新模式）
"""
import asyncio
import sys

from aiohttp import web

from src.config import HOST, PORT, MAX_FILE_SIZE, MAX_MSG_PER_ROOM, ROOM_EXPIRE_DAYS, FILE_RETENTION, SUPABASE_URL
from src.cleanup import cleanup_expired_rooms, cleanup_scheduler
from src.files_manager import ensure_files_table, cleanup_expired_files
from src.routes import create_app


async def main():
    print(f"[服务] 数据库: Supabase ({SUPABASE_URL})")
    print(f"[服务] 房间过期时间: {ROOM_EXPIRE_DAYS} 天")
    print(f"[服务] 每房间消息上限: {MAX_MSG_PER_ROOM} 条")
    print(f"[服务] 文件大小限制: {MAX_FILE_SIZE // (1024**2)}MB")
    print(f"[服务] 文件保留选项: {', '.join(FILE_RETENTION.keys())}")

    await ensure_files_table()
    await cleanup_expired_rooms()
    await cleanup_expired_files()
    _ = asyncio.create_task(cleanup_scheduler())

    # 一体化服务：HTTP + WebSocket 在同一端口
    app = create_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, HOST, PORT)
    await site.start()
    print(f"[服务] 启动成功 → http://{HOST}:{PORT}")
    print(f"[服务] WebSocket → ws://{HOST}:{PORT}/ws")
    print(f"[服务] 在浏览器打开 http://localhost:{PORT} 即可使用")

    await asyncio.Future()


def run_dev():
    """热更新模式：监听 src/ 和 static/ 目录，文件变化时自动重启"""
    from watchfiles import run_process

    print("[热更新] 已启用，修改 .py/.html/.css/.js 文件将自动重启...")
    run_process(
        ".",
        target=f"{sys.executable} main.py",
        watch_filter=lambda _, path: (
            path.endswith(".py") or
            path.endswith(".html") or
            path.endswith(".css") or
            path.endswith(".js")
        ),
    )


if __name__ == "__main__":
    if "--dev" in sys.argv:
        run_dev()
    else:
        asyncio.run(main())
