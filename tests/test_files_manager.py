"""
测试文件管理模块
"""
import pytest
from unittest.mock import patch

from tests.conftest import mock_client, set_mock_response


@pytest.mark.asyncio
async def test_save_file_metadata():
    with patch("src.files_manager.get_client") as mock_get_client:
        mc = mock_client()
        set_mock_response(mc, "post", 201, json_data=[{"id": "mock-file-id", "filename": "test.png", "file_size": 1024}])
        mock_get_client.return_value = mc

        from src.files_manager import save_file_metadata
        meta = await save_file_metadata(
            room_id="ABCD", filename="test.png", file_size=1024,
            file_type="image/png", uploaded_by="tester",
            retention="forever", storage_key="ABCD/test.png",
        )
        # save_file_metadata 生成的 ID 是 UUID，POST 返回的是 Supabase 数据
        assert len(meta["id"]) > 0
        assert meta["filename"] == "test.png"


@pytest.mark.asyncio
async def test_get_room_files():
    with patch("src.files_manager.get_client") as mock_get_client:
        mc = mock_client()
        set_mock_response(mc, "get", 200, json_data=[
            {"id": "f1", "filename": "a.jpg"}, {"id": "f2", "filename": "b.pdf"}
        ])
        mock_get_client.return_value = mc

        from src.files_manager import get_room_files
        files = await get_room_files("ROOM01")
        assert len(files) == 2


@pytest.mark.asyncio
async def test_download_file_content():
    with patch("src.files_manager.get_storage_client") as mock_get_client:
        mc = mock_client()
        set_mock_response(mc, "get", 200, text=b"fake-bytes")
        # 手动设置 headers
        mc.get.return_value.headers = {"content-type": "image/png"}
        mock_get_client.return_value = mc

        from src.files_manager import download_file_content
        content, ct = await download_file_content("ROOM/test.png")
        assert content == b"fake-bytes"
        assert ct == "image/png"


@pytest.mark.asyncio
async def test_upload_file_to_storage():
    with patch("src.files_manager.get_storage_client") as mock_get_client:
        mc = mock_client()
        set_mock_response(mc, "post", 200)
        mock_get_client.return_value = mc

        from src.files_manager import upload_file_to_storage
        key = await upload_file_to_storage("ROOM01", "photo.jpg", b"img", "image/jpeg")
        assert "ROOM01" in key
        assert all(ord(c) < 128 for c in key.split("/")[1])


@pytest.mark.asyncio
async def test_storage_key_no_chinese():
    with patch("src.files_manager.get_storage_client") as mock_get_client:
        mc = mock_client()
        set_mock_response(mc, "post", 200)
        mock_get_client.return_value = mc

        from src.files_manager import upload_file_to_storage
        key = await upload_file_to_storage("ROOM01", "测试.jpg", b"img", "image/jpeg")
        assert all(ord(c) < 128 for c in key)


@pytest.mark.asyncio
async def test_delete_file_record_not_found():
    with patch("src.files_manager.get_client") as mock_get_client:
        mc = mock_client()
        set_mock_response(mc, "get", 200, json_data=[])
        mock_get_client.return_value = mc

        from src.files_manager import delete_file_record
        ok = await delete_file_record("nonexistent")
        # 没找到文件也返回 True（因为没 key 可删，算成功）
        assert ok is True
