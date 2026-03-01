from __future__ import annotations

import asyncio
import json
from typing import Any

from loguru import logger

from ..core.types import ToolCall, ToolResult
from .base import Tool, ToolContext


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    def list(self) -> list[Tool]:
        return list(self._tools.values())

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    async def run(self, calls: list[ToolCall], ctx: ToolContext) -> list[ToolResult]:
        out: list[ToolResult] = []
        for call in calls:
            tool = self.get(call["name"])
            if tool is None:
                out.append({"tool_call_id": call["id"], "name": call["name"], "result": {"error": "unknown_tool"}})
                continue
            try:
                args = call.get("arguments")
                if args is None:
                    args = {}
                if not isinstance(args, dict):
                    out.append({"tool_call_id": call["id"], "name": call["name"], "result": {"error": "invalid_arguments"}})
                    continue
                result: Any = await tool.handler(args, ctx)
                out.append({"tool_call_id": call["id"], "name": call["name"], "result": result})
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.opt(exception=True).warning(f"tool_failed: {call.get('name')}")
                msg = str(e)
                m2 = msg.lstrip()
                if m2.startswith("{") and len(m2) <= 20000:
                    try:
                        j = json.loads(m2)
                    except Exception:
                        j = None
                    if isinstance(j, dict):
                        err = j.get("error")
                        if isinstance(err, dict):
                            m = err.get("message")
                            if isinstance(m, str) and m.strip():
                                msg = m.strip().split("Request id:", 1)[0].strip()
                if len(msg) > 2000:
                    msg = msg[:2000].rstrip() + "…"
                out.append(
                    {
                        "tool_call_id": call["id"],
                        "name": call["name"],
                        "result": {"error": "tool_failed", "message": msg},
                    }
                )
        return out
