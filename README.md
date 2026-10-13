<!-- markdownlint-disable MD033 MD041 -->

<div align="center">

<img src="https://github.com/user-attachments/assets/25f92357-a670-4564-881d-e336f668c252" alt="Moss — Real-time semantic search for AI agents. Sub-10 ms." width="1200" />

<br /><br />

[![License](https://img.shields.io/badge/License-BSD_2--Clause-orange.svg)](https://opensource.org/licenses/BSD-2-Clause)
[![PyPI](https://img.shields.io/pypi/v/moss?color=deepgreen)](https://pypi.org/project/moss/)
[![PyPI downloads](https://static.pepy.tech/personalized-badge/inferedge-moss-core?period=total&units=international_system&left_color=grey&right_color=blue&left_text=pypi+downloads)](https://pepy.tech/project/inferedge-moss-core)
[![npm](https://img.shields.io/npm/v/@moss-js/moss?color=deepgreen)](https://www.npmjs.com/package/@moss-js/moss)
[![npm downloads](https://img.shields.io/npm/dt/@moss-js/moss?label=npm+downloads&color=blue)](https://www.npmjs.com/package/@moss-js/moss)
[![Discord](https://img.shields.io/discord/1433962929526542346?logo=discord&logoColor=white&label=Discord&color=7B2FBE)](https://moss.link/discord)

[Website](https://moss.dev) · [Docs](https://docs.moss.dev) · [Discord](https://moss.link/discord) · [Blog](https://moss.dev/blog)

</div>

---

Moss is a sub-10 ms semantic search runtime built for Conversational AI agents. Hybrid retrieval (semantic + Keyword Search), built-in embeddings, metadata filtering, and a WebAssembly build that runs in the browser - all from a single SDK that embeds in your application.

No network hop on the hot path. No clusters to tune. Point the SDK at Moss Cloud, load your index, and query it in **under 10 ms**. Python, TypeScript, Elixir, C, Swift, and React Native / Expo.

![Moss Python walkthrough](https://github.com/user-attachments/assets/d826023d-92d6-49ac-8e5e-81cf04d409c5)

## Quickstart

**Before you start:** sign up at [moss.dev](https://moss.dev) for `project_id` and `project_key` - free tier available.

The snippets below need Python 3.10+ or Node.js 20+.

### Python

```bash
pip install moss
```

```python
from moss import MossClient, QueryOptions

client = MossClient("your_project_id", "your_project_key")

# Create an index and add documents
await client.create_index("support-docs", [
    {"id": "1", "text": "Refunds are processed within 3-5 business days."},
    {"id": "2", "text": "You can track your order on the dashboard."},
    {"id": "3", "text": "We offer 24/7 live chat support."},
])

# Load and query — results in <10 ms
await client.load_index("support-docs")
results = await client.query("support-docs", "how long do refunds take?", QueryOptions(top_k=3))

for doc in results.docs:
    print(f"[{doc.score:.3f}] {doc.text}")  # Returned in {results.time_taken_ms}ms
```

### TypeScript

```bash
npm install @moss-js/moss
```

```typescript
import { MossClient } from "@moss-js/moss";

const client = new MossClient("your_project_id", "your_project_key");

// Create an index and add documents
await client.createIndex("support-docs", [
  { id: "1", text: "Refunds are processed within 3-5 business days." },
  { id: "2", text: "You can track your order on the dashboard." },
  { id: "3", text: "We offer 24/7 live chat support." },
]);

// Load and query — results in <10 ms
await client.loadIndex("support-docs");
const results = await client.query("support-docs", "how long do refunds take?", { topK: 3 });

results.docs.forEach((doc) => {
  console.log(`[${doc.score.toFixed(3)}] ${doc.text}`); // Returned in ${results.timeTakenInMs}ms
});
```

## Why Moss?

**Most retrieval stacks call out to a remote vector database. The round trip alone runs 200–500 ms - enough to break a real-time conversation.**

Moss runs search and embedding *inside* your process. There's no network hop on the hot path, so query latency lands in the single digits - fast enough that retrieval disappears from the latency budget. If you're building a voice bot, a copilot, or any agent that talks to humans, that's the difference between a tool that feels alive and one that feels laggy.

### Benchmarks

End-to-end query latency (embedding + search) on 100,000 documents, 750 measured queries, top_k=5. Tested with Macbook pro (M4 Pro, 24GB).

| System | P50 | P95 | P99 | Mean |
|--------|-----|-----|-----|------|
| **Moss** | **3.1 ms** | **4.3 ms** | **5.4 ms** | **3.3 ms** |
| Pinecone | 432.6 ms | 732.1 ms | 934.2 ms | 485.8 ms |
| Qdrant | 597.6 ms | 682.0 ms | 771.4 ms | 596.5 ms |
| ChromaDB | 351.8 ms | 423.5 ms | 538.5 ms | 358.0 ms |

Moss includes embedding in the measurement — competitors use an external embedding service ([modal](https://modal.com/docs/examples/text_embeddings_inference)). Pinecone and Qdrant use cloud search.

> [Reproduce these benchmarks →](./benchmarks/)

Moss isn't a database! It's a **search runtime**. You don't manage clusters, tune HNSW parameters, or worry about sharding. You index documents, load them into the runtime, and query. That's it.

## Features

- **Sub-10 ms semantic search** - single-digit-ms p99 in our [benchmarks](#benchmarks)
- **Hybrid search** - semantic + keyword in a single query
- **Built-in embedding models** - no OpenAI key required (or bring your own)
- **Metadata filtering** - `$eq`, `$and`, `$in`, `$near` operators
- **Runs in the browser too** - separate WebAssembly SDK ([`@moss-dev/moss-web`](https://www.npmjs.com/package/@moss-dev/moss-web)) for client-side semantic search with no server
- **Database connectors** - ingest directly from SQLite, MongoDB, MySQL, and Supabase ([`packages/moss-data-connector/`](packages/moss-data-connector/))
- **CLI** - manage indexes and query from the terminal ([`packages/moss-cli/`](packages/moss-cli/))
- **SDKs** - Python (3.10+), TypeScript / Node.js (20+), Elixir, C ([`libmoss`](https://github.com/usemoss/moss/releases)), Swift (iOS), and React Native / Expo (`@moss-dev/moss-react-native`)
- **Framework integrations** - LangChain, DSPy, LlamaIndex, Pipecat, LiveKit, Vapi, ElevenLabs, Strands Agents

## Examples

This repo contains working examples you can copy straight into your project:

```text
examples/
├── python/                  # Python SDK samples
│   ├── load_and_query_sample.py
│   ├── comprehensive_sample.py
│   ├── custom_embedding_sample.py
│   └── metadata_filtering.py
├── python-classification/   # Classification example
├── javascript/              # TypeScript SDK samples
│   ├── load_and_query_sample.ts
│   ├── comprehensive_sample.ts
│   └── custom_embedding_sample.ts
├── javascript-web/          # Browser / WASM SDK samples
├── c/                       # C SDK samples (libmoss)
├── go/                      # Go SDK samples
├── voice-agents/            # End-to-end voice agents (ambient + multi-agent)
│   ├── airline-pnr/         # Ambient retrieval; per-PNR Moss indexes, swap mid-call
│   └── mortgage-lending/    # Multi-agent flow with shared session state
└── cookbook/                # Framework integrations
    ├── langchain/           # LangChain retriever
    ├── dspy/                # DSPy module
    ├── crewai/              # CrewAI integration
    ├── haystack/            # Haystack retriever
    ├── autogen/             # AutoGen integration
    ├── mastra/              # Mastra retriever
    ├── langflow/            # Langflow drag-and-drop retriever
    ├── pydantic-ai/         # Pydantic AI integration
    ├── daytona/             # Daytona sandbox example
     └── vercel-ai-sdk/       # Vercel AI SDK RAG agent example

apps/
├── next-js/                 # Next.js semantic search UI
├── pipecat-moss/            # Pipecat voice agent with Moss retrieval
├── vapi-moss/               # Vapi voice agent with Moss retrieval
├── elevenlabs-moss/         # ElevenLabs voice agent with Moss retrieval
├── livekit-moss-vercel/     # LiveKit voice agent on Vercel
├── agora-moss/              # Agora Conversational AI MCP server with Moss retrieval
├── agora-custom-llm-moss/   # Agora custom-llm middleware (ambient + in-process tool loop)
├── ten-moss/                # TEN voice agent (ambient default + tool-call graph)
├── moss-llamaindex/         # LlamaIndex RAG backend + frontend
├── moss-bun/                # Bun runtime example
└── docker/                  # Dockerized examples (ECS/K8s pattern)

moss-live-labs/              # Experimental zone: prototypes and community demos
├── python/                  # Minimal Python quickstart + advanced query example
├── typescript/              # Minimal TypeScript quickstart + advanced query example
├── examples/                # Larger experiments (image search, voice agents)
│   ├── voice-agent/         # LiveKit + Moss voice assistant
│   ├── advanced-voice-agent/ # Persona impersonator built on a PDF knowledge base
│   └── image-search/        # FastAPI + React image search over COCO
└── community-demos/         # Community-contributed projects
    └── voice-agents/        # bharat-benefits, shoplabs-voice-agent
```

### Run the Python examples

```bash
cd examples/python
pip install -r requirements.txt
cp ../../.env.example .env   # Add your credentials
python load_and_query_sample.py
```

### Run the TypeScript examples

```bash
cd examples/javascript
npm install
cp ../../.env.example .env   # Add your credentials
npx tsx load_and_query_sample.ts
```

### Run the Next.js app

```bash
cd apps/next-js
npm install
cp ../../.env.example .env   # Add your credentials
npm run dev                  # Open http://localhost:3000
```

### Run the Pipecat voice agent

Sub-10 ms retrieval plugged into [Pipecat's](https://github.com/pipecat-ai/pipecat) real-time voice pipeline — a customer support agent that actually keeps up with conversation.

```bash
cd apps/pipecat-moss/pipecat-quickstart
# See README for setup and Pipecat Cloud deployment
```

### Run the fully-local voice agent (Ollama + Moss + Pipecat)

A privacy-first voice AI stack: **Ollama** for LLM inference, **Moss** for retrieval, **Pipecat** for real-time audio - the LLM and retrieval both run on your machine.

```bash
cd apps/pipecat-moss/ollama-local
docker compose up
```

Full API reference: [docs.moss.dev](https://docs.moss.dev).

## Integrations

| Framework | Status | Example |
|-----------|--------|---------|
| [LangChain](https://github.com/langchain-ai/langchain) | Available | [`examples/cookbook/langchain/`](examples/cookbook/langchain/) |
| [DSPy](https://github.com/stanfordnlp/dspy) | Available | [`examples/cookbook/dspy/`](examples/cookbook/dspy/) |
| [LlamaIndex](https://github.com/run-llama/llama_index) | Available | [`apps/moss-llamaindex/`](apps/moss-llamaindex/) |
| [CrewAI](https://github.com/crewAIInc/crewAI) | Available | [`examples/cookbook/crewai/`](examples/cookbook/crewai/) |
| [AutoGen](https://github.com/microsoft/autogen) | Available | [`examples/cookbook/autogen/`](examples/cookbook/autogen/) |
| [Haystack](https://github.com/deepset-ai/haystack) | Available | [`examples/cookbook/haystack/`](examples/cookbook/haystack/) |
| [Mastra](https://mastra.ai) | Available | [`examples/cookbook/mastra/`](examples/cookbook/mastra/) |
| [Pydantic AI](https://ai.pydantic.dev) | Available | [`examples/cookbook/pydantic-ai/`](examples/cookbook/pydantic-ai/) |
| [Pipecat](https://github.com/pipecat-ai/pipecat) | Available | [`apps/pipecat-moss/`](apps/pipecat-moss/) |
| [LiveKit](https://github.com/livekit/livekit) | Available | [`apps/livekit-moss-vercel/`](apps/livekit-moss-vercel/) |
| [Vapi](https://vapi.ai) | Available | [`apps/vapi-moss/`](apps/vapi-moss/) |
| [ElevenLabs](https://elevenlabs.io) | Available | [`apps/elevenlabs-moss/`](apps/elevenlabs-moss/) |
| [Agora](https://www.agora.io/) | Available | [`apps/agora-moss/`](apps/agora-moss/) (MCP) and [`apps/agora-custom-llm-moss/`](apps/agora-custom-llm-moss/) (custom-llm: ambient + tool-call) |
| [TEN Framework](https://github.com/ten-framework/ten-framework) | Available | [`apps/ten-moss/`](apps/ten-moss/) (ambient + tool-call) |
| [Strands Agents](https://github.com/strands-agents/sdk-python) | Available | [`packages/strands-agents-moss/`](packages/strands-agents-moss/) |
| [Langflow](https://github.com/langflow-ai/langflow) | Available | [`examples/cookbook/langflow/`](examples/cookbook/langflow/) |
| [Next.js](https://nextjs.org) | Available | [`apps/next-js/`](apps/next-js/) |
| [VitePress](https://vitepress.dev) | Available | [`packages/vitepress-plugin-moss/`](packages/vitepress-plugin-moss/) |
| [Vercel AI SDK](https://sdk.vercel.ai) | Available | [`examples/cookbook/vercel-ai-sdk/`](examples/cookbook/vercel-ai-sdk/) |
| [n8n](https://n8n.io) | Available | [`packages/n8n-nodes-moss/`](packages/n8n-nodes-moss/) |

## Architecture

![Moss runtime architecture](https://github.com/user-attachments/assets/7aebbedf-a467-48a4-be38-feddfa4f7d04)

Three parts:

- **Moss Cloud** - handles ingestion, document embedding, storage, and distribution. Point the SDK at it with a project ID and key.
- **Index** - your documents and their vectors, packaged as a single artifact that lives on Moss Cloud.
- **Runtime** - embedded in your application. It pulls indexes over HTTPS, holds them in memory, and serves queries locally.

Once an index is loaded, queries don't leave your process - that's where the sub-10 ms latency comes from. Document changes flow through Moss Cloud and the runtime stays in sync.

### Two ways to run the runtime

- **Server-side** - `moss` (Python) and `@moss-js/moss` (Node.js 20+) embed the runtime in your backend. Use this when your agent runs on a server.
- **Browser** - `@moss-dev/moss-web` is a WebAssembly build that downloads the index and runs queries entirely client-side, no server required. Use this for static sites, browser extensions, and offline-first apps. See [`examples/javascript-web/`](examples/javascript-web/).

Full Python SDK source code is available at [`sdks/python/`](sdks/python/).

## Contributing

<div align="center">
  <img src="https://github.com/user-attachments/assets/80b9dd1c-661c-4201-a1b4-9d191afa8e6b" alt="We welcome contributions!" width="1200" />
</div>

Here's where the community can have the most impact:

- **New SDK bindings** — Kotlin/Android, Rust,… React Native / Expo module shipped under `sdks/react-native/`
- **Framework integrations** — CrewAI, Haystack, AutoGen
- **Reranking support** — plug in cross-encoder rerankers
- **Doc-parsing connectors** — PDF, DOCX, HTML, Markdown ingestion
- **Examples and tutorials** — if you build something with Moss, we'd love to feature it

See our [Contributing Guide](CONTRIBUTING.md) for setup instructions and our [Roadmap](ROADMAP.md) for what's planned.

Check out issues labeled [`good first issue`](https://github.com/usemoss/moss/labels/good%20first%20issue) to get started.

## Contributors

[![Contributors](https://contrib.rocks/image?repo=usemoss/moss)](https://github.com/usemoss/moss/graphs/contributors)

## Community

- [Discord](https://moss.link/discord) — ask questions, share what you're building
- [GitHub Issues](https://github.com/usemoss/moss/issues) — bug reports and feature requests
- [Twitter](https://x.com/usemoss) — announcements and updates

## License

[BSD 2-Clause License](LICENSE) — the SDKs, examples, and integrations in this repo are fully open source.

---

<div align="center">
  <sub>Built by the team at <a href="https://moss.dev">Moss</a> · Backed by <a href="https://www.ycombinator.com">Y Combinator</a></sub>
</div>
