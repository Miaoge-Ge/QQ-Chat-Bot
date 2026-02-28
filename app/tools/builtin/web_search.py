from __future__ import annotations

import re
from html import unescape
from typing import Any

import httpx

from ...core.http_client import get_client
from ...tools.base import Tool


def _strip_tags(s: str) -> str:
    return re.sub(r"<[^>]+>", "", s or "").strip()


def _parse_bing_html(html: str, limit: int) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    if not html:
        return out
    for m in re.finditer(r'<li class="b_algo"[\s\S]*?</li>', html):
        block = m.group(0)
        m2 = re.search(r'<h2[^>]*>\s*<a[^>]+href="([^"]+)"[^>]*>([\s\S]*?)</a>', block)
        if not m2:
            continue
        url = unescape(m2.group(1)).strip()
        title = unescape(_strip_tags(m2.group(2)))
        snippet = ""
        m3 = re.search(r"<p[^>]*>([\s\S]*?)</p>", block)
        if m3:
            snippet = unescape(_strip_tags(m3.group(1)))
        if title and url:
            out.append({"title": title, "url": url, "snippet": snippet})
        if len(out) >= limit:
            break
    return out


async def tool_handler(args: dict[str, Any], _ctx) -> dict[str, Any]:
    q = str(args.get("query") or "").strip()
    if not q:
        return {"error": "empty_query"}
    http = get_client()
    try:
        r = await http.get(
            "https://cn.bing.com/search",
            params={"q": q},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=20.0,
        )
    except httpx.HTTPError as e:
        return {"error": "http_error", "message": str(e), "source": "bing"}
    if r.status_code >= 400:
        return {"error": "http_error", "status_code": r.status_code, "source": "bing"}
    results = _parse_bing_html(r.text, 6)
    if not results:
        return {"error": "no_results", "query": q, "source": "bing"}
    return {"query": q, "results": results, "source": "bing"}


TOOL = Tool(
    name="web_search",
    description="网络查询：输入搜索词，返回部分相关结果（Bing）。",
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "搜索关键词"},
        },
        "required": ["query"],
        "additionalProperties": False,
    },
    handler=tool_handler,
)
