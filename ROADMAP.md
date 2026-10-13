# Moss Roadmap

This is a living document. We update it as priorities shift based on community feedback and production learnings. If something here excites you, open an issue or PR — we move fast on contributions.

## Shipped

### SDKs & Runtimes

- [x] Python SDK (`moss`) — async-first, type-safe
- [x] TypeScript SDK (`@moss-dev/moss`) — full feature parity with Python
- [x] Elixir SDK (`moss`) — Hex package for Phoenix / LiveView apps
- [x] Go SDK — bindings-backed manage + local query via `libmoss` (`sdks/go/`)
- [x] C bindings — example usage, metadata filtering, session management
- [x] Bun runtime support — native Bun example application
- [x] WebAssembly runtime — client-side semantic search in the browser, no server required

### Search & Indexing

- [x] Built-in embedding models (`moss-minilm`)
- [x] Custom embedding support (bring your own OpenAI, Cohere, etc.)
- [x] **Hybrid search** — combine semantic search with BM25 keyword matching
- [x] Metadata filtering (`$eq`, `$and`, `$in`, `$near`)
- [x] Document management (add, upsert, get, delete)
- [x] Text classification — zero-shot classification via Moss similarity (`python-classification`)
- [x] **Benchmarks directory** — reproducible latency/throughput scripts comparing Moss vs Pinecone, Qdrant, and Chroma on standardized datasets

### Framework Integrations

- [x] LangChain integration — `MossRetriever` (BaseRetriever) + `get_moss_tool()` factory; canonical Python integration pattern
- [x] DSPy integration — notebook-based DSPy + Moss retrieval
- [x] Haystack integration — `MossDocumentStore` and `MossRetriever` drop-in components for RAG pipelines
- [x] CrewAI integration — Moss as a retrieval tool for CrewAI agents; travel-planning demo
- [x] AutoGen integration — multi-agent e-commerce support with Moss sub-10ms context retrieval
- [x] LlamaIndex integration — full-stack PDF processing with Liteparse + Moss vector search
- [x] Mastra integration — Moss wrapped as a `createTool()` primitive for Mastra agents (TypeScript)
- [x] AWS Strands Agents integration — `strands-agents-moss` package for Strands Agents workflows
- [x] Daytona sandbox integration — log ingestion Q&A agent; code execution in isolated Daytona sandboxes
- [x] Cognee + Daytona integration — multi-agent shared memory graph (Cognee + Moss) across isolated Daytona sandboxes
- [x] LangGraph integration — retrieval node for stateful multi-agent workflows
- [x] Langflow integration — drag-and-drop `MossRetrieverComponent` and `MossSearchComponent`
- [x] n8n community node — create index, manage documents, and query from n8n workflows

### Voice AI

- [x] Pipecat voice agent integration — `pipecat-moss` package + quickstart bot
- [x] **Ollama + Moss + Pipecat reference architecture** — fully local LLM voice agent; single `docker compose up`
- [x] Hume AI + Ollama + Pipecat — local voice agent with Hume AI (Octave) expressive TTS
- [x] LiveKit voice agent integration — LiveKit agent + React frontend deployed to Vercel
- [x] ElevenLabs integration — `elevenlabs-moss` package; knowledge-base-backed Conversational AI bot
- [x] Agora Conversational AI integration — `agora-moss` MCP server; `search_knowledge_base` tool for Agora voice agents
- [x] VAPI integration — `vapi-moss` webhook adapter with HMAC verification; LLM-directed retrieval via Custom Tool
- [x] TEN Framework integration — `MossSessionManager` + voice-assistant app with session-scoped grounding

### Developer Tools & Packages

- [x] **Moss CLI** — `moss index`, `moss query`, `moss documents` — manage indexes and run queries without writing code
- [x] **MCP server** — expose Moss as a Model Context Protocol server so any MCP-compatible AI tool (Claude, Cursor, Windsurf) can do semantic search
- [x] **Vercel AI SDK integration** — `@moss-tools/vercel-sdk` tool wrappers: search, create index, manage documents
- [x] VitePress search plugin — cloud search on first keystroke, on-device after index download; live demo on Vercel
- [x] Markdown documentation indexer — `moss-md-indexer` parses and chunks Markdown docs for upload to Moss
- [x] Zo computer skill — Moss semantic search skill for the Zo computer platform

### Data Connectors

- [x] MongoDB connector — sync MongoDB collections → Moss index
- [x] MySQL / MariaDB connector — sync tables → Moss index via PyMySQL
- [x] SQLite connector — sync SQLite tables → Moss index
- [x] Supabase connector — sync Supabase tables → Moss index via PostgREST

