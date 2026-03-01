from __future__ import annotations

import json
from typing import Any, Literal

import httpx
from loguru import logger

from ..config import settings
from ..core.http_client import get_client
from ..core.types import ChatMessage, ModelInfo, ToolCall
from .base import LLMProvider, LLMResponse


class OpenAICompatProvider(LLMProvider):
    def __init__(self):
        self._base_url = settings.OPENAI_BASE_URL.rstrip("/")
        self._api_key = settings.OPENAI_API_KEY.strip()
        self._model = settings.OPENAI_MODEL.strip()

    @property
    def model_info(self) -> ModelInfo:
        return ModelInfo(provider="openai_compat", model=self._model)

    @staticmethod
    def provider_name() -> Literal["openai_compat"]:
        return "openai_compat"

    def _endpoint(self) -> str:
        if self._base_url.endswith("/v1"):
            return f"{self._base_url}/chat/completions"
        return f"{self._base_url}/v1/chat/completions"

    def _to_openai_messages(self, messages: list[ChatMessage]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for m in messages:
            role = m.get("role")
            if role == "tool":
                out.append(
                    {
                        "role": "tool",
                        "tool_call_id": m.get("tool_call_id"),
                        "content": m.get("content", ""),
                    }
                )
                continue
            if role == "assistant" and isinstance(m.get("tool_calls"), list) and m.get("tool_calls"):
                tcs = []
                for tc in m.get("tool_calls") or []:
                    if not isinstance(tc, dict):
                        continue
                    cid = tc.get("id")
                    name = tc.get("name")
                    args = tc.get("arguments")
                    if not isinstance(cid, str) or not isinstance(name, str):
                        continue
                    args_s = json.dumps(args or {}, ensure_ascii=False)
                    tcs.append({"id": cid, "type": "function", "function": {"name": name, "arguments": args_s}})
                if tcs:
                    out.append({"role": "assistant", "content": m.get("content", "") or "", "tool_calls": tcs})
                    continue
            out.append({"role": role, "content": m.get("content", "")})
        return out

    async def chat(self, messages: list[ChatMessage], tools: list[dict[str, Any]]) -> LLMResponse:
        if not self._api_key:
            raise RuntimeError("OPENAI_API_KEY is required for openai_compat")
        body: dict[str, Any] = {
            "model": self._model,
            "messages": self._to_openai_messages(messages),
        }
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"
        headers = {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}
        client = get_client()
        try:
            r = await client.post(self._endpoint(), headers=headers, json=body, timeout=60.0)
        except httpx.HTTPError as e:
            raise RuntimeError("openai_compat request failed") from e
        if r.status_code >= 400:
            code = None
            msg = None
            try:
                j = r.json()
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
            if msg:
                raise RuntimeError(f"openai_compat error: {r.status_code}: {msg}")
            if code:
                raise RuntimeError(f"openai_compat error: {r.status_code}: {code}")
            raise RuntimeError(f"openai_compat error: {r.status_code}")
        data = r.json()

        msg = None
        try:
            msg = data["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as e:
            logger.debug("openai_compat_invalid_schema: {}", e)
            msg = None
        content = msg.get("content") if isinstance(msg, dict) else ""
        tool_calls: list[ToolCall] = []
        raw_calls = msg.get("tool_calls") if isinstance(msg, dict) else None
        if isinstance(raw_calls, list):
            for rc in raw_calls:
                if not isinstance(rc, dict):
                    continue
                call_id = rc.get("id")
                fn = rc.get("function")
                if not isinstance(call_id, str) or not isinstance(fn, dict):
                    continue
                name = fn.get("name")
                args_v = fn.get("arguments")
                if not isinstance(name, str):
                    continue
                try:
                    if isinstance(args_v, dict):
                        args = args_v
                    elif isinstance(args_v, str):
                        args = json.loads(args_v) if args_v.strip() else {}
                    else:
                        args = {}
                except json.JSONDecodeError:
                    args = {"_raw": args_v}
                tool_calls.append({"id": call_id, "name": name, "arguments": args})
        if not tool_calls and isinstance(msg, dict):
            fc = msg.get("function_call")
            if isinstance(fc, dict):
                name = fc.get("name")
                args_v = fc.get("arguments")
                if isinstance(name, str):
                    try:
                        if isinstance(args_v, dict):
                            args = args_v
                        elif isinstance(args_v, str):
                            args = json.loads(args_v) if args_v.strip() else {}
                        else:
                            args = {}
                    except json.JSONDecodeError:
                        args = {"_raw": args_v}
                    tool_calls.append({"id": "function_call", "name": name, "arguments": args})
        return LLMResponse(content=content if isinstance(content, str) else "", tool_calls=tool_calls, raw=data)
