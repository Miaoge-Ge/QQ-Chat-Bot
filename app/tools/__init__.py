from __future__ import annotations

from ..config import settings
from .builtin import BUILTIN_TOOLS
from .registry import ToolRegistry


def build_tool_registry() -> ToolRegistry:
    reg = ToolRegistry()
    for t in BUILTIN_TOOLS:
        if t.name == "web_search" and not settings.WEB_SEARCH_ENABLED:
            continue
        reg.register(t)

    # Always register image tools if they are available
    from .builtin import image_understand
    reg.register(image_understand.TOOL)

    return reg
