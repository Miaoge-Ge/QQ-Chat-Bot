from __future__ import annotations

from ...tools.base import Tool

async def tool_handler(_args, ctx):
    m = getattr(ctx, "model", None)
    return {"provider": getattr(m, "provider", ""), "model": getattr(m, "model", "")}


TOOL = Tool(
    name="model_name",
    description="查询当前使用的模型提供商与模型名。",
    parameters={"type": "object", "properties": {}, "required": [], "additionalProperties": False},
    handler=tool_handler,
)
