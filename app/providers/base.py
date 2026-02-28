from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Literal

from ..core.types import ChatMessage, ModelInfo, ToolCall


class LLMResponse:
    def __init__(self, content: str, tool_calls: list[ToolCall] | None = None, raw: Any | None = None):
        self.content = content
        self.tool_calls = tool_calls or []
        self.raw = raw


class LLMProvider(ABC):
    @property
    @abstractmethod
    def model_info(self) -> ModelInfo: ...

    @abstractmethod
    async def chat(self, messages: list[ChatMessage], tools: list[dict[str, Any]]) -> LLMResponse: ...

    @staticmethod
    def provider_name() -> Literal["openai_compat"]:
        raise NotImplementedError
