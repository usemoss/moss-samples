# AGENTS.md

This file provides guidance to AI agents when working with code in this repository.

## What This Repo Is

Moss is a real-time semantic search runtime for AI agents targeting sub-10ms query latency. The runtime runs on-device using bundled embedding models (`moss-minilm`) no external embedding API calls are needed. The cloud layer handles project management and index distribution; the local layer handles querying.

This repository contains the **multi-language SDKs**, **framework integrations** (cookbooks), and **application examples**.

## Repository Layout

```
sdks/
  python/sdk/      — Python SDK (PyPI: moss), Python 3.10+
  javascript/sdk/  — JS/TS SDK (npm: @moss-dev/moss), ESM-only
  elixir/sdk/      — Elixir SDK (Hex: moss)
  swift/           — Swift SDK for iOS (wraps Moss.xcframework)
  react-native/    — Expo / React Native module (@moss-dev/moss-react-native); iOS native, Android stub
examples/
  python/          — Standalone Python usage examples
  javascript/      — Standalone TS usage examples
  javascript-web/  — Browser/Vite examples (no Node runtime)
  react-native/    — Expo usage sketch for @moss-dev/moss-react-native
  c/               — C binding examples
  go/              — Standalone Go SDK usage examples
  bun/             — Bun runtime example
  python-classification/ — Text classification with Moss
  voice-agents/    - End-to-end voice agents (LiveKit-based)
    airline-pnr/         - Ambient retrieval; per-caller Moss index, swap mid-call
    mortgage-lending/    - Multi-agent flow with shared session state
  cookbook/        — Framework integrations (one subdirectory per framework)
    autogen/       — AutoGen multi-agent e-commerce support
    crewai/        — CrewAI retrieval tool
    daytona/       — Log Ingestion Q&A Agent on Daytona sandboxes
    dspy/          — DSPy notebook
    haystack/      — Haystack RAG pipeline integration
    langchain/     — LangChain retriever + tool integration
    langflow/      — Langflow drag-and-drop retriever + search components
    langgraph/     - LangGraph stateful retrieval node
    mastra/        — Mastra agent createTool() integration
    pydantic-ai/   - Pydantic AI integration
    moss-cognee-daytona/ — Claude Code + Cognee + Moss on Daytona (shared memory)
apps/
  agora-moss/      — Agora Conversational AI voice agent (MCP server demo)
  agora-custom-llm-moss/ — Agora custom-llm middleware: ambient prepend + in-process tool loop
  docker/          — Dockerized Python + JS SDK examples (ECS/K8s pattern)
  elevenlabs-moss/ — ElevenLabs voice agent with Moss knowledge base
  livekit-moss-vercel/ — LiveKit voice agent + React frontend on Vercel
  moss-bun/        — Production Bun semantic search application
  moss-llamaindex/ — LlamaIndex + Liteparse full-stack PDF search demo
  next-js/         — Next.js 16 browser-based semantic search UI (@moss-dev/moss-web)
  pipecat-moss/    — Pipecat voice agent (three variants below)
    pipecat-quickstart/  — Cloud-deployable quickstart bot
    ollama-local/        — Local LLM + Moss + Pipecat via docker compose
    hume-ollama-local/   — Local LLM + Hume AI TTS + Moss + Pipecat
  ten-moss/        — TEN Framework voice agent with Moss session-scoped grounding
  vapi-moss/       — VAPI Custom Tool webhook server
packages/
  agora-moss/            — Agora Conversational AI MCP server package
  elevenlabs-moss/       — ElevenLabs integration package
  moss-cli/              — CLI for index/document management (no-code workflows)
  moss-data-connector/   — Database source connectors
    moss-connector-mongodb/  — MongoDB connector
    moss-connector-mysql/    — MySQL / MariaDB connector
    moss-connector-sqlite/   — SQLite connector
    moss-connector-supabase/ — Supabase (PostgREST) connector
  moss-md-indexer/       — Markdown docs → Moss index builder
  pipecat-moss/          — Pipecat Python integration package
  strands-agents-moss/   — AWS Strands Agents integration package
  ten-moss/              — TEN Framework Moss session manager (MossSessionManager)
  vapi-moss/             — VAPI Custom Knowledge Base webhook adapter
  n8n-nodes-moss/        — n8n community node for Moss index + query
  vercel-sdk/            — Vercel AI SDK tool wrappers (@moss-tools/vercel-sdk)
  vitepress-plugin-moss/ — VitePress search plugin (on-device fallback after cloud)
  zo-computer/           — Zo computer skill for Moss search
moss-live-labs/          - Experimental zone: prototypes and community demos (APIs can change)
  python/                - Minimal Python quickstart + advanced query example
  typescript/            - Minimal TypeScript quickstart + advanced query example
  examples/
    voice-agent/         - LiveKit + Moss voice assistant
    advanced-voice-agent/ - Persona impersonator built on a PDF knowledge base
    image-search/        - FastAPI + React image search over COCO data
  community-demos/
    voice-agents/
      bharat-benefits/      - Voice RAG over Indian public-benefit schemes (Sarvam STT/TTS)
      shoplabs-voice-agent/ - Pipecat WebRTC ecommerce support agent
```