### Apps & Deployment

- [x] Next.js example app — Next.js 16 browser-based semantic search UI (`@moss-dev/moss-web`)
- [x] Docker deployment examples (ECS / Kubernetes patterns) — Python + JS SDK in containers

---

## In Progress

- [ ] **Firecrawl cookbook** — crawl a URL with Firecrawl and index the content directly into Moss; turnkey web knowledge base for agents
- [ ] **Unstructured cookbook** — ingest PDF, DOCX, and HTML files via Unstructured and load into Moss; doc-parsing connector example
- [ ] **Google ADK integration** — Moss as a retrieval tool for Google's Agent Development Kit
- [ ] **Smolagents integration** — lightweight retrieval tool for Hugging Face's agent framework

---

## Next Up — Community Contributions Welcome

These are well-scoped and ready for contributors. Each one has (or will have) a corresponding GitHub issue with detailed instructions.

### New SDK Bindings

- [ ] **Swift bindings** — for iOS/macOS apps with on-device retrieval ([`good first issue`](https://github.com/usemoss/moss/labels/good%20first%20issue))
- [ ] **Rust bindings** — for performance-critical pipelines ([`good first issue`](https://github.com/usemoss/moss/labels/good%20first%20issue))
- [ ] **Kotlin bindings** — for Android apps and Spring Boot backend services ([`good first issue`](https://github.com/usemoss/moss/labels/good%20first%20issue))
- [x] **React Native / Expo module** — iOS via `Moss.xcframework` + Expo config plugin (`sdks/react-native/`, `@moss-dev/moss-react-native`); Android pending [#411](https://github.com/usemoss/moss/issues/411) ([#432](https://github.com/usemoss/moss/issues/432))

### Voice AI Ecosystem

- [ ] **Daily.co integration** — real-time audio pipeline with semantic context injection
- [ ] **Twilio integration** — retrieval for phone-based AI agents (IVR, call center bots)

### Developer Tools

- [ ] **VS Code extension** — semantic search over your codebase directly from the editor sidebar

### Search Quality

- [ ] **Reranking support** — plug in cross-encoder rerankers as a post-retrieval step
- [ ] **Multi-vector retrieval** — support ColBERT-style late interaction models

### Data Ingestion

- [ ] **Chunking strategies** — built-in text splitters (sentence, paragraph, recursive, semantic)

---

## Future

These are bigger bets we're exploring. They're directional, not committed — community input will shape what gets built.

### Local-First AI Stack

- [ ] **vLLM-based local inference + local search** — a fully local pipeline: your model, your embeddings, your search, your hardware. No API calls. This is a natural fit for the privacy-first voice AI use case and can meaningfully cut latency for on-premise deployments.

### Evaluation & Quality

- [ ] **LLM-as-a-judge evaluation framework** — automated retrieval quality scoring using LLM judges. We want to lay the foundation and let the community decide the direction — what metrics matter, which judges to support, how to benchmark fairly.
- [ ] **Retrieval quality dashboard** — visualize query performance, relevance scores, and failure modes over time

### Browser & Edge

- [ ] **Edge runtime support** — run Moss in Cloudflare Workers, Deno Deploy, and Vercel Edge Functions

### Advanced Retrieval

- [ ] **Query expansion** — LLM-powered query rewriting to improve recall on short or ambiguous queries
- [ ] **Sparse-dense fusion (SPLADE)** — learned sparse retrieval to complement BM25 hybrid, improving precision on rare terms
- [ ] **Contextual retrieval** — pre-chunking contextualization to make every chunk self-contained and more retrievable

### More Data Connectors

Connect knowledge sources to Moss without writing custom ETL.

- [ ] **GitHub connector** — index code, issues, PRs, and docs from repositories
- [ ] **Notion connector** — sync and index Notion workspace pages
- [ ] **Confluence connector** — enterprise knowledge base indexing
- [ ] **S3/GCS sync** — auto-index documents from cloud storage buckets on upload

---

## How to Contribute

1. **Pick something from "Next Up"** — these are ready for PRs
2. **Check the [issues](https://github.com/usemoss/moss/issues)** — look for `good first issue` and `help wanted` labels
3. **Propose something new** — open an issue describing what you want to build. We're open to ideas that aren't on this list.
4. **Read the [Contributing Guide](CONTRIBUTING.md)** — fork, branch from `main`, PR

If you're unsure where to start, drop a message in [Discord](https://discord.gg/eMXExuafBR) and we'll point you in the right direction.
