from __future__ import annotations

import os
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


async def tool_handler(args, _ctx):
    _ = args
    repo_dir = Path("./data/image_repo").resolve()
    images = _list_images(repo_dir)
    if not images:
        return {"error": "empty_repo"}
    pick = secrets.choice(images)
    rel_path = os.path.relpath(str(pick), str(Path(".").resolve()))
    return {"file_path": rel_path}


TOOL = Tool(
    name="image_repo_random",
    description="随机发送图片：从 data/image_repo 目录下随机选择一张图片。",
    parameters={
        "type": "object",
        "properties": {},
        "required": [],
        "additionalProperties": False,
    },
    handler=tool_handler,
)