**`moss-live-labs/` policy:** experimental code. Treat it as staging area for
ideas that may graduate into `sdks/`, `apps/`, `examples/`, or `packages/`, or
that may be deleted. Do not depend on it from stable code paths. When adding
new top-level features, prefer the main directories unless the user explicitly
asks for an experimental landing spot.

## Integrations & Cookbooks

### Framework Cookbooks (`examples/cookbook/`)

| Directory | Framework | What it demonstrates |
| --------- | --------- | -------------------- |
| `autogen/` | Microsoft AutoGen | Multi-agent e-commerce support with intelligent routing; Moss provides sub-10ms context retrieval |
| `crewai/` | CrewAI | Moss as a retrieval tool for CrewAI agents; travel-planning demo with structured JSON data |
| `daytona/` | Daytona | Log ingestion Q&A agent — runs Moss search and code execution inside isolated Daytona sandboxes |
| `dspy/` | DSPy | Notebook-based DSPy + Moss integration |
| `haystack/` | Haystack | `MossDocumentStore` and `MossRetriever` drop-in components for Haystack RAG pipelines |
| `langchain/` | LangChain | `MossRetriever` (BaseRetriever) + `get_moss_tool()` factory; the canonical pattern for new Python cookbook integrations |
| `langflow/` | Langflow | Drag-and-drop `MossRetrieverComponent` and `MossSearchComponent` for Langflow's visual flow builder |
| `mastra/` | Mastra | Moss wrapped as a `createTool()` primitive for Mastra conversational agents (TypeScript) |
| `sim/` | sim.ai | FastAPI webhook server exposing Moss as an external HTTP tool for sim.ai workflows |
| `moss-cognee-daytona/` | Claude Code + Cognee + Daytona | Three Claude Code agents share a persistent Cognee memory graph backed by Moss, each running in an isolated Daytona sandbox |

### Voice Agent Apps (`apps/`)

| Directory | Integration | What it demonstrates |
| --------- | ----------- | -------------------- |
| `agora-moss/` | Agora Conversational AI | Moss as an MCP tool (`search_knowledge_base`) mounted on an Agora voice agent |
| `agora-custom-llm-moss/` | Agora custom-llm | OpenAI-compatible `/chat/completions` with Moss ambient + tool modes; Agora never sees the tool |
| `elevenlabs-moss/` | ElevenLabs | Knowledge-base-backed ElevenLabs Conversational AI bot with live Moss retrieval |
| `livekit-moss-vercel/` | LiveKit + Vercel | LiveKit voice agent with React frontend deployed to Vercel; Moss powers RAG |
| `pipecat-moss/pipecat-quickstart/` | Pipecat Cloud | Minimal Pipecat bot — local dev → Pipecat Cloud deployment |
| `pipecat-moss/ollama-local/` | Pipecat + Ollama | Full-stack local voice AI: Ollama LLM + Moss RAG + Pipecat audio, one `docker compose up` |
| `pipecat-moss/hume-ollama-local/` | Pipecat + Ollama + Hume | Same as above with Hume AI (Octave) expressive TTS |
| `ten-moss/` | TEN Framework | Voice agent that grounds each turn in a Moss session (`MossSessionManager`); graphs `voice_assistant` (ambient, default) and `voice_assistant_tools` (in-process `search_knowledge_base`) |
| `vapi-moss/` | VAPI | Webhook server connecting VAPI Custom Tool calls to Moss search; LLM-directed retrieval |

### Other Apps

| Directory | What it demonstrates |
| --------- | -------------------- |
| `apps/docker/` | Python + JS SDK usage inside Docker containers (ECS / Kubernetes pattern) |
| `apps/moss-bun/` | Production Bun + Moss application |
| `apps/moss-llamaindex/` | Full-stack PDF → LlamaIndex + Liteparse + Moss semantic search demo |
| `apps/next-js/` | Next.js 16 browser-based semantic search UI using `@moss-dev/moss-web`; reference UI for semantic search |

