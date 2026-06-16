"""
测试工具：mock httpx 异步响应
"""
from unittest.mock import AsyncMock, MagicMock


def mock_async_response(status=200, json_data=None, text="", headers=None):
    resp = MagicMock()
    resp.status_code = status
    resp.json = MagicMock(return_value=json_data if json_data is not None else [])
    resp.text = text
    resp.headers = headers or {}
    resp.content = text.encode() if isinstance(text, str) else (text or b"")
    return resp


def mock_client(**responses):
    """
    创建一个 mock httpx.AsyncClient，其 HTTP 方法返回一个支持 await 的对象。
    responses: {"method": {status, json_data, text}, ...}
    """
    client = MagicMock()
    for method in ["get", "post", "patch", "delete", "put"]:
        cfg = responses.get(method, {})
        resp = mock_async_response(
            status=cfg.get("status", 200),
            json_data=cfg.get("json_data"),
            text=cfg.get("text", ""),
            headers=cfg.get("headers"),
        )
        # 关键：把方法设为 AsyncMock，调用它返回 resp
        m = AsyncMock()
        m.return_value = resp
        setattr(client, method, m)
    return client


def set_mock_response(mock_client, method, status=200, json_data=None, text=""):
    resp = mock_async_response(status, json_data, text)
    getattr(mock_client, method).return_value = resp
