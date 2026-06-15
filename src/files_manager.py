"""
文件管理：Supabase Storage 上传/下载/删除、元数据管理
"""
import json
import time
import uuid

from .config import (
    BACKGROUNDS_BUCKET, FILE_RETENTION, FILES_BUCKET,
    REST_URL, STORAGE_URL, get_client, get_storage_client, SUPABASE_URL,
)


# ============ Storage 辅助 ============

async def _ensure_buckets():
    """确保 Storage buckets 存在，不存在则创建"""
    client = get_storage_client()
    # 获取已有 buckets
    resp = await client.get(f"{STORAGE_URL}/bucket")
    existing = [b["name"] for b in (resp.json() or [])] if resp.status_code < 400 else []

    for bucket_name, is_public in [(FILES_BUCKET, False), (BACKGROUNDS_BUCKET, True)]:
        if bucket_name in existing:
            print(f"[存储] bucket '{bucket_name}' 已就绪")
            continue
        resp = await client.post(
            f"{STORAGE_URL}/bucket",
            json={"name": bucket_name, "public": is_public},
        )
        if resp.status_code < 400:
            print(f"[存储] bucket '{bucket_name}' 已创建 (public={is_public})")
        else:
            print(f"[存储] 创建 bucket '{bucket_name}' 失败: {resp.text[:200]}")


async def _upload_to_storage(bucket: str, key: str, data: bytes, content_type: str) -> str:
    """上传文件到 Storage，返回公开 URL 或 storage key"""
    client = get_storage_client()
    resp = await client.post(
        f"{STORAGE_URL}/object/{bucket}/{key}",
        content=data,
        headers={
            "Content-Type": content_type,
            "x-upsert": "true",
        },
    )
    if resp.status_code >= 400:
        detail = resp.text[:300]
        raise RuntimeError(f"Storage 上传失败 ({resp.status_code}): {detail}")
    return f"{SUPABASE_URL}/storage/v1/object/public/{bucket}/{key}"


async def _delete_from_storage(bucket: str, keys: list[str]):
    """从 Storage 删除文件"""
    if not keys:
        return
    client = get_storage_client()
    # 使用 request() 而非 delete()，因为旧版 httpx 的 delete() 不支持 body 参数
    resp = await client.request(
        method="DELETE",
        url=f"{STORAGE_URL}/object/{bucket}",
        content=json.dumps({"prefixes": keys}),
        headers={"Content-Type": "application/json"},
    )
    if resp.status_code >= 400:
        print(f"[存储] 删除失败 ({resp.status_code}): {resp.text[:200]}")


async def _delete_by_prefix(bucket: str, prefix: str):
    """删除 Storage 中指定前缀的所有文件"""
    client = get_storage_client()
    # 列出该前缀下的所有文件
    resp = await client.post(
        f"{STORAGE_URL}/object/list/{bucket}",
        json={"prefix": prefix, "limit": 1000},
    )
    if resp.status_code >= 400:
        print(f"[存储] 列出文件失败 ({resp.status_code}): {resp.text[:200]}")
        return
    items = resp.json()
    if not isinstance(items, list) or not items:
        return
    keys = [item["name"] for item in items if isinstance(item, dict) and "name" in item]
    await _delete_from_storage(bucket, keys)


async def _get_signed_url(bucket: str, key: str, expires_in: int = 3600) -> str:
    """生成带签名的临时下载 URL"""
    client = get_storage_client()
    resp = await client.post(
        f"{STORAGE_URL}/object/sign/{bucket}/{key}",
        json={"expires_in": expires_in},
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"签名 URL 生成失败: {resp.text[:200]}")
    data = resp.json()
    signed = data.get("signedURL") or data.get("signedUrl") or ""
    if not signed:
        raise RuntimeError("签名 URL 为空")
    # 补全域名（signedURL 可能是相对路径）
    if signed.startswith("/"):
        signed = f"{SUPABASE_URL}{signed}"
    return signed


# ============ Bucket 初始化 ============

async def ensure_files_table():
    """确保 files 表 和 Storage buckets 存在"""
    client = get_client()
    url = f"{REST_URL}/files?limit=1"
    resp = await client.get(url)
    if resp.status_code >= 400:
        print(f"[文件] 请先在 Supabase 中创建 files 表，SQL 见 README.md")
    else:
        print(f"[文件] files 表已就绪")

    await _ensure_buckets()


