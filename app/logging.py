from __future__ import annotations

import sys

from loguru import logger


def setup_logging() -> None:
    logger.remove()
    logger.add(
        sys.stderr,
        level="INFO",
        format="<dim>{time:YYYY-MM-DD HH:mm:ss}</dim> | <level>{level}</level> | {message}",
        colorize=True,
        backtrace=False,
        diagnose=False,
    )
