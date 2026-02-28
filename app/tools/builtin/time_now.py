from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from typing import Any

from ...tools.base import Tool

async def tool_handler(args: dict[str, Any], _ctx) -> dict[str, str]:
    tz = str(args.get("timezone") or "Asia/Shanghai").strip() or "Asia/Shanghai"
    try:
        z = ZoneInfo(tz)
    except ZoneInfoNotFoundError:
        z = ZoneInfo("Asia/Shanghai")
        tz = "Asia/Shanghai"
    now = datetime.now(tz=z)
    return {"iso": now.isoformat(), "timezone": tz}

TOOL = Tool(
    name="time_now",
    description="查询当前时间（默认东八区 Asia/Shanghai，返回 ISO 时间）。",
    parameters={
        "type": "object",
        "properties": {"timezone": {"type": "string", "description": "时区名称，例如 Asia/Shanghai"}},
        "required": [],
        "additionalProperties": False,
    },
    handler=tool_handler,
)
