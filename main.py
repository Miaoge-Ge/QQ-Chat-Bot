from __future__ import annotations

import asyncio
import hashlib
import os
import sys

from loguru import logger

from app.config import settings
from app.core.http_client import close_client
from app.logging import setup_logging
from app.memory.history import HistoryStore
from app.onebot.client import OneBotClient
from app.providers.factory import build_provider
from app.runtime.orchestrator import Orchestrator
from app.skills.loader import load_skills
from app.tools import build_tool_registry


async def main() -> None:
    setup_logging()
    logger.info("new_bot 启动中")
    if not settings.OPENAI_API_KEY:
        logger.error("OPENAI_API_KEY is not set. Exiting.")
        sys.exit(1)
    try:
        p = os.path.abspath(settings.SYSTEM_PROMPT_PATH)
        if os.path.exists(p) and os.path.isfile(p):
            with open(p, "rb") as f:
                b = f.read()
            sha = hashlib.sha256(b).hexdigest()[:12]
            logger.info("system_prompt_loaded: path={} bytes={} sha256={}", p, len(b), sha)
        else:
            logger.warning("system_prompt_missing: path={}", p)
    except Exception as e:
        logger.warning("system_prompt_probe_failed: {}", e)
    try:
        provider = build_provider()
        tools = build_tool_registry()
        history = HistoryStore()
        skills = load_skills()
        orch = Orchestrator(provider=provider, tools=tools, history=history, skills=skills)
        bot = OneBotClient(orch)
        await bot.run_forever()
    finally:
        await close_client()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("已退出")
