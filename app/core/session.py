from __future__ import annotations

from typing import Literal


def session_id(message_type: Literal["private", "group"], user_id: int, group_id: int | None) -> str:
    if message_type == "group":
        return f"group_{group_id or 0}"
    return f"private_{user_id}"

