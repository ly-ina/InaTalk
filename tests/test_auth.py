"""
测试认证模块：密码哈希、登录、session token
"""
import pytest
from unittest.mock import patch

from src.auth import hash_password, verify_password, create_session, validate_session, invalidate_session
from tests.conftest import mock_async_response, mock_client, set_mock_response


class TestPasswordHashing:
    def test_hash_produces_different_salts(self):
        h1, s1 = hash_password("test123")
        h2, s2 = hash_password("test123")
        assert s1 != s2
        assert h1 != h2

    def test_verify_correct_password(self):
        h, s = hash_password("mypass")
        assert verify_password("mypass", s, h)

    def test_verify_wrong_password(self):
        h, s = hash_password("mypass")
        assert not verify_password("wrong", s, h)

    def test_hash_output_length(self):
        h, s = hash_password("test")
        assert len(s) > 10
        assert len(h) > 20


class TestSessionToken:
    def test_create_and_validate(self):
        token = create_session("user1")
        assert validate_session(token) == "user1"

    def test_validate_invalid(self):
        assert validate_session("bad_token") is None

    def test_invalidate(self):
        token = create_session("user2")
        invalidate_session(token)
        assert validate_session(token) is None

    def test_unique_tokens(self):
        t1 = create_session("ua")
        t2 = create_session("ub")
        assert t1 != t2


@pytest.mark.asyncio
async def test_create_or_login_user_new():
    """mock 首次登录（用户不存在 → 创建）"""
    with patch("src.auth.get_client") as mock_get_client:
        mc = mock_client()
        set_mock_response(mc, "get", 200, json_data=[])
        set_mock_response(mc, "post", 201, json_data=[{"username": "newuser"}])
        mock_get_client.return_value = mc

        from src.auth import create_or_login_user
        result = await create_or_login_user("newuser", "pass123")
        assert result["success"] is True
        assert result["is_new"] is True


@pytest.mark.asyncio
async def test_create_or_login_user_existing_ok():
    """mock 已有用户登录（密码正确）"""
    h, s = hash_password("correct123")
    with patch("src.auth.get_client") as mock_get_client:
        mc = mock_client()
        set_mock_response(mc, "get", 200, json_data=[{"password_hash": h, "salt": s}])
        mock_get_client.return_value = mc

        from src.auth import create_or_login_user
        result = await create_or_login_user("existing", "correct123")
        assert result["success"] is True


@pytest.mark.asyncio
async def test_create_or_login_user_existing_wrong_password():
    """mock 已有用户登录（密码错误）"""
    h, s = hash_password("realpass")
    with patch("src.auth.get_client") as mock_get_client:
        mc = mock_client()
        set_mock_response(mc, "get", 200, json_data=[{"password_hash": h, "salt": s}])
        mock_get_client.return_value = mc

        from src.auth import create_or_login_user
        result = await create_or_login_user("existing", "wrongpass")
        assert result["success"] is False
