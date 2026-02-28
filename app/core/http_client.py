from __future__ import annotations
from typing import Optional
import httpx

_client: Optional[httpx.AsyncClient] = None

def get_client() -> httpx.AsyncClient:
    """获取全局共享的 HTTP 客户端实例"""
    global _client
    if _client is None or _client.is_closed:
        # 设置合理的默认超时，应用层可在请求时覆盖
        _client = httpx.AsyncClient(timeout=30.0, follow_redirects=True)
    return _client

async def close_client() -> None:
    """关闭全局 HTTP 客户端"""
    global _client
    if _client is not None and not _client.is_closed:
        await _client.aclose()
    _client = None
