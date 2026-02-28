from __future__ import annotations

import os
import json
from urllib.parse import urlparse
from typing import Literal

from dotenv import load_dotenv
from pydantic import BaseModel
from loguru import logger

from .constants import NAPCAT_ONEBOT11_JSON_CANDIDATES

load_dotenv()


class Settings(BaseModel):
    ONEBOT_MODE: Literal["ws", "reverse_ws"] = "ws"
    ONEBOT_WS_URL: str = "ws://127.0.0.1:3001"
    ONEBOT_LISTEN_HOST: str = "127.0.0.1"
    ONEBOT_LISTEN_PORT: int = 3002
    ONEBOT_LISTEN_PATH: str = "/onebot"
    ONEBOT_ACCESS_TOKEN: str = ""

    OPENAI_BASE_URL: str = "http://127.0.0.1:8000/v1"
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"
    OPENAI_IMAGE_MODEL: str = ""

    # Image Understanding (VL)
    VL_BASE_URL: str = ""
    VL_API_KEY: str = ""
    VL_MODEL_NAME: str = "gpt-4o-mini"

    # Image Recognition (OCR/Vision)
    OCR_BASE_URL: str = ""
    OCR_API_KEY: str = ""
    OCR_MODEL_NAME: str = "gpt-4o-mini"

    # Image Generation
    IMAGE_GENERATE_BASE_URL: str = ""
    IMAGE_GENERATE_API_KEY: str = ""
    IMAGE_GENERATE_MODEL_NAME: str = "dall-e-3"

    GROUP_REPLY_MODE: Literal["mention", "always"] = "mention"
    REPLY_AT_SENDER: bool = True

    CONTEXT_TURNS_PRIVATE: int = 12
    CONTEXT_TURNS_GROUP: int = 8
    CONTEXT_MAX_CHARS: int = 1200
    HISTORY_PATH: str = "./data/history.jsonl"

    SKILLS_DIR: str = "./skills"
    ENABLED_SKILLS: str = "default"
    SYSTEM_PROMPT_PATH: str = "./prompts/system.md"

    WEB_SEARCH_ENABLED: bool = True

    ADMIN_QQ_IDS: str = ""


def admin_qq_id_set() -> set[str]:
    s = str(settings.ADMIN_QQ_IDS or "").strip()
    if not s:
        return set()
    out: set[str] = set()
    for part in s.replace("，", ",").split(","):
        v = part.strip()
        if v:
            out.add(v)
    return out


def _getenv(name: str) -> str | None:
    v = os.getenv(name)
    if v is None:
        return None
    s = str(v).strip()
    return s if s else None


