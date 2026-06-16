"""
测试消息模块
"""
import pytest
from unittest.mock import patch

from tests.conftest import mock_client, set_mock_response


@pytest.mark.asyncio
async def test_get_room_messages():
    with patch("src.messages.get_client") as mock_get_client:
        mc = mock_client()
        # Supabase 返回 desc order，get_room_messages 会 reversed → asc
        set_mock_response(mc, "get", 200, json_data=[
            {"username": "bob", "content": "Hi", "msg_type": "text", "created_at": 1100.0},
            {"username": "alice", "content": "你好", "msg_type": "text", "created_at": 1000.0},
        ])
        mock_get_client.return_value = mc

        from src.messages import get_room_messages
        msgs = await get_room_messages("ABCD")
        assert len(msgs) == 2
        # reversed 后 alice 在前
        assert msgs[0]["username"] == "alice"
        assert msgs[1]["username"] == "bob"


@pytest.mark.asyncio
async def test_get_room_messages_empty():
    with patch("src.messages.get_client") as mock_get_client:
        mc = mock_client()
        set_mock_response(mc, "get", 200, json_data=[])
        mock_get_client.return_value = mc

        from src.messages import get_room_messages
        msgs = await get_room_messages("EMPTY01")
        assert msgs == []


@pytest.mark.asyncio
async def test_get_room_files():
    with patch("src.messages.get_client") as mock_get_client:
        mc = mock_client()
        set_mock_response(mc, "get", 200, json_data=[
            {"id": "f1", "filename": "photo.jpg", "file_type": "image/jpeg"}
        ])
        mock_get_client.return_value = mc

        from src.messages import get_room_files
        files = await get_room_files("ABCD")
        assert len(files) == 1
        assert files[0]["filename"] == "photo.jpg"


@pytest.mark.asyncio
async def test_save_message():
    with patch("src.messages.get_client") as mock_get_client:
        mc = mock_client()
        set_mock_response(mc, "post", 201, json_data=[{"id": 1, "username": "alice", "content": "hello", "msg_type": "text", "created_at": 1000.0}])
        set_mock_response(mc, "get", 200, json_data=[])
        set_mock_response(mc, "patch", 200)
        mock_get_client.return_value = mc

        from src.messages import save_message
        msg = await save_message("ROOM", "alice", "hello")
        assert msg["username"] == "alice"
        assert msg["content"] == "hello"
