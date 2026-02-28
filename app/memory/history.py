from __future__ import annotations

import json
import os
import threading
import time
from typing import Literal

from loguru import logger

from ..config import settings
from ..core.types import ChatMessage


class HistoryStore:
    def __init__(self, path: str | None = None):
        self._path = path or settings.HISTORY_PATH
        self._lock = threading.Lock()
        os.makedirs(os.path.dirname(os.path.abspath(self._path)), exist_ok=True)
        if not os.path.exists(self._path):
            with open(self._path, "w", encoding="utf-8") as f:
                f.write("")

    def _clamp(self, text: str) -> str:
        t = (text or "").strip()
        if len(t) <= settings.CONTEXT_MAX_CHARS:
            return t
        return t[-settings.CONTEXT_MAX_CHARS :].strip()

    def _keep(self, session_id: str) -> int:
        turns = settings.CONTEXT_TURNS_PRIVATE if session_id.startswith("private_") else settings.CONTEXT_TURNS_GROUP
        return max(2, turns * 2)

    def append(self, session_id: str, role: Literal["user", "assistant", "meta"], content: str) -> None:
        row = {"ts": int(time.time()), "session_id": session_id, "role": role, "content": self._clamp(content)}
        line = json.dumps(row, ensure_ascii=False)
        with self._lock:
            with open(self._path, "a", encoding="utf-8") as f:
                f.write(line + "\n")

    def _read_reverse_lines(self, buffer_size=8192):
        if not os.path.exists(self._path):
            return

        with open(self._path, "rb") as f:
            f.seek(0, os.SEEK_END)
            position = f.tell()
            remainder = b""

            while position > 0:
                delta = min(buffer_size, position)
                position -= delta
                f.seek(position)
                chunk = f.read(delta)
                chunk += remainder
                lines = chunk.split(b"\n")

                if position > 0:
                    remainder = lines[0]
                    lines = lines[1:]

                for line in reversed(lines):
                    if line.strip():
                        yield line.decode("utf-8", errors="ignore")

    def get_recent(self, session_id: str) -> list[ChatMessage]:
        keep = self._keep(session_id)
        rows: list[ChatMessage] = []
        with self._lock:
            try:
                for raw in self._read_reverse_lines():
                    try:
                        obj = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    if obj.get("session_id") != session_id:
                        continue
                    role = obj.get("role")
                    content = obj.get("content")
                    if role == "meta" and content == "__clear__":
                        break
                    if role in ("user", "assistant") and isinstance(content, str):
                        rows.append({"role": role, "content": content})
                    if len(rows) >= keep:
                        break
            except OSError:
                logger.opt(exception=True).error("Error reading history")
        rows.reverse()
        return rows
