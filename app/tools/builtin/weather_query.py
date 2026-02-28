from __future__ import annotations

from typing import Any

import httpx
from loguru import logger

from ...core.http_client import get_client
from ...tools.base import Tool


_WEATHER_CODE_ZH: dict[int, str] = {
    0: "晴",
    1: "晴间多云",
    2: "多云",
    3: "阴",
    45: "雾",
    48: "雾凇",
    51: "小毛毛雨",
    53: "毛毛雨",
    55: "大毛毛雨",
    56: "小冻毛毛雨",
    57: "大冻毛毛雨",
    61: "小雨",
    63: "中雨",
    65: "大雨",
    66: "小冻雨",
    67: "大冻雨",
    71: "小雪",
    73: "中雪",
    75: "大雪",
    77: "米雪",
    80: "小阵雨",
    81: "阵雨",
    82: "强阵雨",
    85: "小阵雪",
    86: "强阵雪",
    95: "雷暴",
    96: "雷暴伴小冰雹",
    99: "雷暴伴大冰雹",
}


def _num(v: Any) -> float | None:
    try:
        if v is None:
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def _has_cjk(s: str) -> bool:
    for ch in s or "":
        o = ord(ch)
        if 0x4E00 <= o <= 0x9FFF:
            return True
    return False


def _pick_best_geocode(location: str, results: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not results:
        return None
    loc = (location or "").strip()
    has_cjk = _has_cjk(loc)

    def score(it: dict[str, Any]) -> float:
        s = 0.0
        name = it.get("name")
        admin1 = it.get("admin1")
        if isinstance(name, str) and name.strip() and loc and (loc in name or name in loc):
            s += 2.0
        if isinstance(admin1, str) and admin1.strip() and loc and (loc in admin1 or admin1 in loc):
            s += 1.0
        cc = it.get("country_code")
        if has_cjk and isinstance(cc, str) and cc.upper() == "CN":
            s += 1.0
        fc = it.get("feature_code")
        if isinstance(fc, str):
            if fc == "PPLC":
                s += 5.0
            elif fc == "PPLA":
                s += 4.0
            elif fc == "PPLA2":
                s += 3.0
            elif fc == "PPLA3":
                s += 2.5
            elif fc == "PPL":
                s += 2.0
        pop = it.get("population")
        if isinstance(pop, (int, float)) and pop > 0:
            s += min(float(pop) / 1_000_000.0, 10.0)
        return s

    best = max(results, key=score)
    return best if isinstance(best, dict) else None


async def tool_handler(args, _ctx):
    location = str(args.get("location") or "").strip()
    lat = _num(args.get("latitude"))
    lon = _num(args.get("longitude"))

    http = get_client()

    place_name = ""
    if lat is None or lon is None:
        if not location:
            return {"error": "missing_location"}
        candidates = [location]
        loc = location.strip()
        if _has_cjk(loc) and not loc.endswith(("市", "省", "区", "县")):
            candidates.extend([f"{loc}市", f"{loc}省"])

        all_results: list[dict[str, Any]] = []
        for name in candidates:
            try:
                r = await http.get(
                    "https://geocoding-api.open-meteo.com/v1/search",
                    params={"name": name, "count": "5", "language": "zh", "format": "json"},
                    headers={"User-Agent": "new_bot/1.0"},
                    timeout=20.0,
                )
            except httpx.HTTPError as e:
                logger.debug('geocoding_failed: {}: {}', name, e)
                continue
            if r.status_code >= 400:
                continue
            data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
            results = data.get("results") if isinstance(data, dict) else None
            if isinstance(results, list) and results:
                for it in results:
                    if isinstance(it, dict):
                        all_results.append(it)

        best = _pick_best_geocode(location, all_results)
        if not isinstance(best, dict):
            return {"error": "location_not_found", "location": location}

        lat = _num(best.get("latitude"))
        lon = _num(best.get("longitude"))
        if lat is None or lon is None:
            return {"error": "location_not_found", "location": location}
        parts = []
        name = best.get("name")
        if isinstance(name, str) and name.strip():
            parts.append(name.strip())
        admin1 = best.get("admin1")
        if isinstance(admin1, str) and admin1.strip() and admin1.strip() not in parts:
            parts.append(admin1.strip())
        country = best.get("country")
        if isinstance(country, str) and country.strip() and country.strip() not in parts:
            parts.append(country.strip())
        place_name = " ".join(parts).strip() or location
    else:
        place_name = location

    try:
        r = await http.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": str(lat),
                "longitude": str(lon),
                "timezone": "auto",
                "current": "temperature_2m,apparent_temperature,relative_humidity_2m,precipitation,weather_code,wind_speed_10m,wind_direction_10m",
                "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max",
                "forecast_days": "1",
            },
            headers={"User-Agent": "new_bot/1.0"},
            timeout=30.0,
        )
    except httpx.HTTPError as e:
        return {"error": "forecast_failed", "message": str(e)}
    if r.status_code >= 400:
        return {"error": "forecast_failed", "status_code": r.status_code}
    data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    if not isinstance(data, dict):
        return {"error": "forecast_failed"}

    cur = data.get("current") if isinstance(data.get("current"), dict) else {}
    daily = data.get("daily") if isinstance(data.get("daily"), dict) else {}

    wc = cur.get("weather_code")
    wc_i = int(wc) if isinstance(wc, (int, float)) else None
    wc_text = _WEATHER_CODE_ZH.get(wc_i) if wc_i is not None else ""

    def _first_daily(key: str):
        v = daily.get(key)
        if isinstance(v, list) and v:
            return v[0]
        return None

    return {
        "location": place_name,
        "latitude": lat,
        "longitude": lon,
        "timezone": data.get("timezone") if isinstance(data.get("timezone"), str) else "",
        "current": {
            "time": cur.get("time") if isinstance(cur.get("time"), str) else "",
            "temperature_c": _num(cur.get("temperature_2m")),
            "apparent_temperature_c": _num(cur.get("apparent_temperature")),
            "humidity_percent": _num(cur.get("relative_humidity_2m")),
            "precipitation_mm": _num(cur.get("precipitation")),
            "wind_speed_kmh": _num(cur.get("wind_speed_10m")),
            "wind_direction_deg": _num(cur.get("wind_direction_10m")),
            "weather_code": wc_i,
            "weather_text": wc_text,
        },
        "today": {
            "temperature_max_c": _num(_first_daily("temperature_2m_max")),
            "temperature_min_c": _num(_first_daily("temperature_2m_min")),
            "precipitation_probability_max_percent": _num(_first_daily("precipitation_probability_max")),
        },
        "source": "open-meteo",
    }


TOOL = Tool(
    name="weather_query",
    description="天气查询：输入地点（或经纬度），返回当前天气与今日预报（Open-Meteo）。",
    parameters={
        "type": "object",
        "properties": {
            "location": {"type": "string", "description": "地点名称，例如 北京、上海、Hangzhou"},
            "latitude": {"type": "number", "description": "可选：纬度"},
            "longitude": {"type": "number", "description": "可选：经度"},
        },
        "required": [],
        "additionalProperties": False,
    },
    handler=tool_handler,
)
