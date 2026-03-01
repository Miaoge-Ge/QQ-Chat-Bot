from __future__ import annotations

import asyncio
import json
import os

from loguru import logger

from ..config import settings
from ..core.types import ChatMessage
from ..memory.history import HistoryStore
from ..providers.base import LLMProvider
from ..skills.types import Skill
from ..tools.base import ToolContext
from ..tools.registry import ToolRegistry


class Orchestrator:
    def __init__(self, provider: LLMProvider, tools: ToolRegistry, history: HistoryStore, skills: list[Skill]):
        self._provider = provider
        self._tools = tools
        self._history = history
        self._skills = skills

    def _file_system_prompt(self) -> str:
        p = os.path.abspath(settings.SYSTEM_PROMPT_PATH)
        try:
            if not os.path.exists(p):
                return ""
            with open(p, "r", encoding="utf-8") as f:
                return f.read().strip()
        except (OSError, UnicodeDecodeError):
            return ""

    def _system_prompt(self) -> str:
        parts: list[str] = []
        file_prompt = self._file_system_prompt()
        if file_prompt:
            parts.append(file_prompt)
        for s in self._skills:
            if s.system_prompt and s.system_prompt.strip():
                parts.append(s.system_prompt.strip())
        return "\n\n".join(parts).strip()

    def _allowed_tools(self) -> set[str] | None:
        allowed: set[str] = set()
        has_limit = False
        for s in self._skills:
            if s.enabled_tools is None:
                continue
            has_limit = True
            for t in s.enabled_tools:
                if isinstance(t, str) and t.strip():
                    allowed.add(t.strip())
        return allowed if has_limit else None

    def _safe_tool_content(self, obj: object) -> str:
        try:
            return json.dumps(obj, ensure_ascii=False)
        except (TypeError, ValueError, OverflowError):
            s = str(obj)
            if len(s) > 2000:
                s = s[:2000].rstrip() + "…"
            return json.dumps({"error": "non_json_result", "value": s}, ensure_ascii=False)

    def _extract_user_content(self, text: str) -> str:
        s = (text or "").strip()
        if not s:
            return ""
        if s.startswith("【") and "】说：" in s:
            return s.split("】说：", 1)[1].strip()
        if "：" in s:
            left, right = s.split("：", 1)
            if 0 < len(left.strip()) <= 12 and right.strip():
                return right.strip()
        return s

    def _is_reset_command(self, text: str) -> bool:
        t = self._extract_user_content(text)
        if not t:
            return False
        low = t.lower()
        if low in ("/reset", "reset", "/clear", "clear", "/new", "new"):
            return True
        return t in ("清除上下文", "清空上下文", "重置上下文", "重置对话", "清除记忆", "清空记忆")

    async def handle_user_text(self, session_id: str, user_text: str) -> tuple[str, list[str]]:
        text, used, _attachments = await self.handle_user_event(session_id, user_text, [], None, None)
        return text, used

    async def handle_user_event(
        self,
        session_id: str,
        user_text: str,
        image_refs: list[str],
        caller_user_id: str | None,
        caller_message_type: str | None,
    ) -> tuple[str, list[str], list[dict[str, str]]]:
        if len(user_text) > 20000:
            return "输入过长，请精简后再试。", [], []

        if self._is_reset_command(user_text):
            self._history.append(session_id, "meta", "__clear__")
            msg = "好的，上下文已清除。现在是一个全新的对话。"
            self._history.append(session_id, "assistant", msg)
            return msg, [], []

        sys_prompt = self._system_prompt()
        messages: list[ChatMessage] = []
        if sys_prompt:
            messages.append({"role": "system", "content": sys_prompt})

        messages.extend(self._history.get_recent(session_id))

        # 将图片引用作为文本上下文提供给 LLM
        if image_refs:
            # 去重
            unique_refs = []
            for ref in image_refs:
                if ref not in unique_refs:
                    unique_refs.append(ref)
            
            img_context = "\n".join(f"[图片{i+1}: {ref}]" for i, ref in enumerate(unique_refs))
            user_text = f"{user_text.strip()}\n\n【附件信息】\n用户发送了以下图片：\n{img_context}\n\n如需分析图片内容，请使用 image_understand 工具。"

        messages.append({"role": "user", "content": user_text})

        allowed = self._allowed_tools()
        tool_list = []
        for t in self._tools.list():
            if allowed is not None and t.name not in allowed:
                continue
            tool_list.append(t.openai_schema()["function"])

        tools_payload = [{"type": "function", "function": fn} for fn in tool_list]
        ctx = ToolContext(
            session_id=session_id,
            model=self._provider.model_info,
            caller_user_id=caller_user_id,
            caller_message_type=caller_message_type,
        )

        final_text = ""
        used_tools: list[str] = []
        attachments: list[dict[str, str]] = []
        weather_reply: str | None = None
        for _ in range(4):
            try:
                resp = await self._provider.chat(messages, tools_payload)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.opt(exception=True).error("llm_call_failed")
                final_text = "服务暂不可用，请稍后再试。"
                break
            final_text = resp.content or ""
            messages.append({"role": "assistant", "content": resp.content or "", "tool_calls": resp.tool_calls})
            if not resp.tool_calls:
                break
            for c in resp.tool_calls:
                name = c.get("name")
                if isinstance(name, str) and name and name not in used_tools:
                    used_tools.append(name)

            results = await self._tools.run(resp.tool_calls, ctx)
            for r in results:
                if r["name"] in ("image_generate", "image_repo_random") and isinstance(r.get("result"), dict):
                    fp = r["result"].get("file_path")
                    if isinstance(fp, str) and fp.strip():
                        attachments.append({"type": "image", "file_path": fp.strip()})
                if r["name"] == "weather_query" and isinstance(r.get("result"), dict) and weather_reply is None:
                    rt = r["result"].get("reply")
                    if isinstance(rt, str) and rt.strip():
                        weather_reply = rt.strip()

                tool_call_id = r.get("tool_call_id") if isinstance(r, dict) else None
                result_content = r.get("result") if isinstance(r, dict) else r
                
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call_id,
                        "content": self._safe_tool_content(result_content),
                    }
                )
            if weather_reply:
                final_text = weather_reply
                break

        if weather_reply:
            final_text = weather_reply

        if user_text.strip():
            # 保存到历史记录时，去掉可能添加的【发送者昵称】前缀，保持历史记录的纯净性？
            # 不，实际上历史记录里保留【发送者昵称】有助于模型理解上下文。
            # 但是，如果用户直接查看历史记录，可能会觉得奇怪。
            # 这里我们直接保存 user_text（包含了发送者信息），这是正确的，因为这是 LLM 看到的实际输入。
            # 如果下一次请求到来，get_recent 会返回包含【发送者昵称】的内容，这样模型就能知道是谁说的。
            self._history.append(session_id, "user", user_text)
        if final_text.strip():
            self._history.append(session_id, "assistant", final_text)
        return final_text.strip(), used_tools, attachments
