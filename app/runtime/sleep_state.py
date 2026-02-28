from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass

from loguru import logger


@dataclass(frozen=True)
class SleepState:
    enabled: bool
    until_ts: float | None


class SleepStore:
    def __init__(self, path: str = "./data/sleep_state.json"):
        self._path = path

    def _read(self) -> dict[str, object]:
        p = os.path.abspath(self._path)
        if not os.path.exists(p):
            return {}
        try:
            with open(p, "r", encoding="utf-8") as f:
                obj = json.load(f)
            return obj if isinstance(obj, dict) else {}
        except (OSError, json.JSONDecodeError, UnicodeDecodeError) as e:
            logger.debug("sleep_state_read_failed: {}: {}", p, e)
            return {}

    def _write(self, obj: dict[str, object]) -> None:
        p = os.path.abspath(self._path)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False)
        os.replace(tmp, p)

    def get(self) -> SleepState:
        obj = self._read()
        enabled = bool(obj.get("enabled", False))
        until = obj.get("until_ts")
        until_ts: float | None = None
        if until is not None:
            try:
                until_ts = float(until)
            except (TypeError, ValueError):
                until_ts = None
        if enabled and until_ts is not None and time.time() >= until_ts:
            self.clear()
            return SleepState(enabled=False, until_ts=None)
        return SleepState(enabled=enabled, until_ts=until_ts)

    def sleep_forever(self) -> None:
        self._write({"enabled": True, "until_ts": None})

    def sleep_for_hours(self, hours: float) -> None:
        until_ts = time.time() + max(0.0, float(hours)) * 3600.0
        self._write({"enabled": True, "until_ts": until_ts})

    def clear(self) -> None:
        self._write({"enabled": False, "until_ts": None})
