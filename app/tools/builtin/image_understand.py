from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx
from loguru import logger

from ...config import settings
from ...core.http_client import get_client
from ...core.image import download_image_as_base64
from ...tools.base import Tool, ToolContext


_STYLE = "请用精简中文回答，80 字以内。"

def _extract_error_message(resp: httpx.Response) -> tuple[str | None, str | None]:
    code = None
    msg = None
    try:
        j = resp.json()
    except Exception:
        j = None
    if isinstance(j, dict):
        err = j.get("error")
        if isinstance(err, dict):
            c = err.get("code") or err.get("type")
            m = err.get("message")
            if isinstance(c, str) and c.strip():
                code = c.strip()
            if isinstance(m, str) and m.strip():
                msg = m.strip().split("Request id:", 1)[0].strip()
    return code, msg


def _vl_base_url() -> str:
    base = settings.VL_BASE_URL or settings.OPENAI_BASE_URL
    return base.rstrip("/")


def _vl_api_key() -> str:
    return settings.VL_API_KEY or settings.OPENAI_API_KEY


def _vl_model() -> str:
    return settings.VL_MODEL_NAME or settings.OPENAI_MODEL or "gpt-4o-mini"

def _vl_chat_completions_url(base_url: str) -> str:
    b = (base_url or "").rstrip("/")
    if not b:
        return ""
    if b.endswith("/chat/completions"):
        return b
    if b.endswith("/v1"):
        return f"{b}/chat/completions"
    if b.endswith("/api/v3"):
        return f"{b}/chat/completions"
    return f"{b}/v1/chat/completions"

def _should_fallback_model(resp_json: object) -> bool:
    if not isinstance(resp_json, dict):
        return False
    err = resp_json.get("error")
    if not isinstance(err, dict):
        return False
    msg = err.get("message")
    if not isinstance(msg, str) or not msg.strip():
        return False
    s = msg.lower()
    return "does not support this api" in s or "model" in s and "not valid" in s


async def tool_handler(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    _ = ctx
    api_key = _vl_api_key()
    if not api_key:
        return {"error": "missing_api_key", "message": "请配置 VL_API_KEY 或 OPENAI_API_KEY"}

    image = str(args.get("image") or args.get("image_url") or "").strip()
    question = str(args.get("question") or "").strip()
    if not image:
        return {"error": "missing_image"}
    if not question:
        question = f"请描述这张图片。{_STYLE}"
    else:
        question = f"{question}\n\n{_STYLE}"

    data_url = await download_image_as_base64(image, 60.0)
    if not data_url:
        if image.startswith(("http://", "https://")):
            try:
                import urllib.parse

                host = (urllib.parse.urlparse(image).hostname or "").lower()
            except ValueError:
                host = ""
            try:
                client = get_client()
                headers = {
                    "User-Agent": "Mozilla/5.0",
                    "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
                }
                if host.endswith("qq.com") or host.endswith("qq.com.cn"):
                    headers["Referer"] = "https://nt.qq.com/"
                resp = await client.get(image, timeout=30.0, follow_redirects=True, headers=headers)
                return {
                    "error": "download_failed",
                    "message": "图片下载失败：链接可能不可直连或已失效。",
                    "status": int(resp.status_code),
                    "content_type": str(resp.headers.get("Content-Type", "")),
                    "host": host,
                }
            except httpx.HTTPError as e:
                logger.debug("image_download_probe_failed: {}", e)
                return {"error": "download_failed", "message": "图片下载失败：链接可能不可直连或已失效。"}
        return {"error": "download_failed", "message": "图片下载失败：本地图片路径不可读取，或图片链接不可直连。"}

    base_url = _vl_base_url()
    url = _vl_chat_completions_url(base_url)
    if not url:
        return {"error": "missing_base_url", "message": "未配置可用的 VL_BASE_URL/OPENAI_BASE_URL"}
        
    model = _vl_model()
    
    body = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": question},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }
        ],
        "max_tokens": 1000
    }
    
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    
    try:
        client = get_client()
        resp = await client.post(url, json=body, headers=headers, timeout=90.0)
        if resp.status_code >= 400:
            code, msg = _extract_error_message(resp)
            if resp.status_code == 400 and _should_fallback_model(resp.json() if resp.headers.get("content-type", "").startswith("application/json") else None):
                fallback_model = "doubao-1.5-vision-pro-32k-250115"
                if body.get("model") != fallback_model:
                    body2 = dict(body)
                    body2["model"] = fallback_model
                    resp2 = await client.post(url, json=body2, headers=headers, timeout=90.0)
                    if resp2.status_code >= 400:
                        code2, msg2 = _extract_error_message(resp2)
                        out: dict[str, Any] = {"error": "api_error", "status": int(resp2.status_code)}
                        if code2:
                            out["code"] = code2
                        if msg2:
                            out["message"] = msg2
                        return out
                    data2 = resp2.json()
                    choices2 = data2.get("choices")
                    if not isinstance(choices2, list) or not choices2:
                        return {"error": "no_content", "message": "模型未返回任何内容"}
                    content2 = choices2[0]["message"]["content"]
                    return {"text": content2, "model": fallback_model}
            out: dict[str, Any] = {"error": "api_error", "status": int(resp.status_code)}
            if code:
                out["code"] = code
            if msg:
                out["message"] = msg
            return out
        
        data = resp.json()
        
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            return {"error": "no_content", "message": "模型未返回任何内容"}
             
        content = choices[0]["message"]["content"]
        return {"text": content, "model": model}
    except asyncio.CancelledError:
        raise
    except httpx.HTTPError as e:
        return {"error": "http_error", "message": str(e)}
    except (KeyError, IndexError, TypeError, ValueError) as e:
        logger.debug("image_understand_parse_failed: {}", e)
        return {"error": "parse_error", "message": str(e)}
    except Exception as e:
        logger.opt(exception=True).error("image_understand_internal_error")
        return {"error": "internal_error", "message": str(e)}


TOOL = Tool(
    name="image_understand",
    description="图像理解：输入图片URL和问题，调用多模态模型分析图片内容。",
    parameters={
        "type": "object",
        "properties": {
            "image": {"type": "string", "description": "图片URL或路径"},
            "question": {"type": "string", "description": "关于图片的问题，默认为描述图片"},
        },
        "required": ["image"],
        "additionalProperties": False,
    },
    handler=tool_handler,
)
