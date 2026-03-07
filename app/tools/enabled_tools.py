ENABLED_TOOL_NAMES = [
    "admin_manage",
    "time_now",
    "model_name",
    "web_search",
    "weather_query",
    "image_save",
    "image_repo_random",
    "image_generate",
    "image_understand",
]


def is_enabled(name: str) -> bool:
    return (name or "").strip() in ENABLED_TOOL_NAMES
