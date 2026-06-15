"""
文件管理：上传元数据、查询、删除、清理
"""
import shutil
import time
import uuid
from pathlib import Path
from typing import Any

from .config import FILE_RETENTION, REST_URL, UPLOAD_DIR, get_client


async def ensure_files_table():
    """确保 files 表存在"""
    client = get_client()
    url = f"{REST_URL}/files?limit=1"
    resp = await client.get(url)
    if resp.status_code >= 400:
        print(f"[文件] 请先在 Supabase 中创建 files 表，SQL 见 README.md")
    else:
        print(f"[文件] files 表已就绪")


async def save_file_metadata(
    room_id: str,
    filename: str,
    file_size: int,
    file_type: str,
    uploaded_by: str,
    retention: str,
    storage_path: str,
) -> dict[str, object]:
    """保存文件元数据到 Supabase"""
    client = get_client()
    file_id = uuid.uuid4().hex[:12]
    now = time.time()
    retention_seconds = FILE_RETENTION.get(retention)
    expires_at = (now + retention_seconds) if retention_seconds else None

    resp = await client.post(
        f"{REST_URL}/files",
        json={
            "id": file_id,
            "room_id": room_id,
            "filename": filename,
            "file_size": file_size,
            "file_type": file_type,
            "uploaded_by": uploaded_by,
            "retention": retention,
            "expires_at": expires_at,
            "created_at": now,
            "storage_path": storage_path,
        },
    )
    if resp.status_code >= 400:
        detail = resp.text[:300]
        print(f"[文件] 元数据保存失败 ({resp.status_code}): {detail}")
        raise RuntimeError(f"文件元数据保存失败: {detail}")
    return {
        "id": file_id,
        "room_id": room_id,
        "filename": filename,
        "file_size": file_size,
        "file_type": file_type,
        "uploaded_by": uploaded_by,
        "retention": retention,
        "expires_at": expires_at,
        "created_at": now,
    }


async def get_room_files(room_id: str) -> list[dict[str, object]]:
    """获取房间文件列表"""
    client = get_client()
    url = f"{REST_URL}/files?select=*&room_id=eq.{room_id}&order=created_at.desc&limit=100"
    resp = await client.get(url)
    rows = resp.json()
    if not isinstance(rows, list):
        return []
    return list(rows)


async def delete_file_record(file_id: str) -> bool:
    """删除文件记录和磁盘文件"""
    client = get_client()
    url = f"{REST_URL}/files?select=storage_path&id=eq.{file_id}"
    resp = await client.get(url)
    rows = resp.json()
    if isinstance(rows, list) and rows:
        row = rows[0]
        storage_path = row.get("storage_path", "")
        if storage_path:
            file_path = Path(storage_path)
            if file_path.exists():
                file_path.unlink()
    await client.delete(f"{REST_URL}/files?id=eq.{file_id}")
    return True


async def delete_room_files(room_id: str):
    """删除房间的所有文件（磁盘 + 数据库记录）"""
    client = get_client()
    url = f"{REST_URL}/files?select=storage_path&room_id=eq.{room_id}"
    resp = await client.get(url)
    rows = resp.json()
    if isinstance(rows, list):
        for row in rows:
            storage_path = row.get("storage_path", "")
            if storage_path:
                file_path = Path(storage_path)
                if file_path.exists():
                    file_path.unlink()
    # 删除房间上传目录
    room_dir = UPLOAD_DIR / room_id
    if room_dir.exists():
        shutil.rmtree(room_dir, ignore_errors=True)
    await client.delete(f"{REST_URL}/files?room_id=eq.{room_id}")


async def cleanup_expired_files():
    """清理过期的文件"""
    now = time.time()
    client = get_client()
    url = f"{REST_URL}/files?select=id,storage_path&expires_at=lt.{now}&expires_at=not.is.null"
    resp = await client.get(url)
    rows = resp.json()
    if isinstance(rows, list):
        for row in rows:
            storage_path = row.get("storage_path", "")
            if storage_path:
                file_path = Path(storage_path)
                if file_path.exists():
                    file_path.unlink()
            await client.delete(f"{REST_URL}/files?id=eq.{row['id']}")
            print(f"[文件清理] 已删除过期文件: {row.get('id')}")
        if rows:
            print(f"[文件清理] 共清理 {len(rows)} 个过期文件")
