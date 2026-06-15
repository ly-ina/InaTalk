"""
定时清理：过期房间 & 过期文件
"""
import asyncio
import time
from datetime import datetime, timedelta
from pathlib import Path

from .config import CLEANUP_HOUR, CLEANUP_MINUTE, REST_URL, ROOM_EXPIRE_DAYS, get_client
from .files_manager import cleanup_expired_files, delete_room_files


async def cleanup_expired_rooms():
    """清理过期房间（含消息、文件、背景）"""
    cutoff = int(time.time() - ROOM_EXPIRE_DAYS * 86400)
    client = get_client()
    url = f"{REST_URL}/rooms?select=id,name,background&last_activity=lt.{cutoff}"
    resp = await client.get(url)
    data = resp.json()
    if isinstance(data, dict):
        if "message" in data:
            print(f"[清理] API 错误: {data.get('message')}")
            return
        if "id" in data:
            data = [data]
        else:
            return
    if not isinstance(data, list):
        return
    for r in data:
        if isinstance(r, dict) and "id" in r:
            room_id = r["id"]
            # 删除背景文件
            bg = r.get("background")
            if bg:
                bg_path = Path(bg)
                if bg_path.exists():
                    bg_path.unlink(missing_ok=True)
            # 删除房间文件
            await delete_room_files(room_id)
            # 删除房间消息
            await client.delete(f"{REST_URL}/messages?room_id=eq.{room_id}")
            # 删除房间
            await client.delete(f"{REST_URL}/rooms?id=eq.{room_id}")
            print(f"[清理] 已删除过期房间: {r['name']} ({room_id})")
    if data:
        print(f"[清理] 共清理 {len(data)} 个过期房间")


async def cleanup_scheduler():
    """每天定时执行清理任务"""
    while True:
        now = datetime.now()
        next_run = now.replace(hour=CLEANUP_HOUR, minute=CLEANUP_MINUTE, second=0, microsecond=0)
        if now >= next_run:
            next_run += timedelta(days=1)
        wait_seconds = (next_run - now).total_seconds()
        print(f"[清理] 下次清理时间: {next_run.strftime('%Y-%m-%d %H:%M:%S')} (等待 {wait_seconds:.0f} 秒)")
        await asyncio.sleep(wait_seconds)
        await cleanup_expired_rooms()
        await cleanup_expired_files()
