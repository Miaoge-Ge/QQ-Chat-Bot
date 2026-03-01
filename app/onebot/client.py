from __future__ import annotations

import asyncio
import json
import os
import shutil
import time
import uuid
from typing import Any

import websockets
from loguru import logger
from websockets.exceptions import ConnectionClosed, ConnectionClosedError

from ..config import admin_qq_id_set, settings
from ..constants import MAX_INGEST_IMAGE_BYTES
from ..runtime.orchestrator import Orchestrator
from ..runtime.sleep_state import SleepStore
from .utils import extract_images, extract_reply_id, extract_text, is_mentioned


class OneBotClient:
    def __init__(self, orchestrator: Orchestrator):
        self._orchestrator = orchestrator
        self._ws: websockets.WebSocketClientProtocol | None = None
        self._connected = asyncio.Event()
        self._pending: dict[str, asyncio.Future] = {}
        self._ever_connected = False
        self._last_log_ts: dict[str, float] = {}
        self._group_name_cache: dict[int, tuple[str, float]] = {}

    def _throttled_warn(self, key: str, message: str, interval_s: float = 10.0) -> None:
        now = time.monotonic()
        last = self._last_log_ts.get(key, 0.0)
        if now - last < interval_s:
            return
        self._last_log_ts[key] = now
        logger.warning(message)

    def _out_image_file(self, v: str) -> str | None:
        s = str(v or "").strip()
        if not s:
            return None
        if s.startswith(("http://", "https://")):
            return s
        p = s
        if p.startswith("file://"):
            try:
                import urllib.parse

                u = urllib.parse.urlparse(p)
                p = urllib.parse.unquote(u.path or "")
            except (AttributeError, ValueError) as e:
                logger.debug("parse_file_url_failed: {}: {}", p, e)
                return None
        p = os.path.abspath(p)
        if not os.path.exists(p) or not os.path.isfile(p):
            return None
        try:
            import urllib.parse

            return "file://" + urllib.parse.quote(p, safe="/")
        except Exception as e:
            logger.debug("quote_local_path_failed: {}: {}", p, e)
            return "file://" + p

    def _ingest_local_image(self, path_or_file_url: str) -> str | None:
        s = str(path_or_file_url or "").strip()
        if not s:
            return None
        p = s
        if p.startswith("file://"):
            try:
                import urllib.parse

                u = urllib.parse.urlparse(p)
                p = urllib.parse.unquote(u.path or "")
            except (AttributeError, ValueError) as e:
                logger.debug("parse_file_url_failed: {}: {}", p, e)
                return None
        p = os.path.abspath(p)
        if not os.path.exists(p) or not os.path.isfile(p):
            return None
        try:
            if os.path.getsize(p) > MAX_INGEST_IMAGE_BYTES:
                return None
        except OSError:
            return None
        ext = os.path.splitext(p)[1].lower()
        if ext not in (".png", ".jpg", ".jpeg", ".webp", ".gif"):
            ext = ".bin"
        out_dir = os.path.abspath(os.path.join(os.getcwd(), "data", "incoming_images"))
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, f"{uuid.uuid4().hex}{ext}")
        try:
            shutil.copyfile(p, out_path)
            return out_path
        except OSError as e:
            logger.debug("copy_local_image_failed: {} -> {}: {}", p, out_path, e)
            return None

    async def run_forever(self) -> None:
        if settings.ONEBOT_MODE == "reverse_ws":
            await self._run_reverse_ws()
        else:
            await self._run_ws_client()

    def _ws_connect(self, headers: dict[str, str]):
        if not headers:
            return websockets.connect(settings.ONEBOT_WS_URL)
        try:
            return websockets.connect(settings.ONEBOT_WS_URL, additional_headers=headers)
        except TypeError as e:
            if "additional_headers" not in str(e):
                raise
            return websockets.connect(settings.ONEBOT_WS_URL, extra_headers=headers)

    async def _run_ws_client(self) -> None:
        headers: dict[str, str] = {}
        token = settings.ONEBOT_ACCESS_TOKEN.strip()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        while True:
            try:
                async with self._ws_connect(headers) as ws:
                    self._ws = ws
                    listen_task = asyncio.create_task(self._listen(ws))
                    ok = await self._handshake()
                    if not ok:
                        listen_task.cancel()
                        self._throttled_warn(
                            "handshake_fail",
                            "OneBot 握手失败（get_status 未返回 ok），请检查 ONEBOT_WS_URL / ONEBOT_ACCESS_TOKEN 是否正确",
                            interval_s=15.0,
                        )
                        await asyncio.sleep(2)
                        continue
                    self._connected.set()
                    if not self._ever_connected:
                        logger.info(f"OneBot 连接正常：{settings.ONEBOT_WS_URL}")
                        self._ever_connected = True
                    started = time.monotonic()
                    try:
                        await listen_task
                    finally:
                        listen_task.cancel()
                    self._connected.clear()
                    self._ws = None
                    alive_s = time.monotonic() - started
                    if alive_s >= 0.2:
                        self._throttled_warn("disconnect", "OneBot 连接已关闭，正在重连", interval_s=15.0)
                    await asyncio.sleep(5)
            except (ConnectionClosed, ConnectionClosedError, OSError, asyncio.TimeoutError) as e:
                self._connected.clear()
                self._ws = None
                self._throttled_warn("connect_fail", f"OneBot 连接失败：{e}（正在重连）", interval_s=15.0)
                await asyncio.sleep(5)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                self._connected.clear()
                self._ws = None
                logger.opt(exception=True).warning("onebot_connect_error")
                self._throttled_warn("connect_error", f"OneBot 连接异常：{e}（正在重连）", interval_s=15.0)
                await asyncio.sleep(5)

    def _get_request_header(self, ws: Any, key: str) -> str:
        headers = getattr(ws, "request_headers", None)
        if headers is not None:
            return str(headers.get(key, ""))
        req = getattr(ws, "request", None)
        req_headers = getattr(req, "headers", None)
        if req_headers is not None:
            return str(req_headers.get(key, ""))
        return ""

    async def _run_reverse_ws(self) -> None:
        async def handler(ws: Any, path: str | None = None):
            ws_path = path or getattr(ws, "path", "")
            if settings.ONEBOT_LISTEN_PATH and ws_path and ws_path != settings.ONEBOT_LISTEN_PATH:
                await ws.close(code=4404, reason="Not Found")
                return
            token = settings.ONEBOT_ACCESS_TOKEN.strip()
            if token:
                auth = self._get_request_header(ws, "Authorization")
                if auth != f"Bearer {token}":
                    await ws.close(code=4401, reason="Unauthorized")
                    return
            if self._ws is not None and self._connected.is_set():
                await ws.close(code=4429, reason="Only one connection allowed")
                return
            self._ws = ws
            listen_task = asyncio.create_task(self._listen(ws))
            ok = await self._handshake()
            if not ok:
                listen_task.cancel()
                await ws.close(code=4400, reason="Handshake failed")
                self._ws = None
                return
            self._connected.set()
            if not self._ever_connected:
                logger.info("OneBot 反向连接正常")
                self._ever_connected = True
            try:
                await listen_task
            finally:
                listen_task.cancel()
                self._connected.clear()
                self._ws = None

        async with websockets.serve(handler, settings.ONEBOT_LISTEN_HOST, settings.ONEBOT_LISTEN_PORT):
            logger.info(
                f"反向 WS 监听: ws://{settings.ONEBOT_LISTEN_HOST}:{settings.ONEBOT_LISTEN_PORT}{settings.ONEBOT_LISTEN_PATH}"
            )
            await asyncio.Future()

    async def _handshake(self) -> bool:
        resp = await self.send_api_call("get_status", {}, timeout_s=4.0)
        if not isinstance(resp, dict):
            return False
        return resp.get("status") == "ok"

    async def send_api_call(self, action: str, params: dict[str, Any], timeout_s: float = 6.0) -> dict[str, Any] | None:
        ws = self._ws
        if ws is None:
            return None
        echo = uuid.uuid4().hex
        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending[echo] = fut
        payload = {"action": action, "params": params, "echo": echo}
        try:
            await ws.send(json.dumps(payload, ensure_ascii=False))
            result = await asyncio.wait_for(fut, timeout=timeout_s)
            return result if isinstance(result, dict) else None
        except asyncio.CancelledError:
            raise
        except (asyncio.TimeoutError, ConnectionClosed, ConnectionClosedError, OSError) as e:
            logger.debug("onebot_send_api_call_failed: {}: {}", action, e)
            if not fut.done():
                fut.cancel()
            return None
        finally:
            self._pending.pop(echo, None)

    async def send_api(self, action: str, params: dict[str, Any]) -> None:
        await self._connected.wait()
        if self._ws is None:
            return
        payload = {"action": action, "params": params, "echo": uuid.uuid4().hex}
        try:
            await self._ws.send(json.dumps(payload, ensure_ascii=False))
        except asyncio.CancelledError:
            raise
        except (ConnectionClosed, ConnectionClosedError, OSError) as e:
            logger.debug("onebot_send_api_failed: {}: {}", action, e)
        except Exception:
            logger.opt(exception=True).error("onebot_send_api_error: {}", action)

    async def send_msg(self, event: dict[str, Any], message: str) -> None:
        message_type = event.get("message_type")
        params: dict[str, Any] = {"message_type": message_type, "message": message}
        if message_type == "group":
            params["group_id"] = event.get("group_id")
        else:
            params["user_id"] = event.get("user_id")
        await self.send_api("send_msg", params)

    async def _get_group_name(self, group_id: int) -> str:
        cached = self._group_name_cache.get(group_id)
        now = time.monotonic()
        if cached is not None and now - cached[1] < 6 * 3600:
            return cached[0]
        resp = await self.send_api_call("get_group_info", {"group_id": group_id}, timeout_s=3.0)
        name = ""
        try:
            data = resp.get("data") if isinstance(resp, dict) else None
            v = data.get("group_name") if isinstance(data, dict) else None
            name = v.strip() if isinstance(v, str) else ""
        except (AttributeError, TypeError):
            name = ""
        if not name:
            name = str(group_id)
        self._group_name_cache[group_id] = (name, now)
        return name

    async def _peer_name(self, event: dict[str, Any]) -> str:
        if event.get("message_type") == "group":
            gid = event.get("group_id")
            try:
                return await self._get_group_name(int(gid))
            except (TypeError, ValueError):
                return str(gid or "group")
        sender = event.get("sender") or {}
        if isinstance(sender, dict):
            nick = sender.get("nickname")
            if isinstance(nick, str) and nick.strip():
                return nick.strip()
        uid = event.get("user_id")
        return str(uid or "private")

    def _sender_name(self, event: dict[str, Any]) -> str:
        sender = event.get("sender") or {}
        if isinstance(sender, dict):
            nick = sender.get("card") or sender.get("nickname")
            if isinstance(nick, str) and nick.strip():
                return nick.strip()
        uid = event.get("user_id")
        return str(uid or "user")

    def _one_line(self, text: str) -> str:
        return " ".join((text or "").split()).strip()

    async def _user_log_label(self, event: dict[str, Any]) -> str:
        if event.get("message_type") == "group":
            group = await self._peer_name(event)
            return f"{group} {self._sender_name(event)}"
        return await self._peer_name(event)

    async def _listen(self, ws: websockets.WebSocketCommonProtocol) -> None:
        async for message in ws:
            try:
                data = json.loads(message)
            except json.JSONDecodeError:
                continue

            echo = data.get("echo")
            if echo is not None:
                fut = self._pending.get(str(echo))
                if fut is not None and not fut.done():
                    fut.set_result(data)
                continue

            if data.get("post_type") == "meta_event":
                continue
            if data.get("post_type") != "message":
                continue

            asyncio.create_task(self._handle_message(data))

    async def _handle_message(self, event: dict[str, Any]) -> None:
        try:
            if event.get("user_id") == event.get("self_id"):
                return
            uid = str(event.get("user_id") or "").strip()
            is_admin = uid and uid in admin_qq_id_set()
            sleeping = SleepStore().get().enabled
            if sleeping:
                user_text = extract_text(event).strip()
                wake_cmd = user_text in ("开始", "唤醒", "开机", "启动", "start", "/start")
                if wake_cmd and is_admin:
                    SleepStore().clear()
                    await self.send_msg(event, "机器人已恢复运行。")
                return
            if event.get("message_type") == "group":
                if settings.GROUP_REPLY_MODE == "mention" and not is_mentioned(event) and not (sleeping and is_admin):
                    return

            user_text = extract_text(event)
            images = extract_images(event)
            reply_id = extract_reply_id(event)

            quoted_text = ""
            quoted_images: list[dict[str, Any]] = []
            if reply_id:
                resp = await self.send_api_call("get_msg", {"message_id": reply_id}, timeout_s=4.0)
                data = resp.get("data") if isinstance(resp, dict) else None
                if isinstance(data, dict):
                    quoted_text = extract_text(data)
                    quoted_images = extract_images(data)

            if not user_text.strip():
                if quoted_text.strip():
                    user_text = quoted_text.strip()
                elif images or quoted_images:
                    user_text = "请分析我发送的图片。"
                else:
                    user_text = "请问有什么需要帮助？"

            user_label = await self._user_log_label(event)
            logger.opt(colors=True).info(f"<green>{user_label}</green>：{self._one_line(user_text)}")
            self_id = str(event.get("self_id") or "").strip() or "self"
            
            sender_name = self._sender_name(event)
            if event.get("message_type") == "group":
                session_id = f"group_{self_id}_{event.get('group_id')}"
                # 在群聊中，显式告知机器人当前对话者的名字，防止认错
                # 注意：user_text 此时已经是解析后的纯文本或图片描述
                # 但我们需要保留原始的意图，并在 Orchestrator 层处理消息历史
                # 这里我们只修改传递给 Orchestrator 的文本，不影响日志
                pass
            else:
                session_id = f"private_{self_id}_{event.get('user_id')}"

            prefix = ""
            if event.get("message_type") == "group":
                mid = event.get("message_id")
                if mid is not None:
                    prefix += f"[CQ:reply,id={mid}]"
                if settings.REPLY_AT_SENDER:
                    prefix += f"[CQ:at,qq={event.get('user_id')}] "

            cmd = user_text.strip()
            is_send_image_cmd = cmd in ("发送图片", "发图片", "来张图", "来一张图", "随机图片", "随机发送图片", "发图", "来图")
            if not is_send_image_cmd:
                if ("图片" in cmd or "图" in cmd) and any(k in cmd for k in ("发", "来", "随机")) and len(cmd) <= 20:
                    is_send_image_cmd = True
            if is_send_image_cmd:
                from ..tools.builtin.image_repo_random import tool_handler as image_repo_random_handler

                r = await image_repo_random_handler({}, None)
                if isinstance(r, dict) and isinstance(r.get("file_path"), str) and r["file_path"].strip():
                    fp = self._out_image_file(r["file_path"].strip())
                    if isinstance(fp, str) and fp.strip():
                        await self.send_msg(event, prefix + f"[CQ:image,file={fp}]")
                        logger.opt(colors=True).info(
                            "<magenta>BOT</magenta>：图片已发送。 <dim>| tools:</dim> <yellow>image_send</yellow>"
                        )
                        return

            if event.get("message_type") == "group":
                user_text_for_llm = f"【{sender_name}】说：{user_text}"
            else:
                user_text_for_llm = user_text

            if quoted_text.strip() and quoted_text.strip() != user_text.strip():
                user_text_for_llm = f"{user_text_for_llm.strip()}\n\n引用消息：{quoted_text.strip()}"
            image_refs: list[str] = []
            for it in (images + quoted_images)[:3]:
                if not isinstance(it, dict):
                    continue
                v_file = it.get("file") or it.get("path")
                if isinstance(v_file, str) and v_file.strip():
                    s = v_file.strip()
                    if s.startswith(("file://", "/")):
                        ingested = self._ingest_local_image(s)
                        if isinstance(ingested, str) and ingested.strip():
                            image_refs.append(ingested.strip())
                            continue
                        continue
                    resp = await self.send_api_call("get_image", {"file": s}, timeout_s=4.0)
                    data = resp.get("data") if isinstance(resp, dict) else None
                    url = data.get("url") if isinstance(data, dict) else None
                    if isinstance(url, str) and url.strip():
                        image_refs.append(url.strip())
                        continue
                    f2 = data.get("file") if isinstance(data, dict) else None
                    if isinstance(f2, str) and f2.strip() and f2.strip().startswith(("file://", "/")):
                        ingested = self._ingest_local_image(f2.strip())
                        if isinstance(ingested, str) and ingested.strip():
                            image_refs.append(ingested.strip())
                            continue
                v_url = it.get("url")
                if isinstance(v_url, str) and v_url.strip():
                    u = v_url.strip()
                    if u.startswith(("file://", "/")):
                        ingested = self._ingest_local_image(u)
                        if isinstance(ingested, str) and ingested.strip():
                            image_refs.append(ingested.strip())
                            continue
                    image_refs.append(u)
            answer, used_tools, attachments = await self._orchestrator.handle_user_event(
                session_id,
                user_text_for_llm,
                image_refs,
                str(event.get("user_id") or "").strip() or None,
                str(event.get("message_type") or "").strip() or None,
            )
            out = self._one_line(answer.strip())
            if used_tools:
                tools_s = ",".join(used_tools)
                logger.opt(colors=True).info(
                    f"<magenta>BOT</magenta>：{out} <dim>| tools:</dim> <yellow>{tools_s}</yellow>"
                )
            else:
                logger.opt(colors=True).info(f"<magenta>BOT</magenta>：{out}")
            has_generated_image = any(a.get("type") == "image" for a in attachments)
            
            if has_generated_image:
                msg = prefix
            else:
                msg = prefix + answer.strip()

            first_image = True
            appended_any_image = False
            for a in attachments:
                if not isinstance(a, dict):
                    continue
                if a.get("type") != "image":
                    continue
                raw = a.get("file_path") or a.get("path") or a.get("file") or a.get("url")
                if isinstance(raw, str) and raw.strip():
                    fp = self._out_image_file(raw.strip())
                    if not (isinstance(fp, str) and fp.strip()):
                        continue
                    if has_generated_image and msg == prefix and first_image:
                        msg += f"[CQ:image,file={fp}]"
                    else:
                        msg += f"\n[CQ:image,file={fp}]"
                    first_image = False
                    appended_any_image = True
            if msg == prefix and not appended_any_image:
                msg = prefix + (answer.strip() if answer.strip() else " ")
            await self.send_msg(event, msg)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.opt(exception=True).error("handle_message_failed")
