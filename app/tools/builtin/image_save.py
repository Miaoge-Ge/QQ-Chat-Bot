from __future__ import annotations

import os
import re
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from ...core.http_client import get_client
from ...tools.base import Tool


_ALLOWED_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tif", ".tiff", ".ico"}
_CT_TO_EXT = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/bmp": ".bmp",
    "image/tiff": ".tiff",
    "image/x-icon": ".ico",
    "image/vnd.microsoft.icon": ".ico",
}


def _is_url(s: str) -> bool:
    try:
        u = urlparse(s)
        return u.scheme in ("http", "https") and bool(u.netloc)
    except ValueError:
        return False


def _safe_basename(name: str) -> str:
    s = (name or "").strip().replace("\\", "/")
    s = s.rsplit("/", 1)[-1]
    s = re.sub(r"[^A-Za-z0-9._-]+", "_", s)
    s = s.strip("._-")
    return s[:120] if s else ""


def _pick_ext_from_name(name: str) -> str | None:
    if not name:
        return None
    ext = Path(name).suffix.lower()
    return ext if ext in _ALLOWED_EXTS else None


def _pick_ext_from_content_type(ct: Any) -> str | None:
    if not isinstance(ct, str):
        return None
    c = ct.split(";", 1)[0].strip().lower()
    return _CT_TO_EXT.get(c)


async def tool_handler(args: dict[str, Any], _ctx) -> dict[str, Any]:
    image_ref = str(args.get("image_ref") or "").strip()
    if not image_ref:
        return {"error": "missing_image_ref"}

    filename = _safe_basename(str(args.get("filename") or "").strip())
    ext = _pick_ext_from_name(filename) or _pick_ext_from_name(image_ref) or ".png"

    base_dir = Path("./data/image_save").resolve()
    try:
        base_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        return {"error": "mkdir_failed", "message": str(e)}

    out_name = filename
    if not out_name:
        out_name = f"{uuid.uuid4().hex}{ext}"
    else:
        if not Path(out_name).suffix:
            out_name = f"{out_name}{ext}"
        elif _pick_ext_from_name(out_name) is None:
            out_name = f"{Path(out_name).stem}{ext}"

    out_path = (base_dir / out_name).resolve()
    if os.path.commonpath([str(base_dir), str(out_path)]) != str(base_dir):
        return {"error": "invalid_filename"}

    if _is_url(image_ref):
        http = get_client()
        try:
            r = await http.get(image_ref, timeout=30.0, headers={"User-Agent": "new_bot/1.0"})
        except httpx.HTTPError as e:
            return {"error": "download_failed", "message": str(e)}
        if r.status_code >= 400:
            return {"error": "download_failed", "status_code": r.status_code}
        ct_ext = _pick_ext_from_content_type(r.headers.get("content-type"))
        if ct_ext and ct_ext != ext:
            out_path = (base_dir / f"{Path(out_name).stem}{ct_ext}").resolve()
        try:
            out_path.write_bytes(r.content)
        except OSError as e:
            return {"error": "write_failed", "message": str(e)}
    else:
        src = Path(image_ref).expanduser().resolve()
        if not src.exists() or not src.is_file():
            return {"error": "source_not_found"}
        src_ext = _pick_ext_from_name(src.name)
        if src_ext and src_ext != ext and not filename:
            out_path = (base_dir / f"{out_name}{src_ext}").resolve()
        try:
            out_path.write_bytes(src.read_bytes())
        except OSError as e:
            return {"error": "copy_failed", "message": str(e)}

    rel_path = os.path.relpath(str(out_path), str(Path(".").resolve()))
    return {"file_path": rel_path}


TOOL = Tool(
    name="image_save",
    description="保存图片：输入图片 URL 或本地路径，将图片保存到 data/image_save 目录。",
    parameters={
        "type": "object",
        "properties": {
            "image_ref": {"type": "string", "description": "图片 URL 或本地文件路径"},
            "filename": {"type": "string", "description": "可选：保存文件名（不含目录）"},
        },
        "required": ["image_ref"],
        "additionalProperties": False,
    },
    handler=tool_handler,
)
