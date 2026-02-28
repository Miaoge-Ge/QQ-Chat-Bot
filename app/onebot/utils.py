from __future__ import annotations

import re
from typing import Any


def strip_cq(text: str) -> str:
    return re.sub(r"\[CQ:[^\]]+\]", "", text or "").strip()


def _parse_cq_segments(text: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    s = text or ""
    i = 0
    for m in re.finditer(r"\[CQ:([a-zA-Z0-9_]+)(?:,([^\]]*))?\]", s):
        if m.start() > i:
            t = s[i : m.start()]
            if t:
                out.append({"type": "text", "data": {"text": t}})
        seg_type = m.group(1) or ""
        raw_params = m.group(2) or ""
        data: dict[str, Any] = {}
        if raw_params:
            for part in raw_params.split(","):
                if not part:
                    continue
                if "=" not in part:
                    continue
                k, v = part.split("=", 1)
                data[k] = v
        out.append({"type": seg_type, "data": data})
        i = m.end()
    if i < len(s):
        t = s[i:]
        if t:
            out.append({"type": "text", "data": {"text": t}})
    return out


def get_segments(event: dict[str, Any]) -> list[dict[str, Any]]:
    msg = event.get("message")
    if isinstance(msg, list):
        return [seg for seg in msg if isinstance(seg, dict)]
    if isinstance(msg, str) and msg:
        return _parse_cq_segments(msg)
    raw = event.get("raw_message")
    if isinstance(raw, str) and raw:
        return _parse_cq_segments(raw)
    return []


def extract_images(event: dict[str, Any]) -> list[dict[str, Any]]:
    segs = get_segments(event)
    out: list[dict[str, Any]] = []
    for seg in segs:
        if seg.get("type") != "image":
            continue
        data = seg.get("data")
        if isinstance(data, dict) and data:
            out.append(data)
    return out


def extract_reply_id(event: dict[str, Any]) -> str | None:
    segs = get_segments(event)
    for seg in segs:
        if seg.get("type") != "reply":
            continue
        data = seg.get("data")
        if not isinstance(data, dict):
            continue
        v = data.get("id")
        if v is None:
            continue
        s = str(v).strip()
        return s if s else None
    return None


def extract_text(event: dict[str, Any]) -> str:
    segs = get_segments(event)
    parts: list[str] = []
    for seg in segs:
        if seg.get("type") != "text":
            continue
        data = seg.get("data") or {}
        if not isinstance(data, dict):
            continue
        t = data.get("text")
        if isinstance(t, str) and t.strip():
            parts.append(t)
    return strip_cq(" ".join(parts))


def is_mentioned(event: dict[str, Any]) -> bool:
    if event.get("message_type") != "group":
        return False
    self_id = str(event.get("self_id", ""))
    for seg in get_segments(event):
        if seg.get("type") != "at":
            continue
        data = seg.get("data") or {}
        if not isinstance(data, dict):
            continue
        qq = data.get("qq")
        if qq is None:
            continue
        if str(qq) == self_id:
            return True
    return False
