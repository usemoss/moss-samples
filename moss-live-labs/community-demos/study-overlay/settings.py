import json
import os
import platform
from pathlib import Path
from typing import Any


APP_NAME = "StudyOverlay"
CONFIG_FILE = "config.json"

REQUIRED_KEYS = (
    "OPENROUTER_API_KEY",
    "MOSS_PROJECT_ID",
    "MOSS_PROJECT_KEY",
)


def user_data_dir() -> Path:
    system = platform.system()
    if system == "Darwin":
        base = Path.home() / "Library" / "Application Support"
    elif system == "Windows":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / APP_NAME


def config_path() -> Path:
    return user_data_dir() / CONFIG_FILE


def load_settings() -> dict[str, str]:
    path = config_path()
    if not path.exists():
        return {}

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}

    return {
        key: str(value).strip()
        for key, value in data.items()
        if isinstance(key, str) and value is not None
    }


def save_settings(values: dict[str, Any]) -> dict[str, str]:
    current = load_settings()
    for key in REQUIRED_KEYS:
        value = str(values.get(key, "")).strip()
        if value:
            current[key] = value
        else:
            current.pop(key, None)

    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(current, indent=2), encoding="utf-8")
    return current


def missing_required(settings: dict[str, str] | None = None) -> list[str]:
    data = settings if settings is not None else load_settings()
    return [key for key in REQUIRED_KEYS if not data.get(key)]


def public_settings(settings: dict[str, str] | None = None) -> dict[str, Any]:
    data = settings if settings is not None else load_settings()
    return {
        "config_path": str(config_path()),
        "missing": missing_required(data),
        "has_openrouter": bool(data.get("OPENROUTER_API_KEY")),
        "has_moss_project_id": bool(data.get("MOSS_PROJECT_ID")),
        "has_moss_project_key": bool(data.get("MOSS_PROJECT_KEY")),
        "values": {
            "OPENROUTER_API_KEY": data.get("OPENROUTER_API_KEY", ""),
            "MOSS_PROJECT_ID": data.get("MOSS_PROJECT_ID", ""),
            "MOSS_PROJECT_KEY": data.get("MOSS_PROJECT_KEY", ""),
        },
    }
