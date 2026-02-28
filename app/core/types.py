from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, TypedDict


Role = Literal["system", "user", "assistant", "tool"]


class ToolCall(TypedDict):
    id: str
    name: str
    arguments: dict[str, Any]


class ToolResult(TypedDict):
    tool_call_id: str
    name: str
    result: Any


class ChatMessage(TypedDict, total=False):
    role: Role
    content: str
    name: str
    tool_call_id: str
    tool_calls: list[ToolCall]


@dataclass(frozen=True)
class ModelInfo:
    provider: Literal["openai_compat"]
    model: str
