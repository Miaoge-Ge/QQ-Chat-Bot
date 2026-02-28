from __future__ import annotations

import base64
import mimetypes
import os
import urllib.parse

import httpx
from loguru import logger

from .http_client import get_client


async def download_image_as_base64(url: str, timeout_s: float = 30.0) -> str | None:
    """下载图片并转换为 data URL (Base64)"""
    s = (url or "").strip()
    if not s:
        return None
    if s.startswith("data:"):
        return s

    raw: bytes | None = None
    mime = ""

    if s.startswith(("http://", "https://")):
        try:
            client = get_client()
            headers = {
                "User-Agent": "Mozilla/5.0",
                "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
            }
            try:
                host = (urllib.parse.urlparse(s).hostname or "").lower()
            except ValueError:
                host = ""
            if host.endswith("qq.com") or host.endswith("qq.com.cn"):
                headers["Referer"] = "https://nt.qq.com/"
            resp = await client.get(s, timeout=timeout_s, follow_redirects=True, headers=headers)
            if resp.status_code != 200:
                return None
            ct = resp.headers.get("Content-Type", "")
            if isinstance(ct, str) and ct.lower().startswith("text/"):
                return None
            raw = resp.content
            if ct:
                mime = ct.split(";", 1)[0].strip()
        except httpx.HTTPError as e:
            logger.debug("download_image_failed: {}: {}", s, e)
            return None
    elif s.startswith("file://") or s.startswith("/"):
        p = s
        if p.startswith("file://"):
            try:
                u = urllib.parse.urlparse(p)
                p = urllib.parse.unquote(u.path or "")
            except ValueError:
                return None
        
        # 安全检查：禁止读取敏感目录
        # 只允许读取 data/images 目录下的文件，或者系统明确允许的临时目录
        p = os.path.abspath(p)
        allowed_dir = os.path.abspath(os.path.join(os.getcwd(), "data"))
        if not p.startswith(allowed_dir):
            # 记录安全警告
            return None

        if not os.path.exists(p):
            return None
        try:
            with open(p, "rb") as f:
                raw = f.read()
            mime = mimetypes.guess_type(p)[0] or ""
        except OSError:
            return None
    
    if raw is None:
        return None
        
    if not mime:
        mime = "image/png"  # Default fallback
        
    b64 = base64.b64encode(raw).decode("ascii")
    return f"data:{mime};base64,{b64}"