### Reusable Packages (`packages/`)

| Package | PyPI / npm | What it provides |
| ------- | ---------- | ---------------- |
| `agora-moss/` | (internal) | MCP server exposing Moss search to Agora Conversational AI |
| `elevenlabs-moss/` | `elevenlabs-moss` | `MossElevenLabsTool` — drop-in knowledge-base tool for ElevenLabs agents |
| `moss-cli/` | `moss-cli` | CLI: `moss index`, `moss query`, `moss documents` — no-code index management |
| `moss-connector-mongodb/` | `moss-connector-mongodb` | Sync MongoDB collections → Moss index |
| `moss-connector-mysql/` | `moss-connector-mysql` | Sync MySQL / MariaDB tables → Moss index |
| `moss-connector-sqlite/` | `moss-connector-sqlite` | Sync SQLite tables → Moss index |
| `moss-connector-supabase/` | `moss-connector-supabase` | Sync Supabase tables → Moss index via PostgREST |
| `moss-md-indexer/` | `moss-md-indexer` | Parse Markdown docs, chunk, upload to Moss (used by VitePress plugin) |
| `pipecat-moss/` | `pipecat-moss` | `MossPipecatTool` — retrieval tool for Pipecat pipeline services |
| `sim-moss/` | `sim-moss` | `MossSimSearch` — knowledge base adapter for sim.ai workflow HTTP tool nodes |
| `strands-agents-moss/` | `strands-agents-moss` | Moss tool for AWS Strands Agents |
| `ten-moss/` | `ten-moss` | `MossSessionManager` — session-scoped Moss grounding for TEN Framework control extensions |
| `vapi-moss/` | `vapi-moss` | `MossVapiSearch` adapter + HMAC webhook verification for VAPI |
| `n8n-nodes-moss/` | `n8n-nodes-moss` | n8n community node: create index, add/delete docs, list/get/delete indexes, query |
| `vercel-sdk/` | `@moss-tools/vercel-sdk` | Vercel AI SDK 6 `tool()` wrappers: search, create index, manage documents |
| `vitepress-plugin-moss/` | `vitepress-plugin-moss` | VitePress plugin: cloud search on first keystroke, on-device after index download |
| `zo-computer/` | (internal) | Zo computer skill backed by Moss search |

### Standalone Language Examples (`examples/`)

| Directory | Language / Runtime | Key files |
| --------- | ------------------ | --------- |
| `python/` | Python | `comprehensive_sample.py`, `metadata_filtering.py`, `custom_embedding_sample.py` |
| `javascript/` | TypeScript (Node) | `comprehensive_sample.ts`, `cached_load_sample.ts`, `custom_authenticator_sample.ts` |
| `javascript-web/` | TypeScript (browser/Vite) | `comprehensive_sample.ts`, `metadata_filtering_sample.ts` |
| `c/` | C | `example_usage.c`, `metadata_filtering.c`, `session_usage.c` |
| `go/` | Go | `basic/main.go`, `custom-embeddings/main.go` |
| `bun/` | Bun | Bun-native runtime example |
| `python-classification/` | Python | `classify_sample.py` — zero-shot text classification via Moss |
| `voice-agents/airline-pnr/` | Python (LiveKit) | Ambient retrieval: every user turn auto-queries a per-PNR Moss index before the LLM speaks |
| `voice-agents/mortgage-lending/` | Python (LiveKit) | Multi-agent handoff (retrieval-heavy Q&A -> payment flow) with shared session state |

### Moss Live Labs (`moss-live-labs/`)

Experimental staging area. Use it to prototype before promoting into the main
directories. Examples here may move, change shape, or be removed.

| Directory | What it demonstrates |
| --------- | -------------------- |
| `python/` | Minimal `uv`-based Python quickstart + advanced query example |
| `typescript/` | Minimal Node/TypeScript quickstart + advanced query example |
| `examples/voice-agent/` | LiveKit voice assistant over a Moss knowledge base |
| `examples/advanced-voice-agent/` | Persona impersonator (e.g. Harry Potter) built on a PDF index |
| `examples/image-search/` | FastAPI backend + React frontend doing image search over COCO |
| `community-demos/voice-agents/bharat-benefits/` | Voice RAG over Indian public-benefit schemes using Sarvam AI |
| `community-demos/voice-agents/shoplabs-voice-agent/` | Pipecat WebRTC ecommerce support agent |

