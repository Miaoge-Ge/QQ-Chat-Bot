from ..base import Tool
from .admin_manage import TOOL as ADMIN_MANAGE
from .image_generate import TOOL as IMAGE_GENERATE
from .image_repo_random import TOOL as IMAGE_REPO_RANDOM
from .image_save import TOOL as IMAGE_SAVE
from .model_name import TOOL as MODEL_NAME
from .time_now import TOOL as TIME_NOW
from .web_search import TOOL as WEB_SEARCH
from .weather_query import TOOL as WEATHER_QUERY
from .image_understand import TOOL as IMAGE_UNDERSTAND


def _to_tool(spec: dict | Tool) -> Tool:
    if isinstance(spec, Tool):
        return spec
    return Tool(
        name=str(spec.get("name") or ""),
        description=str(spec.get("description") or ""),
        parameters=spec.get("parameters") if isinstance(spec.get("parameters"), dict) else {"type": "object", "properties": {}},
        handler=spec["handler"],
    )

ALL_BUILTIN_TOOLS = [
    _to_tool(ADMIN_MANAGE),
    _to_tool(TIME_NOW),
    _to_tool(MODEL_NAME),
    _to_tool(WEB_SEARCH),
    _to_tool(WEATHER_QUERY),
    _to_tool(IMAGE_SAVE),
    _to_tool(IMAGE_REPO_RANDOM),
    _to_tool(IMAGE_GENERATE),
    _to_tool(IMAGE_UNDERSTAND),
]
