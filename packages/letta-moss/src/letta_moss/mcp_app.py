"""Moss archival memory exposed as an MCP server for Letta.

Letta can act as an MCP host, connecting to an external MCP server without
any Moss code running inside Letta's own process. Run this module's app
behind a reachable URL and register it as an MCP server on the agent, as an
alternative to the in-sandbox custom tools in ``letta_moss.tools``.
"""

from __future__ import annotations

import dataclasses
from contextlib import asynccontextmanager

from mcp.server.fastmcp import FastMCP

from . import tools
from .memory import MossLettaMemory


def create_mcp_app(memory: MossLettaMemory) -> FastMCP:
    """Build a FastMCP server exposing Moss archival memory tools.

    The server awaits ``memory.load_index()`` in its lifespan before
    accepting tool calls. This is the single exception-to-tool-error
    boundary: adapter methods raise ordinary exceptions, and each tool
    wrapper here re-raises them as ``RuntimeError`` so FastMCP serializes
    them as MCP tool-errors.

    Tool names are taken from ``letta_moss.tools``'s function names (via
    ``@app.tool(name=...)``) rather than hardcoded again here, so this
    surface and the custom-tool surface in ``letta_moss.tools`` can't
    silently drift apart if one of them is renamed.
    """

    @asynccontextmanager
    async def lifespan(_app: FastMCP):
        await memory.load_index()
        yield

    app = FastMCP("letta-moss", lifespan=lifespan)

    @app.tool(name=tools.moss_memory_insert.__name__)
    async def _insert(content: str, tags: list[str] | None = None) -> str:
        """Insert a new memory into Moss-backed archival storage."""
        try:
            return await memory.insert_memory(content, tags=tags)
        except Exception as e:
            raise RuntimeError("Moss memory insert failed") from e

    @app.tool(name=tools.moss_memory_search.__name__)
    async def _search(query: str, top_k: int = 5, tags: list[str] | None = None) -> list[dict]:
        """Search Moss-backed archival storage for memories relevant to a query."""
        try:
            items = await memory.search_memory(query, top_k=top_k, tags=tags)
        except Exception as e:
            raise RuntimeError("Moss memory search failed") from e
        return [dataclasses.asdict(item) for item in items]

    @app.tool(name=tools.moss_memory_delete.__name__)
    async def _delete(memory_id: str) -> None:
        """Delete a memory from Moss-backed archival storage by id."""
        try:
            await memory.delete_memory(memory_id)
        except Exception as e:
            raise RuntimeError("Moss memory delete failed") from e

    return app
