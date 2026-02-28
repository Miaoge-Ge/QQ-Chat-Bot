from __future__ import annotations

import time
from typing import Any

from ...config import settings
from ...runtime.sleep_state import SleepStore
from ...tools.base import Tool, ToolContext


def _parse_admin_ids(raw: str) -> set[str]:
    s = str(raw or "").strip()
    if not s:
        return set()
    out: set[str] = set()
    for part in s.replace("，", ",").split(","):
        v = part.strip()
        if v:
            out.add(v)
    return out


def _is_admin(ctx: ToolContext) -> bool:
    admins = _parse_admin_ids(settings.ADMIN_QQ_IDS)
    if not admins:
        return False
    uid = str(ctx.caller_user_id or "").strip()
    return bool(uid) and uid in admins


async def tool_handler(args: dict[str, Any], ctx: ToolContext):
    if not _is_admin(ctx):
        return {"error": "permission_denied", "reply": "无权限：仅管理员可使用该功能。"}

    action = str(args.get("action") or "").strip()
    hours_v = args.get("hours")
    store = SleepStore()

    if action == "shutdown":
        store.sleep_forever()
        return {"status": "ok", "reply": "机器人已进入睡眠模式。"}

    if action == "shutdown_in":
        try:
            h = float(hours_v)
        except (TypeError, ValueError):
            return {"error": "invalid_hours", "reply": "参数错误：hours 必须是数字。"}
        if h <= 0:
            return {"error": "invalid_hours", "reply": "参数错误：hours 必须大于 0。"}
        until_ts = time.time() + h * 3600.0
        until_s = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(until_ts))
        store.sleep_for_hours(h)
        return {"status": "ok", "reply": f"机器人将于 {until_s} 自动开机，现在进入睡眠。"}

    if action == "start":
        store.clear()
        return {"status": "ok", "reply": "机器人已恢复运行。"}

    return {"error": "invalid_action", "reply": "参数错误：action 必须是 shutdown / shutdown_in / start。"}


TOOL = Tool(
    name="admin_manage",
    description="管理工具：睡眠、定时睡眠、开始（唤醒）。仅管理员 QQ 可用。",
    parameters={
        "type": "object",
        "properties": {
            "action": {"type": "string", "description": "shutdown / shutdown_in / start"},
            "hours": {"type": "number", "description": "action=shutdown_in 时使用：X 小时后自动恢复"},
        },
        "required": ["action"],
        "additionalProperties": False,
    },
    handler=tool_handler,
)
