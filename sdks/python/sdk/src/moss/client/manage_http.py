from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Mapping, Optional

DEFAULT_BASE_URL = "https://service.usemoss.dev"
MANAGE_PATH = "/v1/manage"


class ManageApiError(RuntimeError):
    """HTTP error from POST /v1/manage."""

    def __init__(self, status: int, body: str) -> None:
        suffix = f": {body}" if body else ""
        super().__init__(f"HTTP error! status: {status}{suffix}")
        self.status = status
        self.body = body


def resolve_manage_url() -> str:
    base = os.environ.get("MOSS_CLOUD_API_BASE_URL", DEFAULT_BASE_URL)
    return f"{base.rstrip('/')}{MANAGE_PATH}"


def _omit_none(data: Optional[Mapping[str, Any]]) -> dict[str, Any]:
    if not data:
        return {}
    return {key: value for key, value in data.items() if value is not None}


def request_manage(
    project_id: str,
    project_key: str,
    action: str,
    data: Optional[Mapping[str, Any]] = None,
) -> Any:
    """POST /v1/manage with X-Project-Key.

    Reserved fields (`action`, `projectId`) are assigned after the payload
    spread so callers cannot overwrite them.
    """
    body = {**_omit_none(data), "action": action, "projectId": project_id}
    request = urllib.request.Request(
        resolve_manage_url(),
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "X-Project-Key": project_key,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=600) as response:
            raw = response.read()
    except urllib.error.HTTPError as error:
        err_body = error.read().decode("utf-8", "replace")
        raise ManageApiError(error.code, err_body) from error
    if not raw:
        return {}
    return json.loads(raw.decode("utf-8"))
