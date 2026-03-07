from __future__ import annotations

import os
import re
import secrets
from pathlib import Path

from ...tools.base import Tool


_ALLOWED_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tif", ".tiff", ".ico"}


def _list_images(root: Path) -> list[Path]:
    out: list[Path] = []
    if not root.exists() or not root.is_dir():
        return out
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix.lower() in _ALLOWED_EXTS:
            out.append(p)
    return out


def _safe_basename(name: str) -> str:
    s = (name or "").strip().replace("\\", "/")
    s = s.rsplit("/", 1)[-1]
    s = re.sub(r"[\x00-\x1f<>:\"/\\|?*]+", "_", s)
    s = re.sub(r"\s+", " ", s).strip()
    s = s.strip().strip(".")
    return s[:120] if s else ""


def _find_by_name(root: Path, desired: str) -> list[Path]:
    d = _safe_basename(desired)
    if not d or not root.exists() or not root.is_dir():
        return []
    want_ext = Path(d).suffix.lower()
    has_ext = want_ext in _ALLOWED_EXTS
    d_low = d.lower()
    stem_low = Path(d).stem.lower()
    out: list[Path] = []
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix.lower() not in _ALLOWED_EXTS:
            continue
        if has_ext:
            if p.name.lower() == d_low:
                out.append(p)
        else:
            ps = p.stem.lower()
            if ps == stem_low or ps.startswith(stem_low + "_"):
                out.append(p)
    def _k(p: Path) -> tuple[float, str]:
        try:
            ts = float(p.stat().st_mtime)
        except OSError:
            ts = 0.0
        return (ts, str(p))

    return sorted(out, key=_k, reverse=True)


async def tool_handler(args, _ctx):
    name = ""
    if isinstance(args, dict):
        name = str(args.get("name") or args.get("filename") or "").strip()

    root = Path(__file__).resolve().parents[3]
    save_dir = (root / "data" / "image_save").resolve()
    repo_dir = (root / "data" / "image_repo").resolve()

    if name:
        matches = _find_by_name(save_dir, name)
        if matches:
            pick = matches[0]
            return {"file_path": str(pick)}
        matches = _find_by_name(repo_dir, name)
        if matches:
            pick = matches[0]
            return {"file_path": str(pick)}

    images = _list_images(repo_dir)
    if not images:
        return {"error": "empty_repo"}
    pick = secrets.choice(images)
    return {"file_path": str(pick)}


TOOL = Tool(
    name="image_repo_random",
    description="发送图片：可按名称匹配（data/image_save 与 data/image_repo），否则从 data/image_repo 随机选择一张。",
    parameters={
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "可选：图片名称（带或不带扩展名）"},
            "filename": {"type": "string", "description": "可选：图片名称（兼容旧字段）"},
        },
        "required": [],
        "additionalProperties": False,
    },
    handler=tool_handler,
)