## Commands

### Python SDK (`sdks/python/sdk/`)

```bash
cd sdks/python/sdk
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

pytest tests/                    # run all tests (E2E tests auto-skip without credentials)
pytest tests/test_client.py      # run a single test file
black src/ tests/                # format
isort src/ tests/                # sort imports
mypy --ignore-missing-imports src/  # type check
ruff check .                     # lint (used in CI)
```

### JavaScript/TypeScript SDK (`sdks/javascript/sdk/`)

```bash
cd sdks/javascript/sdk
npm install
npm run build      # compile TS → dist/
npm test           # vitest run
npm run test:watch # vitest watch mode
npm run lint       # eslint
npm run format     # prettier
```

### Root (examples only — not the SDK)

```bash
npm run type-check  # TS type check across examples/javascript and apps/next-js
npm run lint        # eslint across examples/javascript and apps/next-js
```

### Elixir SDK (`sdks/elixir/sdk/`)

```bash
cd sdks/elixir/sdk
mix deps.get
mix test
```

### React Native / Expo module (`sdks/react-native/`)

```bash
cd sdks/react-native
npm install
npm run build      # tsc → build/
```

iOS links `Moss.xcframework` (downloaded at `pod install` via `ios/scripts/download-moss-xcframework.sh`).
Android is a stub until [#411](https://github.com/usemoss/moss/issues/411). Requires Expo prebuild / a dev client — not Expo Go.

## Architecture: Two-Layer Design

Every SDK has the same two-layer structure:

```
Your Code
   ↓
SDK layer (pure language, open source)
   └─ MossClient — async API surface for index and document operations
   └─ Communicates with Moss Cloud (HTTPS) for mutations and distribution
   ↓
Native bindings (Rust, pre-compiled, published as separate package)
   └─ ManageClient / IndexManager — handles embedding, indexing, local search
   └─ Imported as: moss-core (Python), @moss-dev/moss-core (JS), moss_core (Elixir)
```

The Python `MossClient` in [sdks/python/sdk/src/moss/client/moss_client.py](sdks/python/sdk/src/moss/client/moss_client.py) re-exports types from `moss_core` and wraps `ManageClient` + `IndexManager` from the native layer. The JS SDK follows the same pattern in [sdks/javascript/sdk/src/client/](sdks/javascript/sdk/src/client/).

**Key invariant:** Mutations (create/add/delete) go to the cloud via `ManageClient`. Queries use the local `IndexManager` when an index is loaded; otherwise fall back to the cloud query API.

## Environment Variables

```bash
MOSS_PROJECT_ID=...          # required for all SDK usage
MOSS_PROJECT_KEY=...          # required for all SDK usage
```

Copy `.env.example` to `.env` in the relevant example/app directory.

## SDK Patterns to Follow

When adding examples or cookbook integrations, follow the existing patterns:

- **Python examples**: Import `MossClient, DocumentInfo` from `moss`; use `async/await`; store credentials in env vars via `python-dotenv`
- **JS examples**: Import from `@moss-dev/moss`; ESM only (`"type": "module"`); use `tsx` to run `.ts` files directly
- **Framework cookbooks**: Each lives in `examples/cookbook/<name>/` with its own `pyproject.toml` or `package.json`, a `README.md`, and minimal dependencies on top of the core SDK

## Testing Notes

- E2E and integration tests require `MOSS_PROJECT_ID` and `MOSS_PROJECT_KEY`; they auto-skip gracefully when credentials are absent
- CI runs Python SDK tests across versions 3.10–3.14 in a GitHub Actions matrix using `pytest` directly
- CI lints Python with `ruff` and type-checks with `mypy`; format locally with `black` + `isort`
- JS tests use Vitest; CI runs on Node 20

## CI Workflows

The `.github/workflows/ci.yml` pipeline runs on push to `main` and on PRs:
- `python-lint` — ruff on examples and apps
- `python-sdk-test` — matrix over Python 3.10–3.14
- `javascript-lint` — eslint
- `agora-ten-samples-smoke` — TEN graph contract + `bench/run.py --echo-grounding` + custom-llm mock/doctor (no Agora/LLM keys)
- Separate release workflows publish to PyPI / npm on tagged releases

## Maintaining this file

Keep this file for knowledge useful to almost every future agent session in this project.
Do not repeat what the codebase already shows; point to the authoritative file or command instead.
Prefer rewriting or pruning existing entries over appending new ones.
When updating this file, preserve this bar for all agents and keep entries concise.
