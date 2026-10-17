"""Shared shell-completion helpers for dynamic value completion."""

from __future__ import annotations

import asyncio

import typer

from .config import resolve_credentials


def complete_index_name(
    ctx: typer.Context, args: list[str], incomplete: str
) -> list[str]:
    """Autocompletion callback that lists the user's index names.

    The shell invokes this while completing an index-name argument. It resolves
    credentials the same way commands do (flags > env vars > active profile) and
    lists the available indexes.

    It is intentionally best-effort: any failure (missing credentials, network
    error, or the SDK not being importable) returns no completions so the shell
    never errors out or blocks. Typer filters the returned names against the
    text typed so far, so we return the full list.
    """
    try:
        from moss import MossClient  # lazy import; the SDK is heavy

        project_id = None
        project_key = None
        profile = None
        root = ctx.find_root() if ctx is not None else None
        if root is not None and root.params:
            project_id = root.params.get("project_id")
            project_key = root.params.get("project_key")
            profile = root.params.get("profile")

        pid, pkey = resolve_credentials(project_id, project_key, profile)
        client = MossClient(pid, pkey)
        indexes = asyncio.run(client.list_indexes())
        return [idx.name for idx in indexes if getattr(idx, "name", None)]
    except Exception:
        return []
