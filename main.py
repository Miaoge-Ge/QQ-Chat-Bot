from __future__ import annotations

import asyncio
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

