"""KeySafe UI settings (timeout etc.)."""

from __future__ import annotations

import json
from pathlib import Path

from .store import STORE_DIR

SETTINGS_PATH = STORE_DIR / "settings.json"

# минуты; 0 = выкл
TIMEOUT_CHOICES = (0, 1, 5, 15, 30)


def load_timeout_minutes() -> int:
    try:
        data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        val = int(data.get("timeout_minutes", 5))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return 5
    if val not in TIMEOUT_CHOICES:
        return 5
    return val


def save_timeout_minutes(minutes: int) -> None:
    minutes = minutes if minutes in TIMEOUT_CHOICES else 5
    STORE_DIR.mkdir(parents=True, exist_ok=True)
    data = {}
    if SETTINGS_PATH.is_file():
        try:
            data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
    data["timeout_minutes"] = minutes
    SETTINGS_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def timeout_label(minutes: int) -> str:
    if minutes <= 0:
        return "Таймаут: выкл"
    return f"Таймаут: {minutes}м"
