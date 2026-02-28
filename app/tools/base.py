from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from ..core.types import ModelInfo


@dataclass(frozen=True)
class ToolContext:
    session_id: str
    model: ModelInfo
    caller_user_id: str | None = None
    caller_message_type: str | None = None


ToolHandler = Callable[[dict[str, Any], ToolContext], Awaitable[Any]]


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: ToolHandler

    def openai_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }
