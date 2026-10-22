# J.A.R.V.I.S.

Jarvis is a text-first personal AI assistant with a compact Iron Man-inspired HUD and a persistent “second brain.” With only Moss and OpenRouter configured, it immediately accepts typed commands, recalls relevant short- and long-term context, generates an answer, and stores useful facts and tasks. Picovoice wake-word/STT and ElevenLabs speech are optional upgrades that activate automatically when their keys are available.

The repository can run as:

- a browser development application at `http://localhost:3000`; or
- a frameless, transparent, always-on-top Tauri desktop overlay with its own bundled Node runtime.

## Current implementation status

- Text prompting works with Moss Project ID/Key plus one OpenRouter API key.
- Any OpenRouter text/chat model slug can be selected; GPT-4.1 Mini is only the default value.
- Every successful turn is written to private local storage before any Moss Cloud request.
- Moss local retrieval remains operational when cloud index, ingest, or monthly usage quota is unavailable.
- The compact **SECOND BRAIN** HUD card opens a full-screen cognitive archive with search, recency ranking, memory inspection, semantic neighbors, an interactive connection graph, direct memory writes, and multi-source ingestion.
- Notes, Markdown, plain text, PDF, Word, HTML, CSV/log files, ChatGPT/Claude/generic AI chat-export JSON, public articles, and public YouTube transcripts can be brought into the same searchable memory space.
- The macOS build is self-contained: `Jarvis.app` carries Next.js standalone output, pnpm dependencies, Moss's native Apple Silicon module, and Node itself.
- Browser and desktop WebView credentials are separate because each has its own `localStorage`.

## Feature status

| Capability | Implementation |
| --- | --- |
| Text conversation | Core mode; requires only Moss and OpenRouter |
| Wake word | Optional local Picovoice Porcupine Web model using the built-in `Jarvis` keyword |
| Speech-to-text | Optional local Picovoice Cheetah streaming transcription with endpoint detection |
| Conversational reasoning | OpenRouter Chat Completions with a configurable model |
| Live conversational memory | In-process recent-turn buffer plus a Moss local `SessionIndex` |
| Persistent second brain | Private local JSON + Moss local index, with automatic Moss Cloud synchronization when quota permits |
| Full-screen memory workspace | Clickable archive with search, filters, full text, related memories, stats, ingestion, direct remember, delete, and an interactive graph |
| Knowledge ingestion | Heading-aware deterministic chunking for text/documents/chat exports plus public article and YouTube transcript capture |
| Task capture | OpenRouter returns structured tasks; Jarvis stores them as Moss documents with metadata |
| Morning briefing | Reads open task documents from Moss and asks OpenRouter to produce a concise spoken briefing |
| Speech output | Optional ElevenLabs text-to-speech; OS speech synthesis is used only if an enabled ElevenLabs request/playback fails |
| Desktop shell | Tauri 2 frameless, transparent, resizable, always-on-top window |
| Text command channel | HUD command bar performs local recall → OpenRouter → local persistence → optional Moss Cloud sync |
| Runtime configuration | Masked in-app credential form plus `.env.local` support |

## What each component contributes

### Moss: memory, retrieval, and synchronization

Moss is the foundation of Jarvis's second brain. It is not the language model and does not generate Jarvis's responses. Moss is responsible for turning memory documents into a locally searchable index and making those documents available across future sessions.

In this project Moss contributes:

1. **Local embeddings.** Jarvis produces deterministic 384-dimensional embeddings on-device and supplies them to Moss as BYO/custom embeddings. This avoids a separate embedding API and continues working when hosted Moss embedding/voice quota is exhausted.
2. **Short-term working memory.** The current conversation is held in a bounded in-process recent-turn buffer.
3. **Long-term semantic memory.** A Moss local `SessionIndex` searches the stable second-brain documents. The same documents are saved first to `.jarvis-data/second-brain.json`, so a server restart cannot erase successful turns.
4. **Retrieval before every answer.** Jarvis searches recent working turns and the Moss local long-term index. Up to five results from each source are included in the OpenRouter prompt.
5. **Local query execution.** The custom-embedding `SessionIndex` is queried in-process. When cloud sync is online, Jarvis can additionally query the loaded `jarvis-second-brain` cloud snapshot and merge those results.
6. **Metadata-bearing documents.** Facts, conversation records, system records, and tasks are differentiated using document metadata. Task metadata makes the memory filterable by fields such as type, status, due date, recurrence, and priority.
7. **Cloud persistence.** When the project has available Moss quota, Jarvis creates or updates the single `jarvis-second-brain` cloud index through `createIndex()` / `addDocs()` and refreshes it with `loadIndex()`.
8. **Fail-safe persistence.** If Moss Cloud returns a quota or network error, the HUD reports `MOSS LOCAL`; the turn is still stored on disk and indexed by the local Moss engine. A later initialization retries cloud synchronization.
9. **Retrieval telemetry.** Query duration and retrieved-document counts are exposed in the HUD as Moss latency and memory recall metrics.
10. **Semantic connection graph.** Jarvis compares source-level custom embeddings, keeps each source's strongest neighbors, and renders the resulting weighted graph as an interactive canvas.
11. **Direct episodic memory.** The full-screen archive can write a timestamped fact, decision, preference, or event straight to local storage and the Moss index without spending an LLM call.