# ============ 文件元数据 ============

async def save_file_metadata(
    room_id: str,
    filename: str,
    file_size: int,
    file_type: str,
    uploaded_by: str,
    retention: str,
    storage_key: str,
) -> dict[str, object]:
    """保存文件元数据到 Supabase files 表"""
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
            "storage_path": storage_key,
        },
    )
    if resp.status_code >= 400:
        detail = resp.text[:300]
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
    """删除文件记录和 Storage 文件"""
    client = get_client()
    # 查询 storage_key
    url = f"{REST_URL}/files?select=storage_path&id=eq.{file_id}"
    resp = await client.get(url)
    rows = resp.json()
    if isinstance(rows, list) and rows:
        storage_key = rows[0].get("storage_path", "")
        if storage_key:
            # 从 Storage 删除
            await _delete_from_storage(FILES_BUCKET, [storage_key])
    # 删除数据库记录
    await client.delete(f"{REST_URL}/files?id=eq.{file_id}")
    return True


async def delete_room_files(room_id: str):
    """删除房间的所有文件（Storage + 数据库记录）"""
    # 从 Storage 删除该房间前缀下的所有文件
    await _delete_by_prefix(FILES_BUCKET, f"{room_id}/")
    # 删除数据库记录
    client = get_client()
    await client.delete(f"{REST_URL}/files?room_id=eq.{room_id}")


async def cleanup_expired_files():
    """清理过期的文件"""
    now = time.time()
    client = get_client()
    url = f"{REST_URL}/files?select=id,storage_path&expires_at=lt.{now}&expires_at=not.is.null"
    resp = await client.get(url)
    rows = resp.json()
    if isinstance(rows, list) and rows:
        keys = [r["storage_path"] for r in rows if r.get("storage_path")]
        if keys:
            await _delete_from_storage(FILES_BUCKET, keys)
        for r in rows:
            await client.delete(f"{REST_URL}/files?id=eq.{r['id']}")
            print(f"[文件清理] 已删除过期文件: {r.get('id')}")
        print(f"[文件清理] 共清理 {len(rows)} 个过期文件")


# ============ 供 routes.py 使用的公开接口 ============

async def upload_file_to_storage(room_id: str, filename: str, data: bytes, content_type: str) -> str:
    """上传聊天文件到 Storage，返回 storage_key"""
    file_uuid = uuid.uuid4().hex[:8]
    key = f"{room_id}/{file_uuid}_{filename}"
    await _upload_to_storage(FILES_BUCKET, key, data, content_type)
    return key


async def get_file_download_url(storage_key: str) -> str:
    """获取文件的签名下载 URL（1小时有效）"""
    return await _get_signed_url(FILES_BUCKET, storage_key)


async def upload_background_to_storage(room_id: str, data: bytes, ext: str) -> str:
    """上传房间背景到 Storage，返回公开 URL"""
    file_uuid = uuid.uuid4().hex[:8]
    key = f"{room_id}_{file_uuid}{ext}"
    content_type = {
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".png": "image/png", ".gif": "image/gif",
        ".webp": "image/webp", ".bmp": "image/bmp",
    }.get(ext, "image/png")
    url = await _upload_to_storage(BACKGROUNDS_BUCKET, key, data, content_type)
    return url


async def delete_background_by_url(bg_url: str):
    """根据公开 URL 删除背景文件"""
    if not bg_url:
        return
    # URL 格式: {SUPABASE_URL}/storage/v1/object/public/{bucket}/{key}
    prefix = "/storage/v1/object/public/"
    idx = bg_url.find(prefix)
    if idx < 0:
        return
    rest = bg_url[idx + len(prefix):]
    # rest = "room-backgrounds/key"
    bucket_end = rest.find("/")
    if bucket_end < 0:
        return
    key = rest[bucket_end + 1:]
    await _delete_from_storage(BACKGROUNDS_BUCKET, [key])


async def get_background_public_url(room_id: str, data: bytes, ext: str) -> str:
    """上传并返回公开背景 URL"""
    return await upload_background_to_storage(room_id, data, ext)
