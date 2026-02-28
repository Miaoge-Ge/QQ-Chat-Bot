from __future__ import annotations

from .base import LLMProvider
from .openai_compat import OpenAICompatProvider


def build_provider() -> LLMProvider:
    return OpenAICompatProvider()