### Full-screen Second Brain workspace

Click the **SECOND BRAIN** card on the right side of the main HUD. The archive takes over the Jarvis window and provides four workspaces:

| Workspace | What it does |
| --- | --- |
| **Memories** | Lists durable chunks, performs semantic search, filters by memory type, optionally re-ranks dated content for recency, shows complete stored text, traverses semantic neighbors, opens original URLs, and deletes individual vectors |
| **Graph** | Builds a source-level knowledge graph from local embeddings; drag to pan, scroll to zoom, and click a node to open all chunks from that source |
| **Ingest** | Imports supported files and public links, sanitizes prompt-role markers, extracts readable text, splits on Markdown headings, creates deterministic chunk IDs, embeds locally, and then attempts Moss Cloud synchronization |
| **Remember** | Writes a titled/tagged episodic memory directly to the canonical local store and Moss local index without calling OpenRouter |

The integration adapts the architecture and ingestion ideas from [Naut1cal5/moss-brain](https://github.com/Naut1cal5/moss-brain), an MIT-licensed project by Aarush Nigam. Jarvis implements those ideas natively in TypeScript so the packaged Tauri app does not require Python, `pip`, a separate MCP server, or an Obsidian installation. See [`THIRD_PARTY_NOTICES.md`](./THIRD_PARTY_NOTICES.md).

#### Ingestion behavior

- Files: `.md`, `.markdown`, `.txt`, `.rst`, `.org`, `.csv`, `.log`, `.html`, `.htm`, `.pdf`, `.docx`, and AI chat-export `.json`.
- Links: public HTTP(S) articles and public YouTube videos with an available English transcript.
- Safety: localhost and private-network link ingestion is rejected; script/navigation boilerplate is removed from HTML; known model-role control markers are neutralized before indexing.
- Chunking: Markdown headings define semantic sections, large sections are capped at approximately 3,600 characters, and IDs derive from `source + section + part`, so re-importing the same source updates rather than duplicates those chunks.
- Parsing: ChatGPT, Claude, and vendor-neutral `role`/`content`-shaped exports are mapped into question/answer archives. PDF extraction uses `pdf-parse`; Word extraction uses `mammoth`.
- Persistence: the canonical JSON archive is updated first, the local Moss `SessionIndex` second, and the optional private Moss Cloud index last.

The upstream CLI/MCP-only capabilities that do not map directly to the current desktop UI—continuous filesystem watching, writing `[[wikilinks]]` into an Obsidian vault, and serving memory to other applications over MCP—remain outside Jarvis for now.

This uses Moss's documented custom-embedding, local-session, index mutation, `loadIndex()`, and query APIs. See the [Moss client reference](https://docs.moss.dev/docs/reference/js/classes/MossClient) and [storage/persistence guide](https://docs.moss.dev/docs/integrate/storage-persistence).

### What Moss does not do here

Clear ownership matters:

- Moss does **not** decide what Jarvis says; OpenRouter does.
- Moss does **not** extract facts or interpret “remind me”; the OpenRouter response provides structured facts and tasks.
- Moss does **not** listen to the microphone; Picovoice does.
- Moss does **not** synthesize audio; ElevenLabs does.
- Moss is not currently used as a clock-based notification scheduler. It stores task state and makes it retrievable for briefings.
- Open task selection currently filters the session's durable local document collection in the Node process. Task documents remain compatible with Moss metadata filters, but the briefing path does not yet issue a filtered Moss query.

### OpenRouter: model-agnostic reasoning and structured extraction

All conversational model calls go through OpenRouter. The model receives:

- the current user command;
- relevant recent working-memory documents;
- relevant documents retrieved from the Moss local/cloud second-brain index; and
- instructions to return strict JSON containing a spoken response, durable facts, and structured tasks.

The expected response shape is:

```json
{
  "response": "Certainly. I have added that to your task matrix.",
  "facts": ["The user prefers morning meetings."],
  "tasks": [
    {
      "title": "Send the project update",
      "due": "2026-07-12T09:00:00+05:30",
      "recurrence": "none",
      "priority": "high"
    }
  ]
}
```

Jarvis validates this structure before storing it. The model is configured with `OPENROUTER_MODEL`, so it can be replaced without changing code. The in-app model field is free-form and also loads suggestions from OpenRouter's model catalog. Enter the exact OpenRouter model ID, such as an `anthropic/...`, `google/...`, `meta-llama/...`, or `openai/...` slug. The OpenRouter API key belongs to the OpenRouter account, not to GPT-4.1 Mini.

Jarvis deliberately does not require the provider-specific `response_format` option. This keeps ordinary text chat compatible with models that do not advertise native JSON or structured-output support. Models that follow the JSON instruction provide full task and durable-fact extraction; if a model answers with plain prose, Jarvis still displays the answer but skips structured fact/task extraction for that turn.

### Picovoice: local audio intelligence

Two Picovoice Web SDKs form the input side of the voice loop:

- **Porcupine** continuously processes microphone frames locally and invokes Jarvis when it detects the built-in `Jarvis` keyword.
- **Cheetah** takes over after the wake word, streams partial transcription into the HUD, and marks the utterance complete after approximately 1.15 seconds of endpoint silence.

The included files are:

- `public/models/porcupine_params.pv`
- `public/models/cheetah_params.pv`

The first initialization is slower because the 34 MB Cheetah model must be loaded and cached by the browser. Speech processing runs locally after the model is loaded, but Picovoice still requires an AccessKey for SDK authorization.

### ElevenLabs: spoken output

`POST /api/jarvis/tts` sends the final response to ElevenLabs and returns MP3 audio to the HUD. The default configuration uses:

- voice ID `JBFqnCBsd6RMkjVDRZzb` (George); and
- model `eleven_multilingual_v2`.

When ElevenLabs is not configured, Jarvis stays in text-only output mode. If ElevenLabs is configured but its request or playback fails, the UI attempts to use the operating system's `en-GB` speech-synthesis voice. That fallback is useful for recovery but is not equivalent to ElevenLabs quality.

### Next.js: application and orchestration layer

Next.js provides both the React HUD and the Node.js API routes. The server layer owns the in-memory Jarvis session registry, calls Moss, OpenRouter, and ElevenLabs, and returns sanitized state to the client. Credentials loaded from `.env.local` remain server-side; credentials entered through the optional in-app form are explicitly sent from browser storage to the local server at runtime.

### Tauri: desktop window

Tauri wraps the Next.js application in a native macOS window configured as:

- frameless;
- transparent;
- resizable;
- always on top; and
- draggable through the custom HUD title bar.

The production build bundles both Next.js standalone output and the build machine's Node executable as Tauri resources. The Finder-launched application therefore starts its own loopback server without depending on shell PATH configuration or a separate system Node installation.

## Minimum text-only mode

The minimum working configuration is:

```env
MOSS_PROJECT_ID=your_project_id
MOSS_PROJECT_KEY=your_project_key
OPENROUTER_API_KEY=your_openrouter_api_key
```

With those three values, Jarvis can:

- accept typed prompts through the HUD;
- query short- and long-term Moss memory;
- answer through OpenRouter;
- extract and persist facts and tasks;
- generate text morning briefings; and
- retain the entire visual HUD and reactor state system.

It will not request microphone access, initialize Picovoice, call ElevenLabs, or attempt speech playback. Clicking the central reactor focuses the text-command field instead.

## End-to-end voice turn

```text
1. Microphone frames
        │
        ▼
2. Porcupine detects “Jarvis” locally
        │
        ▼
3. Cheetah streams local transcription
        │
        ▼
4. POST /api/jarvis { action: "turn" }
        │
        ├── add user turn to recent working memory
        │
        ├── query recent working memory (top 5)
        │
        └── query Moss local second-brain index (top 5)
                    │
                    ▼
5. Combined retrieved context → OpenRouter
                    │
                    ▼
6. JSON response: spoken answer + facts + tasks
        │
        ├── add assistant turn to recent working memory
        │
        ├── write conversation record to private local storage
        │
        ├── add extracted fact documents
        │
        ├── add structured task documents
        │
        ├── update Moss local SessionIndex
        │
        └── addDocs() + loadIndex() for Moss Cloud when quota is available
                    │
                    ▼
7. Answer → ElevenLabs → MP3 → speaker
```

The text command bar begins at step 4 and otherwise uses the identical pipeline.

## Moss memory model in detail

The implementation lives in [`lib/jarvis-store.ts`](./lib/jarvis-store.ts).

### Working memory: short-term context

Each user and assistant turn is stored as a document like:

```json
{
  "id": "turn-...",
  "text": "User: Remind me to send the update tomorrow morning.",
  "metadata": {
    "type": "conversation-turn",
    "role": "user",
    "createdAt": "2026-07-11T02:00:00.000Z"
  }
}
```

Working memory keeps the latest 40 raw user/assistant turns in the active Node process. Every completed exchange is also written as a durable `conversation-summary`, so it survives even though the raw working buffer is intentionally short-lived.

### Long-term memory: local first, Moss synchronized

```ts
const localIndex = await client.session("jarvis-local-second-brain", "custom");
await localIndex.addDocs(documentsWithLocalEmbeddings);
await localIndex.saveToDisk("second-brain.moss");
```

The canonical local document store is `.jarvis-data/second-brain.json` in development. The packaged desktop app sets `JARVIS_DATA_DIR` to the macOS application-data directory, so memory is writable outside the read-only app bundle. Files are created with owner-only permissions.

After each successful model turn, Jarvis adds:

- one complete user/assistant conversation record;
- zero or more durable fact documents; and
- zero or more structured task documents.

Jarvis saves the local document file before attempting network synchronization. If Moss Cloud is available, it then uses:

```ts
await client.addDocs("jarvis-second-brain", documentsWithLocalEmbeddings);
await client.loadIndex("jarvis-second-brain");
```

If the cloud index does not exist, Jarvis creates it once with `createIndex(..., { modelId: "custom" })`. If cloud quota is exhausted, local persistence and Moss local retrieval remain active and the next initialization retries the sync.

### Parallel retrieval

Before OpenRouter generates an answer, Jarvis performs:

```ts
const working = searchRecentTurns(userText, 5);
const longTerm = await session.localIndex.query(userText, {
  topK: 5,
  embedding: localEmbedding(userText),
});
```

Results carry a `working` or `long-term` source label so the prompt preserves the memory boundary. When Moss Cloud is synchronized, Jarvis can also query the loaded cloud snapshot and merge those results.

### Memory document types

| `metadata.type` | Purpose | Typical lifetime |
| --- | --- | --- |
| `system` | Second-brain bootstrap and system records | Permanent |
| `conversation-turn` | Raw user or assistant turn in working memory | Active process/session |
| `conversation-summary` | Durable record of a completed exchange | Permanent |
| `fact` | Extracted user preference or durable personal fact | Permanent |
| `task` | Action item used by the task matrix and morning briefing | Until its status changes |

Current task documents use:

```json
{
  "id": "task-...",
  "text": "Send the project update",
  "metadata": {
    "type": "task",
    "status": "open",
    "due": "2026-07-12T09:00:00+05:30",
    "recurrence": "none",
    "priority": "high",
    "createdAt": "2026-07-11T02:00:00.000Z"
  }
}
```

Moss evaluates metadata filtering on a locally loaded index. This schema is ready for queries such as open tasks, overdue tasks, or recurring tasks using Moss filters. See [Moss metadata filtering](https://docs.moss.dev/docs/integrate/metadata-filtering).

## Morning briefing

The morning briefing path is deliberately separate from a normal turn:

1. `openTasks()` reads documents from the durable local second-brain collection.
2. Jarvis keeps documents with `metadata.type === "task"` and `metadata.status === "open"`.
3. OpenRouter receives the structured open-task list and current timestamp.
4. The resulting briefing prioritizes overdue, due-today, and high-priority items.
5. ElevenLabs speaks the briefing when configured; otherwise it remains text in the HUD.

When no task documents are open, Jarvis returns a deterministic no-tasks briefing without spending an OpenRouter request.

## Project structure

```text
app/
├── page.tsx                    HUD, state machine, settings, transcript, audio playback
├── second-brain.tsx            Full-screen archive, ingestion/remember UI, semantic graph canvas
├── globals.css                 HUD visuals and state-specific reactor animations
└── api/jarvis/
    ├── route.ts                Init, chat, briefing, memory browser/search/graph actions
    ├── brain/ingest/route.ts   Multipart file/link extraction and durable ingestion
    └── tts/route.ts            ElevenLabs text-to-speech proxy

lib/
├── brain-ingest.ts             Sanitization, parsers, URL capture, deterministic chunking
├── jarvis-store.ts             Local-first store, custom embeddings, Moss sync/retrieval, tasks
├── runtime-config.ts           Runtime provider configuration and environment fallback
└── voice-engine.ts             Porcupine/Cheetah worker lifecycle and microphone routing

scripts/
└── prepare-desktop.mjs         Materializes pnpm packages and embeds the active Node executable

public/models/
├── porcupine_params.pv         Local wake-word parameters
└── cheetah_params.pv           Local streaming STT parameters

src-tauri/
├── icons/                      Jarvis SVG/PNG application icon
├── src/lib.rs                  Bundled server process, NODE_PATH, data directory, and HUD window
├── tauri.conf.json             Tauri build, bundle, security, and resource configuration
├── capabilities/default.json   Window permissions
└── Cargo.lock                  Reproducible Rust dependency lockfile
```

## Requirements

- Node.js 20 or newer
- pnpm (used by the development and Tauri build scripts)
- Rust stable
- [Tauri 2 platform prerequisites](https://v2.tauri.app/start/prerequisites/)
- Moss project credentials
- OpenRouter API key with access to the configured model
- Optional: ElevenLabs API key with text-to-speech permission
- Optional: Picovoice AccessKey and microphone permission
- Internet access for Moss synchronization and OpenRouter generation; ElevenLabs also requires it when enabled

Wake-word detection and speech-to-text run locally after the Picovoice models have initialized. The Moss local second brain and disk persistence work without cloud access; creating/updating the optional cloud index requires network access and available Moss project quota.

## Installation

```bash
git clone <repository-url>
cd <repository-directory>
pnpm install
cp .env.local.example .env.local
```

### Credential option A: `.env.local`

For text-only mode, fill in:

```env
MOSS_PROJECT_ID=your_project_id
MOSS_PROJECT_KEY=your_project_key
MOSS_LONG_TERM_INDEX=jarvis-second-brain

OPENROUTER_API_KEY=your_openrouter_api_key
OPENROUTER_MODEL=openai/gpt-4.1-mini
```

`openai/gpt-4.1-mini` is only the example default. Replace it with any text/chat model ID currently available to your OpenRouter account. You can also change the model at runtime in **CONFIG → OPENROUTER → MODEL SLUG**; no rebuild is required.

Optionally add spoken input and output:

```env

ELEVENLABS_API_KEY=your_elevenlabs_api_key
ELEVENLABS_VOICE_ID=JBFqnCBsd6RMkjVDRZzb
ELEVENLABS_MODEL_ID=eleven_multilingual_v2

NEXT_PUBLIC_PICOVOICE_ACCESS_KEY=your_picovoice_access_key

JARVIS_TIMEZONE=Asia/Kolkata
APP_URL=http://localhost:3000
```

Restart the development server after changing `.env.local`.

### Credential option B: in-app configuration

Open **CONFIG** or the top-right settings control. Enter the required Moss and OpenRouter credentials, choose or type an OpenRouter model slug, then select **SAVE & INITIALIZE TEXT CORE**. The model suggestions are loaded from OpenRouter, but the field remains free-form so a newly released model can be used immediately. The ElevenLabs and Picovoice sections are explicitly marked optional and may be left blank.

Runtime configuration behavior:

- values are stored in the current browser/WebView's `localStorage`;
- values are sent to the local `/api/jarvis` route and retained in server memory;
- non-empty runtime values override `.env.local` values for the current process;
- a blank runtime field leaves an existing server environment value unchanged;
- local memory and Moss synchronization are initialized immediately, without restarting Next.js; and
- credentials must be re-injected from browser storage after the Node process restarts.

Chrome/Safari development storage and the Tauri WebView storage are intentionally separate. Enter the credentials once in the native CONFIG panel after first launching `Jarvis.app`.

The masked inputs prevent shoulder surfing, but `localStorage` is not encrypted secret storage. For stricter server-side secrecy, use `.env.local`. `NEXT_PUBLIC_PICOVOICE_ACCESS_KEY` is necessarily available to the browser because the Picovoice Web SDK runs client-side.

## Running Jarvis

### Browser development mode

```bash
pnpm dev
```

Open `http://localhost:3000`.

### Tauri desktop mode

```bash
rustup default stable
pnpm desktop
```

The first Rust/Tauri compilation can take several minutes and requires at least 5 GB of free disk space. Development mode launches the frameless, always-on-top native window against the local Next.js server.

### Optional voice activation

1. Add both the optional ElevenLabs and Picovoice credentials.
2. Save the configuration.
3. Click **ARM VOICE** or the central reactor.
4. Allow microphone access.
5. Wait for `WAKE LINK ARMED`.
6. Say “Jarvis,” speak a command, and pause naturally.

Without optional voice credentials, type into the command bar and press **TRANSMIT**. Responses appear immediately as HUD telemetry.

## Production build

```bash
pnpm desktop:build
```

This command:

1. creates Next.js standalone output;
2. copies static and public assets into the standalone server;
3. dereferences pnpm links into `.desktop-server` so packages resolve inside an app bundle;
4. materializes `@moss-dev/moss-core` and its architecture-specific native package;
5. copies the active Node executable into Tauri resources;
6. compiles the Rust launcher; and
7. creates `src-tauri/target/release/bundle/macos/Jarvis.app`.

`scripts/prepare-desktop.mjs` copies the active Node executable into the app bundle, and the Rust launcher executes that exact bundled path.

Install the generated bundle once:

```bash
ditto src-tauri/target/release/bundle/macos/Jarvis.app /Applications/Jarvis.app
pnpm desktop:launch
```

`desktop:launch` opens `/Applications/Jarvis.app`, so it requires the installation copy step first.

The native launcher passes the macOS application-data directory to the server as `JARVIS_DATA_DIR`, so second-brain files survive app upgrades and are never written inside the application bundle.

The bundled Node executable is architecture-specific. Build the macOS app on the same architecture you intend to distribute, or add separate universal/Intel packaging if needed.

### Launching and stopping the installed app

```bash
open /Applications/Jarvis.app
```

Quit from the app/window normally. The Rust launcher owns the bundled `next-server` child and terminates it when Jarvis exits. Jarvis listens only on `127.0.0.1:3000`.

## API contract

All Jarvis orchestration uses `POST /api/jarvis`.

| Action | Required fields | Result |
| --- | --- | --- |
| `status` | optional `config` | Boolean provider-link status; never returns secret values |
| `models` | optional `config` | OpenRouter text-model catalog for the free-form model suggestions |
| `init` | optional `config` | Opens local memory, initializes Moss local retrieval, attempts cloud sync, and returns truthful memory status |
| `turn` | `sessionId`, `text` | Returns answer, extracted facts/tasks, recall count, local document count, and Moss sync status |
| `chat` | `text` | Emergency direct OpenRouter turn when no memory session can be recovered |
| `briefing` | `sessionId` | Returns the spoken briefing and current open tasks |
| `memory-search` | `sessionId`, `text` | Diagnostic retrieval against working and long-term memory |
| `brain-list` / `brain-search` | `sessionId`; optional `text`, `type`, `source`, `recent`, `limit` | Full-screen archive listing or semantic search |
| `brain-related` | `sessionId`, `memoryId` | Semantically adjacent source memories |
| `brain-remember` | `sessionId`, `text`; optional `title`, `tags` | Direct durable episodic-memory write without an LLM call |
| `brain-stats` | `sessionId` | Counts, storage mode/path, and graph connection total |
| `brain-graph` | `sessionId` | Source nodes and weighted embedding-similarity edges |
| `brain-delete` | `sessionId`, `memoryId` | Deletes one local vector and mirrors deletion to Moss when available |

`POST /api/jarvis/tts` accepts `{ "text": "..." }` and returns `audio/mpeg` when ElevenLabs succeeds.

`POST /api/jarvis/brain/ingest` accepts multipart form data with `sessionId`, zero or more `file` fields, and zero or more public `url` fields. A file is limited to 25 MB and a batch to 60 MB.

## Network and privacy boundaries

| Data | Destination | Reason |
| --- | --- | --- |
| Raw microphone frames | Local Porcupine/Cheetah Web Workers | Wake detection and transcription |
| User transcript | Local Next.js API, local memory files, OpenRouter, and Moss Cloud only when sync succeeds | Memory, retrieval, and response generation |
| Retrieved Moss context | OpenRouter | Grounding the response in relevant memory |
| Conversation record, extracted facts, tasks | Private local data file first; Moss Cloud through `addDocs()` when available | Guaranteed local persistence and optional cross-device sync |
| Imported files and public-link text | Local extraction, private local data file, local Moss index, and optional private Moss Cloud index | Searchable knowledge ingestion |
| Final response text | ElevenLabs | Speech synthesis |
| Runtime credentials entered in the UI | Browser `localStorage` and local Next.js process | Runtime provider configuration |

Do not expose this development server to an untrusted network while using browser-stored provider keys.

## Memory and credential locations

| Mode | Second-brain location | Credential location |
| --- | --- | --- |
| Browser development | `<repo>/.jarvis-data/second-brain.json` and `second-brain.moss/` | Browser `localStorage` or `.env.local` |
| Installed macOS app | `~/Library/Application Support/ai.jarvis.secondbrain/` | Tauri WebView `localStorage` |

The JSON memory file is written atomically with owner-only (`0600`) permissions. `second-brain.moss/` is a generated local Moss index; the JSON document store remains the canonical recovery source. `.env.local`, local memories, generated server bundles, embedded Node copies, and Rust build output are ignored by Git.

## GitHub publishing checklist

Before pushing:

```bash
pnpm typecheck
git status --short
```

Commit source files including `src-tauri/Cargo.lock`, `src-tauri/icons/`, and `scripts/prepare-desktop.mjs`. Do not commit:

- `.env.local` or any provider key;
- `.jarvis-data/` or personal memories;
- `.next/` or `.desktop-server/`;
- `src-tauri/resources/node`;
- `src-tauri/target/`; or
- the installed `/Applications/Jarvis.app` bundle.

GitHub users build their own architecture-matched Node/Tauri bundle with `pnpm desktop:build`.

## Failure behavior

| Failure | UI behavior |
| --- | --- |
| Missing Moss credentials | Core opens CONFIG and keeps the command channel locked until Moss and OpenRouter values exist |
| Invalid Moss credentials or unavailable cloud quota | Jarvis can continue as `MOSS LOCAL` when the local engine initializes; the HUD reports the actual cloud error |
| Missing OpenRouter key | Moss can initialize, but conversational turns fail before generation |
| Missing ElevenLabs key | Normal text response; no TTS request or speech playback is attempted |
| Missing Picovoice key | Normal text mode; the reactor focuses the command field and `ADD VOICE` opens configuration |
| Microphone denied | Text command bar remains available |
| Session lost after server restart or hot reload | The next text prompt automatically creates a replacement Moss session and retries once |
| Moss Cloud quota/index unavailable | Jarvis reports `MOSS LOCAL`, saves the turn locally, retrieves it through Moss's local engine, and retries cloud sync on a later initialization |
| Local Moss engine unavailable | Jarvis still stores the turn in the private JSON store and uses deterministic local retrieval |

## Current limitations

- Task completion and editing are not yet exposed in the HUD. Individual Second Brain chunks can be deleted from the full-screen archive.
- Tasks are memory documents, not operating-system notifications or background alarms.
- Recurrence is stored but not expanded into future task instances.
- Raw working turns are process-local; completed exchanges are durable conversation documents.
- Conversation “summaries” currently store the complete user/assistant exchange rather than a separately compressed summary.
- There is no account/user namespace beyond the configured Moss project and index name.
- Runtime credentials use browser storage rather than the macOS Keychain or Tauri Stronghold.
- The generated macOS app is locally built and not notarized for public distribution.
- The desktop UI imports selected files rather than continuously watching arbitrary folders.
- The integration does not currently write Obsidian `[[wikilinks]]` or expose Jarvis memory as an MCP server to other applications.

## Troubleshooting

### The HUD says `MOSS CREDENTIALS REQUIRED`

Open **CONFIG**, enter both the Moss Project ID and Project Key, and save. Their presence unlocks the text-first initialization path; Jarvis then reports whether cloud sync succeeded or local Moss mode is active.

### Settings say OpenRouter is linked, but turns fail

Confirm that the configured OpenRouter account has credits and access to `OPENROUTER_MODEL`. A linked status only means a key exists; it does not make a paid provider request during the status check.

### The text command field will not accept typing

Text input becomes available as soon as both Moss and OpenRouter show `LINKED`; a temporary Moss session ID is not required just to type. Click the command bar or the central reactor, type a directive, and press Return or **TRANSMIT**. If the Next.js server restarted and invalidated the old in-memory session, Jarvis rebuilds it automatically when the prompt is sent. If the field still says to add credentials, open **CONFIG**, save the two required providers, and hard-refresh the page.

If Moss Cloud rejects synchronization because the project has reached an index, ingest, or monthly usage limit, the HUD displays `MOSS LOCAL`. This is not a memory-loss mode: completed turns are written to the local second brain and indexed by Moss locally. Cloud synchronization resumes after quota becomes available.

### Moss says `Monthly voice minutes limit ... reached`

This response comes from the Moss project API, even when Jarvis itself is in text mode; it is unrelated to ElevenLabs or Picovoice. The local Moss engine remains operational. To restore Moss Cloud sync, use a Moss project whose monthly allowance is available, wait for the billing-period reset, enable pay-as-you-go/upgrade the plan, or ask Moss support to correct the project meter. Entering a different valid Project ID and Project Key in **CONFIG** immediately triggers a new sync attempt; the existing local memories are uploaded to `jarvis-second-brain` if that project accepts index creation.

### Can I use a model other than GPT-4.1 Mini?

Yes. In **CONFIG**, replace the model field with any exact OpenRouter text/chat model ID available to your account. The catalog suggestions are conveniences, not an allow-list. Models without reliable JSON instruction following can still answer normally; only automatic durable-fact and task extraction may be less consistent for those models.

### Voice initialization takes a long time

The Cheetah model is approximately 34 MB. The initial browser load and IndexedDB cache write can be noticeably slower than later starts.

### The central reactor is red

Read the status line directly under it. Red indicates missing credentials, provider validation failure, or an API error; it is not merely a decorative state.

### Tauri cannot compile

Verify:

```bash
node --version
pnpm --version
rustc --version
cargo --version
```

Then confirm the platform dependencies in the [Tauri prerequisites guide](https://v2.tauri.app/start/prerequisites/). The first build needs several gigabytes of free disk space.

### The packaged app opens but its server does not start

Rebuild with `pnpm desktop:build`; do not manually copy `.next/standalone` into an app bundle. The preparation script must materialize pnpm dependencies, copy the Moss native package, and embed Node. Confirm that no unrelated process is already listening on port 3000:

```bash
lsof -nP -iTCP:3000 -sTCP:LISTEN
```

### The desktop CONFIG panel does not show browser credentials

This is expected. Safari/Chrome and Tauri use separate storage. Enter the credentials once in the desktop CONFIG panel or provide them through `.env.local` for development.

## Validation commands

```bash
pnpm typecheck
pnpm build
pnpm desktop:build
```

## Primary references

- [Naut1cal5/moss-brain](https://github.com/Naut1cal5/moss-brain)
- [Moss sessions](https://docs.moss.dev/docs/integrate/sessions)
- [Moss storage and persistence](https://docs.moss.dev/docs/integrate/storage-persistence)
- [Moss pricing and limits](https://docs.moss.dev/docs/pricing)
- [Moss metadata filtering](https://docs.moss.dev/docs/integrate/metadata-filtering)
- [Moss JavaScript SDK reference](https://docs.moss.dev/docs/reference/js/api)
- [Moss repository and ElevenLabs example](https://github.com/usemoss/moss/tree/main/apps/elevenlabs-moss)
- [Porcupine Web quick start](https://picovoice.ai/docs/quick-start/porcupine-web/)
- [Cheetah Web quick start](https://picovoice.ai/docs/quick-start/cheetah-web/)
- [OpenRouter quick start](https://openrouter.ai/docs/quickstart)
- [OpenRouter models](https://openrouter.ai/docs/guides/overview/models)
- [ElevenLabs text-to-speech endpoint](https://elevenlabs.io/docs/api-reference/text-to-speech/convert)
- [Tauri 2 configuration reference](https://v2.tauri.app/reference/config/)
- [Tauri external binaries](https://v2.tauri.app/develop/sidecar/)
- [Tauri macOS application bundles](https://v2.tauri.app/distribute/macos-application-bundle/)
