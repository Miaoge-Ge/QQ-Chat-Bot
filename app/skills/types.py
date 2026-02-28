from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class Skill(BaseModel):
    name: str
    version: str = "0.1.0"
    system_prompt: str | None = None
    enabled_tools: list[str] | None = None

    @classmethod
    def from_json(cls, data: Any) -> "Skill":
        return cls.model_validate(data)

