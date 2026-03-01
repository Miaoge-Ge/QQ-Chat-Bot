from __future__ import annotations

import asyncio
import base64
import binascii
import mimetypes
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, unquote

import httpx
from loguru import logger
from openai import AsyncOpenAI

from ...config import settings
from ...core.http_client import get_client
from ...tools.base import Tool, ToolContext


def _extract_api_error(exc: Exception) -> tuple[int | None, str | None, str | None]:
    status = getattr(exc, "status_code", None)
    if isinstance(status, bool):
        status = None
    if status is not None:
        try:
            status = int(status)
        except (TypeError, ValueError):
            status = None

    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        err = body.get("error")
        if isinstance(err, dict):
            code = err.get("code")
            msg = err.get("message")
            t = err.get("type")
            return status, str(code) if isinstance(code, str) and code else (str(t) if isinstance(t, str) and t else None), str(msg) if isinstance(msg, str) and msg else None

    resp = getattr(exc, "response", None)
    if resp is not None:
        try:
            status2 = getattr(resp, "status_code", None)
            if status is None and status2 is not None:
                status = int(status2)
        except (TypeError, ValueError):
            pass
        try:
            j = resp.json()
        except Exception:
            j = None
        if isinstance(j, dict):
            err = j.get("error")
            if isinstance(err, dict):
                code = err.get("code")
                msg = err.get("message")
                t = err.get("type")
                return status, str(code) if isinstance(code, str) and code else (str(t) if isinstance(t, str) and t else None), str(msg) if isinstance(msg, str) and msg else None

    return status, None, None


def _friendly_generate_error(status: int | None, code: str | None, msg: str | None) -> dict[str, Any]:
    c = (code or "").strip()
    m = (msg or "").strip()
    if c == "OutputImageSensitiveContentDetected":
        return {
            "error": "policy_violation",
            "message": "生成失败：图片可能触发敏感内容限制。请把描述改得更保守（减少裸露/擦边/暴力等细节），或换一个更健康的主题。",
        }
    if status == 401:
        return {"error": "unauthorized", "message": "生成失败：鉴权失败（API Key 无效或无权限）。"}
    if status == 403:
        return {"error": "forbidden", "message": "生成失败：无权限调用该模型或接口。"}
    if status == 429:
        return {"error": "rate_limited", "message": "生成失败：请求过于频繁或额度不足，请稍后重试。"}
    if status == 400:
        return {"error": "bad_request", "message": "生成失败：请求参数不合法或触发内容限制，请调整提示词后重试。"}
    if status is not None and status >= 500:
        return {"error": "api_error", "message": "生成失败：服务端错误，请稍后重试。"}
    if m:
        short = m.split("Request id:", 1)[0].strip()
        if short:
            return {"error": "api_error", "message": f"生成失败：{short}"}
    return {"error": "api_error", "message": "生成失败：请求未成功，请稍后重试或更换提示词。"}


def _openai_base_url() -> str:
    base = settings.IMAGE_GENERATE_BASE_URL or settings.OPENAI_BASE_URL
    return (base or "").rstrip("/")


def _openai_api_key() -> str:
    return settings.IMAGE_GENERATE_API_KEY or settings.OPENAI_API_KEY


def _openai_image_model() -> str:
    return settings.IMAGE_GENERATE_MODEL_NAME or settings.OPENAI_IMAGE_MODEL or "dall-e-3"


def _get_storage_dir() -> Path:
    root = Path(__file__).resolve().parents[3]
    p = root / "data" / "image_generate"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _save_image(content: bytes, content_type: str | None, suggested_name: str | None) -> str:
    out_dir = _get_storage_dir()
    ext = ""
    if isinstance(content_type, str) and content_type.strip():
        ext = mimetypes.guess_extension(content_type.split(";", 1)[0].strip()) or ""
    name = (suggested_name or "").strip() if isinstance(suggested_name, str) else ""
    if not name:
        name = uuid.uuid4().hex
    if "." not in name:
        name += ext or ".png"
    p = out_dir / name
    with open(p, "wb") as f:
        f.write(content)
    return str(p)


def _extract_filename_from_url(url: str) -> str:
    try:
        u = urlparse(url)
        return unquote((u.path or "").split("/")[-1])
    except ValueError:
        return ""


def _clamp_n(v: object) -> int:
    try:
        n = int(v) if v is not None else 1
    except (TypeError, ValueError):
        n = 1
    return max(1, min(4, n))


def _parse_size_wh(size: str) -> tuple[int, int] | None:
    s = (size or "").strip().lower().replace("×", "x").replace("*", "x")
    if "x" not in s:
        return None
    left, right = s.split("x", 1)
    try:
        w = int(left.strip())
        h = int(right.strip())
    except ValueError:
        return None
    if w <= 0 or h <= 0:
        return None
    return (w, h)