settings = Settings(
    ONEBOT_MODE=_getenv("ONEBOT_MODE") or Settings().ONEBOT_MODE,
    ONEBOT_WS_URL=_getenv("ONEBOT_WS_URL") or Settings().ONEBOT_WS_URL,
    ONEBOT_LISTEN_HOST=_getenv("ONEBOT_LISTEN_HOST") or Settings().ONEBOT_LISTEN_HOST,
    ONEBOT_LISTEN_PORT=int(_getenv("ONEBOT_LISTEN_PORT") or Settings().ONEBOT_LISTEN_PORT),
    ONEBOT_LISTEN_PATH=_getenv("ONEBOT_LISTEN_PATH") or Settings().ONEBOT_LISTEN_PATH,
    ONEBOT_ACCESS_TOKEN=_getenv("ONEBOT_ACCESS_TOKEN") or "",
    OPENAI_BASE_URL=_getenv("OPENAI_BASE_URL") or Settings().OPENAI_BASE_URL,
    OPENAI_API_KEY=_getenv("OPENAI_API_KEY") or "",
    OPENAI_MODEL=_getenv("OPENAI_MODEL") or Settings().OPENAI_MODEL,
    OPENAI_IMAGE_MODEL=_getenv("OPENAI_IMAGE_MODEL") or "",
    VL_BASE_URL=_getenv("VL_BASE_URL") or _getenv("IMAGE_UNDERSTAND_BASE_URL") or Settings().VL_BASE_URL,
    VL_API_KEY=_getenv("VL_API_KEY") or _getenv("IMAGE_UNDERSTAND_API_KEY") or "",
    VL_MODEL_NAME=_getenv("VL_MODEL_NAME") or _getenv("IMAGE_UNDERSTAND_MODEL_NAME") or Settings().VL_MODEL_NAME,
    OCR_BASE_URL=_getenv("OCR_BASE_URL") or Settings().OCR_BASE_URL,
    OCR_API_KEY=_getenv("OCR_API_KEY") or "",
    OCR_MODEL_NAME=_getenv("OCR_MODEL_NAME") or Settings().OCR_MODEL_NAME,
    IMAGE_GENERATE_BASE_URL=_getenv("IMAGE_GENERATE_BASE_URL") or Settings().IMAGE_GENERATE_BASE_URL,
    IMAGE_GENERATE_API_KEY=_getenv("IMAGE_GENERATE_API_KEY") or "",
    IMAGE_GENERATE_MODEL_NAME=_getenv("IMAGE_GENERATE_MODEL_NAME") or Settings().IMAGE_GENERATE_MODEL_NAME,
    GROUP_REPLY_MODE=_getenv("GROUP_REPLY_MODE") or Settings().GROUP_REPLY_MODE,
    REPLY_AT_SENDER=(_getenv("REPLY_AT_SENDER") or "true").lower() in ("1", "true", "yes", "y", "on"),
    CONTEXT_TURNS_PRIVATE=int(_getenv("CONTEXT_TURNS_PRIVATE") or Settings().CONTEXT_TURNS_PRIVATE),
    CONTEXT_TURNS_GROUP=int(_getenv("CONTEXT_TURNS_GROUP") or Settings().CONTEXT_TURNS_GROUP),
    CONTEXT_MAX_CHARS=int(_getenv("CONTEXT_MAX_CHARS") or Settings().CONTEXT_MAX_CHARS),
    HISTORY_PATH=_getenv("HISTORY_PATH") or Settings().HISTORY_PATH,
    SKILLS_DIR=_getenv("SKILLS_DIR") or Settings().SKILLS_DIR,
    ENABLED_SKILLS=_getenv("ENABLED_SKILLS") or Settings().ENABLED_SKILLS,
    SYSTEM_PROMPT_PATH=_getenv("SYSTEM_PROMPT_PATH") or Settings().SYSTEM_PROMPT_PATH,
    WEB_SEARCH_ENABLED=(_getenv("WEB_SEARCH_ENABLED") or "true").lower() in ("1", "true", "yes", "y", "on"),
    ADMIN_QQ_IDS=_getenv("ADMIN_QQ_IDS") or "",
)


def _parse_ws_host_port(ws_url: str) -> tuple[str, int] | None:
    try:
        u = urlparse(ws_url)
        host = u.hostname or ""
        if not host:
            return None
        if u.port is not None:
            return (host, int(u.port))
        if (u.scheme or "").lower() == "wss":
            return (host, 443)
        return (host, 80)
    except (TypeError, ValueError):
        return None


def _try_load_napcat_ws_token(ws_url: str) -> str | None:
    hp = _parse_ws_host_port(ws_url)
    if hp is None:
        return None
    host, port = hp
    for p in NAPCAT_ONEBOT11_JSON_CANDIDATES:
        try:
            if not os.path.exists(p):
                continue
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            net = data.get("network") if isinstance(data, dict) else None
            ws_servers = net.get("websocketServers") if isinstance(net, dict) else None
            if not isinstance(ws_servers, list):
                continue
            for s in ws_servers:
                if not isinstance(s, dict):
                    continue
                if not s.get("enable", False):
                    continue
                if str(s.get("host", "")) != host:
                    continue
                if int(s.get("port", -1)) != port:
                    continue
                tok = s.get("token")
                if isinstance(tok, str) and tok.strip():
                    return tok.strip()
        except (OSError, json.JSONDecodeError, UnicodeDecodeError, TypeError, ValueError) as e:
            logger.debug("napcat_onebot11_load_failed: {}: {}", p, e)
            continue
    return None


if settings.ONEBOT_MODE == "ws" and not settings.ONEBOT_ACCESS_TOKEN:
    t = _try_load_napcat_ws_token(settings.ONEBOT_WS_URL)
    if t:
        settings.ONEBOT_ACCESS_TOKEN = t
