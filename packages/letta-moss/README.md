# letta-moss

Moss-backed archival memory for [Letta](https://docs.letta.com) (MemGPT) agents.

Letta's archival memory storage layer no longer has a pluggable backend interface — it's hardcoded to Postgres/pgvector, Turbopuffer, or Pinecone, with no public extension point to register a fourth. Letta's own docs recommend "External RAG through custom tools or MCP" as the sanctioned path once you need something beyond built-in archival memory. This package follows that path: it wraps a Moss index as agent-callable memory tools, in both forms Letta documents.

**No code in the `letta` package is modified.** You register these tools against your Letta agent explicitly, and set `include_base_tools=False` so Moss fully replaces Letta's built-in `archival_memory_insert`/`archival_memory_search` tools.

## Install

```bash
pip install letta-moss
# or
uv add letta-moss
```

## Quickstart — Option A: custom tools (recommended, no extra process)

Registers plain async functions with `client.tools.upsert_from_function`; they run inside Letta's own sandboxed tool-execution environment.

```python
from letta_client import Letta
from letta_moss import moss_memory_insert, moss_memory_search

client = Letta(token="...")

# Deliberately excludes moss_memory_delete — see "Deletion is opt-in" below.
tool_ids = [
    client.tools.upsert_from_function(func=fn, pip_requirements=["letta-moss"]).id
    for fn in (moss_memory_insert, moss_memory_search)
]

agent = client.agents.create(
    model="...",
    embedding="...",
    include_base_tools=False,  # drop Letta's built-in archival_memory_* tools
    tool_ids=tool_ids,
    tool_exec_environment_variables={
        "MOSS_PROJECT_ID": "moss-project-id",
        "MOSS_PROJECT_KEY": "moss-project-key",
        "MOSS_INDEX_NAME": "my-agent-memory",
    },
)
```

**Why `pip_requirements`:** Letta's `upsert_from_function` uploads only the extracted source of each function, not the rest of `letta_moss/tools.py` — so `moss_memory_insert`/`_search`/`_delete` each import `_get_memory` (and, for search, `dataclasses`) *inside* their own body rather than relying on this module's top-level imports. Passing `pip_requirements=["letta-moss"]` ensures the sandbox has the package installed so those in-body imports resolve.

**Deletion is opt-in:** `moss_memory_delete` is left out of the default registration above on purpose. Letta's own built-in archival memory has no delete tool either, and giving every conversational agent standing access to erase entries from a shared index is a larger blast radius than most agents need — a prompt-injected or simply mistaken agent could wipe archival memory after a search returns ids. Register it explicitly, and only for agents that are meant to curate memory (e.g. a separate admin/maintenance agent), the same way as the other tools:

```python
from letta_moss import moss_memory_delete

delete_tool_id = client.tools.upsert_from_function(
    func=moss_memory_delete, pip_requirements=["letta-moss"]
).id
```

## Quickstart — Option B: MCP server

Runs Moss as an out-of-process MCP server; Letta connects to it as an MCP host, so no Moss code runs inside Letta's own infrastructure. This option needs an ASGI server, so install the `server` extra:

```bash
pip install "letta-moss[server]"
```

```python
import uvicorn
from letta_moss import MossLettaMemory, create_mcp_app

memory = MossLettaMemory(
    project_id="moss-project-id",
    project_key="moss-project-key",
    index_name="my-agent-memory",
)

app = create_mcp_app(memory)
uvicorn.run(app.streamable_http_app(), host="127.0.0.1", port=8080)
```

**Security:** `create_mcp_app` adds no authentication of its own — the `moss_memory_insert`/`_search`/`_delete` tools are wide open to anyone who can reach the listening port. The snippet above binds to `127.0.0.1` deliberately; if Letta runs on a different host and you need to expose this beyond localhost, put it behind a reverse proxy or gateway that authenticates the caller (e.g. FastMCP's `auth`/`token_verifier` options, mTLS, or a private network) rather than binding `host="0.0.0.0"` directly to a public interface.

Then register the server as an MCP tool source on your Letta agent, pointing at `https://<public-host>/mcp` (behind whatever auth layer you put in front of it), and — as in Option A — create the agent with `include_base_tools=False`.

## Public API

| Symbol | Kind | Purpose |
|---|---|---|
| `MossLettaMemory(*, project_id=None, project_key=None, index_name, top_k=5, alpha=0.8, auto_refresh=True, refresh_interval_seconds=60)` | class | Core adapter; `async load_index()`, `async insert_memory(content, tags=, metadata=) -> str`, `async search_memory(query, top_k=, tags=) -> list[ArchivalMemoryItem]`, `async delete_memory(memory_id)`, `async get_memory(memory_id) -> ArchivalMemoryItem \| None`, `async list_memories(limit=) -> list[ArchivalMemoryItem]`. Falls back to `MOSS_PROJECT_ID`/`MOSS_PROJECT_KEY` env vars when credentials are omitted. `auto_refresh`/`refresh_interval_seconds` are forwarded to Moss's `load_index()` so this process's in-memory snapshot picks up writes made by *other* processes against the same index, not just its own. |
| `moss_memory_insert(content, tags=None) -> str` | async function | Custom-tool wrapper; insert a memory, return its id. |
| `moss_memory_search(query, top_k=5, tags=None) -> list[dict]` | async function | Custom-tool wrapper; search memories, return dicts. |
| `moss_memory_delete(memory_id) -> None` | async function | Custom-tool wrapper; delete a memory by id. |
| `create_mcp_app(memory) -> FastMCP` | function | Returns a FastMCP server exposing `moss_memory_insert`/`moss_memory_search`/`moss_memory_delete`; runs `memory.load_index()` in its lifespan. |
| `ArchivalMemoryItem` | dataclass | `id: str`, `content: str`, `tags: list[str]`, `metadata: dict`, `score: float \| None` (only populated on search results). |

**Note:** `include_base_tools=False` is required when attaching these tools, or the agent ends up with two competing memory tool sets — Letta's built-in `archival_memory_*` tools and these Moss-backed ones.

**Index creation:** `insert_memory` creates the backing Moss index automatically on the first call if `index_name` doesn't exist yet — you don't need to pre-create it. `search_memory`/`load_index` treat a not-yet-created index as "no memories yet" (returning an empty list) rather than raising.

**Tag filtering:** `search_memory(..., tags=...)` filters client-side on the already-returned results, not via a Moss-side query filter — tags are stored as a single JSON-encoded metadata blob, and Moss's `QueryOptions.filter` grammar only supports `$eq`-style matching against scalar string fields, which can't express "contains tag X" against that blob. To reduce (not eliminate) the chance of under-returning, the underlying query is oversampled when `tags` is set and truncated back to the requested `top_k` after filtering.

**Reserved metadata key:** `insert_memory`'s `metadata` argument must not contain a `"tags"` key — `tags` is a first-class parameter, and passing it inside `metadata` too raises `ValueError` rather than silently overwriting one or the other.

**Env var fallback:** `MossLettaMemory` falls back to `MOSS_PROJECT_ID`/`MOSS_PROJECT_KEY` when constructor args are omitted, unlike some other Moss integrations in this repo (e.g. `agora-moss`) that require explicit args. This is deliberate: these tools typically run inside Letta's sandboxed tool-execution environment, where env vars passed via `tool_exec_environment_variables` are the natural way to configure credentials without hardcoding them in tool source.

**Sandbox process reuse:** the Option A custom tools cache a single `MossLettaMemory` instance at module scope per worker process (so `load_index()` only runs once). That cache is keyed on `MOSS_PROJECT_ID`/`MOSS_PROJECT_KEY`/`MOSS_INDEX_NAME` — if Letta reuses the same worker process for a different agent whose `tool_exec_environment_variables` set different values, the cached instance is discarded and rebuilt against the new values rather than leaking reads/writes across agents.

## Dependencies

- `moss>=1.1.1`
- `mcp>=1.28,<2` (Model Context Protocol Python SDK, FastMCP; pinned to the v1 line — `create_mcp_app`'s `lifespan=` support and `streamable_http_app()` aren't in the v2 `MCPServer` API)
- Python `>=3.10,<3.15`

This package does not depend on `letta`/`letta-client` — it installs and runs standalone; you bring your own Letta client to register the tools.

## License

BSD-2-Clause. See repository root.
