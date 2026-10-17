"""Auth resolution: CLI flags > env vars > config file."""

from __future__ import annotations

import json
import os
from pathlib import Path

import typer

DEFAULT_PROFILE = "default"


def get_config_path() -> Path:
    return Path.home() / ".moss" / "config.json"


def load_config() -> dict:
    path = get_config_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def save_config(data: dict) -> None:
    path = get_config_path()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def _normalize_config(config: dict) -> dict:
    """Normalize legacy and modern config shapes into profile-based format."""
    profiles = config.get("profiles")
    if isinstance(profiles, dict):
        clean_profiles: dict[str, dict[str, str]] = {}
        for name, creds in profiles.items():
            if not isinstance(name, str) or not isinstance(creds, dict):
                continue
            pid = creds.get("project_id")
            pkey = creds.get("project_key")
            if isinstance(pid, str) and isinstance(pkey, str) and pid and pkey:
                clean_profiles[name] = {"project_id": pid, "project_key": pkey}

        active = config.get("active_profile")
        if not isinstance(active, str) or not active:
            active = DEFAULT_PROFILE
        return {"active_profile": active, "profiles": clean_profiles}

    # Backward compatibility with the old flat shape:
    # {"project_id": "...", "project_key": "..."}
    pid = config.get("project_id")
    pkey = config.get("project_key")
    normalized: dict[str, object] = {
        "active_profile": DEFAULT_PROFILE,
        "profiles": {},
    }
    if isinstance(pid, str) and isinstance(pkey, str) and pid and pkey:
        normalized["profiles"] = {
            DEFAULT_PROFILE: {"project_id": pid, "project_key": pkey}
        }
    return normalized


def get_selected_profile(profile: str | None = None) -> str:
    if profile:
        return profile

    env_profile = os.getenv("MOSS_PROFILE")
    if env_profile:
        return env_profile

    config = _normalize_config(load_config())
    active_profile = config.get("active_profile")
    if isinstance(active_profile, str) and active_profile:
        return active_profile
    return DEFAULT_PROFILE


def get_profile_credentials(profile: str) -> tuple[str | None, str | None]:
    config = _normalize_config(load_config())
    profiles = config.get("profiles", {})
    if not isinstance(profiles, dict):
        return None, None

    creds = profiles.get(profile)
    if not isinstance(creds, dict):
        return None, None
    pid = creds.get("project_id")
    pkey = creds.get("project_key")
    if not isinstance(pid, str) or not isinstance(pkey, str):
        return None, None
    return pid, pkey


def set_profile_credentials(profile: str, project_id: str, project_key: str) -> None:
    normalized = _normalize_config(load_config())
    profiles = normalized.get("profiles", {})
    if not isinstance(profiles, dict):
        profiles = {}

    profiles[profile] = {"project_id": project_id, "project_key": project_key}
    active_profile = normalized.get("active_profile")
    if not isinstance(active_profile, str) or not active_profile or active_profile not in profiles:
        active_profile = profile
    save_config({"active_profile": active_profile, "profiles": profiles})


def list_profiles() -> list[str]:
    config = _normalize_config(load_config())
    profiles = config.get("profiles", {})
    if not isinstance(profiles, dict):
        return []
    return sorted(name for name in profiles.keys() if isinstance(name, str) and name)


def delete_profile(profile: str) -> tuple[bool, str | None]:
    normalized = _normalize_config(load_config())
    profiles = normalized.get("profiles", {})
    if not isinstance(profiles, dict) or profile not in profiles:
        return False, None

    del profiles[profile]

    active_profile = normalized.get("active_profile")
    remaining_profiles = sorted(name for name in profiles.keys() if isinstance(name, str) and name)
    if (
        not isinstance(active_profile, str)
        or not active_profile
        or active_profile == profile
        or active_profile not in profiles
    ):
        active_profile = remaining_profiles[0] if remaining_profiles else None

    data: dict[str, object] = {"profiles": profiles}
    if isinstance(active_profile, str) and active_profile:
        data["active_profile"] = active_profile
    save_config(data)
    return True, active_profile if isinstance(active_profile, str) and active_profile else None


def resolve_credentials(
    project_id: str | None = None,
    project_key: str | None = None,
    profile: str | None = None,
) -> tuple[str, str]:
    """Resolve credentials from flags, env vars, or config file."""
    pid = project_id or os.getenv("MOSS_PROJECT_ID")
    pkey = project_key or os.getenv("MOSS_PROJECT_KEY")

    if pid and pkey:
        return pid, pkey

    selected_profile = get_selected_profile(profile)
    cfg_pid, cfg_pkey = get_profile_credentials(selected_profile)
    pid = pid or cfg_pid
    pkey = pkey or cfg_pkey

    if not pid or not pkey:
        raise typer.BadParameter(
            "Missing credentials. Provide --project-id/--project-key, "
            "set MOSS_PROJECT_ID/MOSS_PROJECT_KEY env vars, "
            f"or run 'moss init --profile {selected_profile}' to save them."
        )
    return pid, pkey
