# Moss Interview Coach

Real-time voice interview coach grounded by **Moss** sub-10ms hybrid retrieval. Voice runs fully local:

| Layer | Service | Cloud key? |
|-------|---------|------------|
| Retrieval | Moss (per-track rubric indexes) | Yes — only required cloud creds |
| LLM | Ollama `llama3.1` (tool calling) | No |
| STT | Whisper (faster-whisper) | No |
| TTS | Piper | No |
| Transport | Pipecat SmallWebRTC (P2P) | No |

## Prerequisites

- Python 3.11+
- Node.js 22.14+ — required by `@daily-co/daily-js`, pulled in via
  `@pipecat-ai/small-webrtc-transport`; installs under Node 20 fail when
  `engine-strict` is set
- [Ollama](https://ollama.com) with `llama3.1`
- Moss project credentials from [moss.dev](https://moss.dev) / [docs.moss.dev](https://docs.moss.dev)

## Setup

### 1. Ollama

```bash
ollama pull llama3.1
ollama serve
```

### 2. Backend

```bash
cd apps/moss-interview-coach/backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Set ONLY:
#   MOSS_PROJECT_ID=...
#   MOSS_PROJECT_KEY=...
python ingest_knowledge.py
python server.py
```

`server.py` loads `.env` via `python-dotenv` and starts uvicorn with `BACKEND_HOST` / `BACKEND_PORT` (defaults `127.0.0.1:8000`).

> [!WARNING]
> `/api/offer` is unauthenticated, and CORS does not stop non-browser callers.
> Every call starts local Whisper/Ollama/Piper work and grader subprocesses, so
> the backend binds to loopback by default. Set `BACKEND_HOST=0.0.0.0` only when
> you deliberately want to expose it, and put authentication in front of it.

First conversation may download Whisper / Piper models. Health: `GET http://localhost:8000/health` (or your configured `BACKEND_PORT`)

Re-ingest rubrics (all tracks by default):

```bash
python ingest_knowledge.py --recreate
# single track: python ingest_knowledge.py --track machine-learning-concepts --recreate
# custom source: python ingest_knowledge.py --source ./knowledge/system_design_rubrics.json --index-name system-design-rubric --recreate
```

### 3. Frontend

```bash
cd apps/moss-interview-coach/frontend
cp .env.example .env.local
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) → pick a track (**System Design**, **Agent-Native Infrastructure**, or **Machine Learning Concepts**) → **Start Interview**.

## Environment

| Variable | Required | Default |
|----------|----------|---------|
| `MOSS_PROJECT_ID` | yes | — |
| `MOSS_PROJECT_KEY` | yes | — |
| `OLLAMA_BASE_URL` | no | `http://localhost:11434/v1` |
| `OLLAMA_MODEL` | no | `llama3.1` |
| `OLLAMA_GRADE_MODEL` | no | unset — follows `OLLAMA_MODEL` (leave commented in `.env.example`) |
| `WHISPER_MODEL` | no | `base` |
| `WHISPER_DEVICE` | no | `auto` |
| `PIPER_VOICE` | no | `en_US-lessac-medium` |
| `GRADE_SUBPROCESS_TIMEOUT_SECS` | no | `60` |
| `SESSION_HANDSHAKE_TIMEOUT_SECS` | no | `45` — ends a session whose client never completes the WebRTC/RTVI handshake |
| `MAX_ACTIVE_BOTS` | no | `2` — further offers get 503 until a slot frees |
| `BACKEND_HOST` | no | `127.0.0.1` |
| `BACKEND_PORT` | no | `8000` |
| `BACKEND_RELOAD` | no | unset — uvicorn autoreload off; set `1` for development only |
| `CORS_ORIGINS` | no | `http://localhost:3000` |
| `NEXT_PUBLIC_BACKEND_URL` | no | `http://localhost:8000` |

Each track loads its own Moss index:

| Track | Index | Knowledge file |
|-------|-------|----------------|
| System Design | `system-design-rubric` | `knowledge/system_design_rubrics.json` |
| Agent-Native Infrastructure | `agent-native-infrastructure-rubric` | `knowledge/agent_native_rubrics.json` |
| Machine Learning Concepts | `machine-learning-concepts-rubric` | `knowledge/ml_concepts_rubrics.json` |

## Architecture

```text
Browser (SmallWebRTC)
  ↔ POST /api/offer (SDP)
  ↔ Pipecat: Silero VAD → Whisper → MossContextInjector → Ollama(+tools) → Piper
  ↔ Assist panel events: current_question / user_answer / grade_result
```

Moss loads **all track indexes** into the local runtime at startup (`load_index`), then each user turn queries the selected track’s index in-process (&lt;10 ms) and appends **Context/Rubric Guidelines** to the LLM system prompt — the same ambient-retrieval pattern described in the [Moss Pipecat integration](https://docs.moss.dev/docs/integrations/pipecat) and [offline-first search](https://docs.moss.dev/docs/build/offline-first-search) docs.

During an active session, the **Assist** side panel shows the current coach question, your last answer, and real-time grade feedback. When the coach LLM decides a substantive answer was given, it calls the `grade_candidate_answer` tool; grading then runs in a **separate Python subprocess** ([`grader_worker.py`](backend/grader_worker.py)) against the Moss rubric (score + tips) so Ollama grading work never shares the spoken coach process. Results return only via RTVI to the Assist panel — never through TTS.

## Key files

- [`backend/tracks.py`](backend/tracks.py) — track prompts, index names, grader personas
- [`backend/ingest_knowledge.py`](backend/ingest_knowledge.py) — create/load per-track Moss indexes
- [`backend/grader_worker.py`](backend/grader_worker.py) — subprocess grader (must ship with the app)
- [`backend/server.py`](backend/server.py) — FastAPI + SmallWebRTC + Moss injector
- [`frontend/app/page.tsx`](frontend/app/page.tsx) — Idle / Connecting / Active HUD

## Notes

- Assist panel reads WebRTC data-channel JSON (`type: "interruption"` / `"current_question"` / `"user_answer"` / `"grade_result"` / `"grading_started"`). Grading is LLM tool-triggered via `grade_candidate_answer`, then executed in the `grader_worker` subprocess.
- Local Whisper + Piper STT/TTS latency will usually exceed cloud Deepgram/Cartesia; Moss remains the sub-10ms retrieval hop.
- Interruption / barge-in uses Pipecat VAD turn strategies. Active session footer: **Powered by Moss**.
- Coach conversation uses Ollama tool calling; `llama3` (no tools) will 400 — use `llama3.1` or another tool-capable model.
