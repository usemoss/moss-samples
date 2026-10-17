"""Unit tests for the MCP server app."""

import os

import pytest


class FakeMemory:
    def __init__(self):
        self.load_index_calls = 0

    async def load_index(self):
        self.load_index_calls += 1

    async def insert_memory(self, content, *, tags=None):
        return "generated-id"

    async def search_memory(self, query, *, top_k=5, tags=None):
        from letta_moss.memory import ArchivalMemoryItem

        return [ArchivalMemoryItem(id="1", content="hit", tags=[], metadata={}, score=0.9)]

    async def delete_memory(self, memory_id):
        pass


class TestCreateMcpApp:
    def test_returns_fastmcp_with_expected_tools(self):
        import asyncio

        from mcp.server.fastmcp import FastMCP

        from letta_moss.mcp_app import create_mcp_app

        app = create_mcp_app(FakeMemory())
        assert isinstance(app, FastMCP)

        tools = asyncio.run(app.list_tools())
        names = {t.name for t in tools}
        assert names == {"moss_memory_insert", "moss_memory_search", "moss_memory_delete"}


class TestMcpToolBehavior:
    async def test_insert_tool_delegates(self):
        from letta_moss.mcp_app import create_mcp_app

        memory = FakeMemory()
        app = create_mcp_app(memory)
        fn = app._tool_manager.get_tool("moss_memory_insert").fn
        result = await fn(content="hello", tags=["a"])
        assert result == "generated-id"

    async def test_search_tool_returns_dicts(self):
        from letta_moss.mcp_app import create_mcp_app

        app = create_mcp_app(FakeMemory())
        fn = app._tool_manager.get_tool("moss_memory_search").fn
        result = await fn(query="q", top_k=5)
        assert result == [{"id": "1", "content": "hit", "tags": [], "metadata": {}, "score": 0.9}]


class TestMcpErrorMapping:
    async def test_insert_exception_is_raised_as_runtime_error(self):
        from letta_moss.mcp_app import create_mcp_app

        memory = FakeMemory()

        async def broken_insert(content, *, tags=None):
            raise ValueError("moss blew up")

        memory.insert_memory = broken_insert
        app = create_mcp_app(memory)
        fn = app._tool_manager.get_tool("moss_memory_insert").fn

        with pytest.raises(RuntimeError, match="Moss memory insert failed"):
            await fn(content="x")

    async def test_search_exception_is_raised_as_runtime_error(self):
        from letta_moss.mcp_app import create_mcp_app

        memory = FakeMemory()

        async def broken_search(query, *, top_k=5):
            raise ValueError("moss blew up")

        memory.search_memory = broken_search
        app = create_mcp_app(memory)
        fn = app._tool_manager.get_tool("moss_memory_search").fn

        with pytest.raises(RuntimeError, match="Moss memory search failed"):
            await fn(query="x")

    async def test_delete_exception_is_raised_as_runtime_error(self):
        from letta_moss.mcp_app import create_mcp_app

        memory = FakeMemory()

        async def broken_delete(memory_id):
            raise ValueError("moss blew up")

        memory.delete_memory = broken_delete
        app = create_mcp_app(memory)
        fn = app._tool_manager.get_tool("moss_memory_delete").fn

        with pytest.raises(RuntimeError, match="Moss memory delete failed"):
            await fn(memory_id="1")


_HAS_MOSS_CREDS = bool(os.environ.get("MOSS_PROJECT_ID")) and bool(
    os.environ.get("MOSS_PROJECT_KEY")
)
_MOSS_INDEX = os.environ.get("MOSS_INDEX_NAME", "letta-moss-test")


@pytest.mark.skipif(
    not _HAS_MOSS_CREDS, reason="requires MOSS_PROJECT_ID + MOSS_PROJECT_KEY env vars"
)
class TestMcpRoundtrip:
    async def test_insert_then_search_then_delete(self):
        """Spin up the FastMCP streamable-HTTP app and round-trip a memory.

        Uses the index named ``MOSS_INDEX_NAME`` (created automatically by
        the first insert if it doesn't already exist).
        """
        import asyncio
        import socket
        from contextlib import asynccontextmanager

        import httpx
        import uvicorn
        from mcp.client.session import ClientSession
        from mcp.client.streamable_http import streamablehttp_client

        from letta_moss import MossLettaMemory, create_mcp_app

        def free_port() -> int:
            with socket.socket() as s:
                s.bind(("127.0.0.1", 0))
                return s.getsockname()[1]

        port = free_port()
        memory = MossLettaMemory(
            project_id=os.environ["MOSS_PROJECT_ID"],
            project_key=os.environ["MOSS_PROJECT_KEY"],
            index_name=_MOSS_INDEX,
        )
        app = create_mcp_app(memory)

        config = uvicorn.Config(
            app.streamable_http_app(), host="127.0.0.1", port=port, log_level="warning"
        )
        server = uvicorn.Server(config)

        @asynccontextmanager
        async def running_server():
            task = asyncio.create_task(server.serve())
            for _ in range(50):
                try:
                    async with httpx.AsyncClient() as http:
                        r = await http.get(f"http://127.0.0.1:{port}/mcp", timeout=0.2)
                        if r.status_code < 500:
                            break
                except (httpx.ConnectError, httpx.ReadTimeout):
                    await asyncio.sleep(0.1)
            try:
                yield
            finally:
                server.should_exit = True
                await task

        async with running_server():
            async with streamablehttp_client(f"http://127.0.0.1:{port}/mcp") as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    tool_names = [t.name for t in (await session.list_tools()).tools]
                    expected = {"moss_memory_insert", "moss_memory_search", "moss_memory_delete"}
                    assert expected <= set(tool_names)

                    insert_result = await session.call_tool(
                        "moss_memory_insert",
                        arguments={
                            "content": "The user's favorite color is teal.",
                            "tags": ["preference"],
                        },
                    )
                    assert not insert_result.isError
                    memory_id = insert_result.content[0].text.strip('"')

                    search_result = await session.call_tool(
                        "moss_memory_search", arguments={"query": "favorite color"}
                    )
                    assert not search_result.isError

                    delete_result = await session.call_tool(
                        "moss_memory_delete", arguments={"memory_id": memory_id}
                    )
                    assert not delete_result.isError
