"""
测试房间模块：创建、加入、删除
"""
import pytest
from unittest.mock import patch

from src.auth import hash_password
from src.rooms import create_room, join_room
from tests.conftest import mock_client, set_mock_response


@pytest.mark.asyncio
async def test_create_room() -> None:
    with patch("src.rooms.get_client") as mock_get_client:
        mc = mock_client()
        set_mock_response(mc, "get", 200, json_data=[])
        set_mock_response(mc, "post", 201, json_data=[
            {"id": "MOCK1234", "name": "测试房间", "creator": "tester", "password_hash": None, "last_activity": 1000.0}
        ])
        mock_get_client.return_value = mc

        result = await create_room("测试房间", "", "tester")
        assert result["success"] is True
        assert len(result["room"]["id"]) == 8


@pytest.mark.asyncio
async def test_create_room_with_password() -> None:
    with patch("src.rooms.get_client") as mock_get_client:
        mc = mock_client()
        set_mock_response(mc, "get", 200, json_data=[])
        set_mock_response(mc, "post", 201, json_data=[{"id": "BBBB1111", "name": "私密房"}])
        mock_get_client.return_value = mc

        result = await create_room("私密房", "secret123", "owner")
        assert result["success"] is True


@pytest.mark.asyncio
async def test_join_room_no_password() -> None:
    with patch("src.rooms.get_client") as mock_get_client:
        mc = mock_client()
        set_mock_response(mc, "get", 200, json_data=[
            {"id": "OPEN001", "name": "开放", "password_hash": None, "creator": "admin", "last_activity": 2000.0}
        ])
        mock_get_client.return_value = mc

        result = await join_room("OPEN001", "", "tester")
        assert result["success"] is True


@pytest.mark.asyncio
async def test_join_room_correct_password() -> None:
    h, s = hash_password("secret123")
    with patch("src.rooms.get_client") as mock_get_client:
        mc = mock_client()
        set_mock_response(mc, "get", 200, json_data=[
            {"id": "SECR0001", "name": "秘密", "password_hash": h, "salt": s, "creator": "admin", "last_activity": 2000.0}
        ])
        mock_get_client.return_value = mc

        result = await join_room("SECR0001", "secret123", "alice")
        assert result["success"] is True


@pytest.mark.asyncio
async def test_join_room_wrong_password() -> None:
    h, s = hash_password("realpass")
    with patch("src.rooms.get_client") as mock_get_client:
        mc = mock_client()
        set_mock_response(mc, "get", 200, json_data=[
            {"id": "SECR0001", "name": "秘密", "password_hash": h, "salt": s, "creator": "admin", "last_activity": 2000.0}
        ])
        mock_get_client.return_value = mc

        result = await join_room("SECR0001", "wrongpass", "bob")
        assert result["success"] is False


@pytest.mark.asyncio
async def test_join_nonexistent_room() -> None:
    with patch("src.rooms.get_client") as mock_get_client:
        mc = mock_client()
        set_mock_response(mc, "get", 200, json_data=[])
        mock_get_client.return_value = mc

        result = await join_room("DEADBEEF", "", "tester")
        assert result["success"] is False
