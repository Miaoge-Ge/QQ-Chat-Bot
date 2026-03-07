from __future__ import annotations

from ..config import settings
from .builtin import ALL_BUILTIN_TOOLS
from .enabled_tools import is_enabled
from .registry import ToolRegistry


def build_tool_registry() -> ToolRegistry:
    reg = ToolRegistry()
    for t in ALL_BUILTIN_TOOLS:
        if not is_enabled(t.name):
            continue
        if t.name == "web_search" and not settings.WEB_SEARCH_ENABLED:
            continue
        reg.register(t)

    return reg
