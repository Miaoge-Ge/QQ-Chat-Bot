from __future__ import annotations

import json
import os

from loguru import logger

from ..config import settings
from .types import Skill


def load_skills() -> list[Skill]:
    base = os.path.abspath(settings.SKILLS_DIR)
    enabled = [s.strip() for s in (settings.ENABLED_SKILLS or "").split(",") if s.strip()]
    if not enabled:
        enabled = ["default"]
    out: list[Skill] = []
    for name in enabled:
        p = os.path.join(base, name, "skill.json")
        if not os.path.exists(p):
            continue
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            out.append(Skill.from_json(data))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError, TypeError, ValueError):
            logger.opt(exception=True).error("Failed to load skill {}", name)
            continue
    return out