async def tool_handler(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    _ = ctx
    api_key = _openai_api_key()
    if not api_key:
        return {"error": "missing_api_key", "message": "请配置 IMAGE_GENERATE_API_KEY 或 OPENAI_API_KEY"}

    prompt = str(args.get("prompt") or "").strip()
    if not prompt:
        return {"error": "empty_prompt"}

    base_url = _openai_base_url()
    model = str(args.get("model") or "").strip() or _openai_image_model()
    try:
        if not base_url:
            return {"error": "missing_base_url", "message": "未配置可用的 IMAGE_GENERATE_BASE_URL/OPENAI_BASE_URL"}

        size0 = str(args.get("size") or "").strip() or "2048x2048"
        if size0.upper() == "2K":
            size0 = "2048x2048"

        wh = _parse_size_wh(size0)
        if wh is not None and model.startswith("doubao-seedream"):
            w, h = wh
            if (w * h) < 3686400:
                size0 = "2048x2048"

        rf = str(args.get("response_format") or "").strip() or "url"
        n0 = _clamp_n(args.get("n"))
        watermark = args.get("watermark")
        if not isinstance(watermark, bool):
            watermark = False

        client = AsyncOpenAI(base_url=base_url, api_key=api_key)
        extra_body: dict | None = {"watermark": bool(watermark)}
        resp = await client.images.generate(
            model=model,
            prompt=prompt,
            size=size0,
            n=n0,
            response_format=rf,
            extra_body=extra_body,
        )

        items = getattr(resp, "data", None) or []
        if not isinstance(items, list) or not items:
            return {"error": "no_image", "message": "API未返回图片数据"}

        http = get_client()
        file_paths: list[str] = []
        for item in items:
            if rf == "b64_json":
                b64 = getattr(item, "b64_json", None)
                if not isinstance(b64, str) or not b64:
                    continue
                try:
                    img = base64.b64decode(b64)
                except binascii.Error:
                    continue
                p = _save_image(img, "image/png", f"{uuid.uuid4().hex}.png")
                file_paths.append(p)
                continue

            u = getattr(item, "url", None)
            if not isinstance(u, str) or not u.strip():
                b64 = getattr(item, "b64_json", None)
                if isinstance(b64, str) and b64:
                    try:
                        img = base64.b64decode(b64)
                    except binascii.Error:
                        continue
                    p = _save_image(img, "image/png", f"{uuid.uuid4().hex}.png")
                    file_paths.append(p)
                continue

            img_url = u.strip()
            try:
                r = await http.get(img_url, timeout=60.0, follow_redirects=True)
            except httpx.HTTPError:
                continue
            if r.status_code >= 400:
                continue
            ct = r.headers.get("Content-Type", "")
            fn = _extract_filename_from_url(img_url)
            p = _save_image(r.content, ct, fn or None)
            file_paths.append(p)

        if not file_paths:
            return {"error": "no_image", "message": "生成失败：未获得可用图片输出"}

        out: dict = {"file_path": file_paths[0], "model": model}
        if len(file_paths) > 1:
            out["file_paths"] = file_paths
        return out
    except asyncio.CancelledError:
        raise
    except Exception as e:
        status, code, msg = _extract_api_error(e)
        if status is not None or code or msg:
            logger.warning("image_generate_api_error: model={} base_url={}", model, base_url)
            return _friendly_generate_error(status, code, msg)
        logger.opt(exception=True).error("image_generate_failed: model={} base_url={}", model, base_url)
        msg = str(e)
        if len(msg) > 2000:
            msg = msg[:2000].rstrip() + "…"
        return {"error": "internal_error", "message": msg}



TOOL = Tool(
    name="image_generate",
    description="图像生成：调用 images/generations 接口生成图片并落盘，返回本地文件路径",
    parameters={
        "type": "object",
        "properties": {
            "prompt": {"type": "string", "description": "生成提示词"},
            "model": {"type": "string", "description": "可选模型名称，默认使用 IMAGE_GENERATE_MODEL_NAME"},
            "size": {"type": "string", "description": "可选尺寸，例如 1024x1024 或 2048x2048"},
            "n": {"type": "integer", "description": "生成张数，默认 1，最大 4"},
            "response_format": {"type": "string", "description": "返回格式：url 或 b64_json，默认 url"},
            "watermark": {"type": "boolean", "description": "可选：是否加水印（部分服务支持）"},
        },
        "required": ["prompt"],
        "additionalProperties": False,
    },
    handler=tool_handler,
)
