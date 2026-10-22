# Voice Agent

A customer-support **voice agent** grounded in a Moss knowledge base, with a brand-styled
web UI that shows Moss doing the retrieval live. You talk to it, it searches your data,
and a side panel surfaces the exact chunks Moss returned (with match scores and query
latency) for every turn.

```
Browser (web/)  ⟷  LiveKit room  ⟷  agent.py (STT → LLM → TTS)  ⟷  Moss (RAG)
```

## What you need

- A [Moss](https://moss.dev) account (project ID + key)
- [LiveKit](https://livekit.io) — local (`livekit-server --dev`) or [LiveKit Cloud](https://cloud.livekit.io)
- [OpenAI](https://platform.openai.com) (LLM), [Deepgram](https://deepgram.com)
  (speech-to-text), and [Cartesia](https://cartesia.ai) (text-to-speech) API keys
- Python 3.14+ (`uv`) and Node 18.18+ (`npm`) for the web UI

## Setup

```bash
uv sync
cp .env.example .env          # fill in your Moss + provider keys
uv run python agent.py download-files
```

`.env` keys: `MOSS_PROJECT_ID`, `MOSS_PROJECT_KEY`, `OPENAI_API_KEY`, `DEEPGRAM_API_KEY`, `CARTESIA_API_KEY`.
For local LiveKit, leave the `LIVEKIT_*` values as-is; for LiveKit Cloud, set them to your
project's URL/key/secret and copy the same three into `web/.env.local`. The index name
defaults to `demo-customer_faqs` (override with `MOSS_INDEX_NAME`).

## 1. Seed the knowledge base

Loads the sample support FAQs in `data/faqs.json` into a Moss index:

```bash
uv run python seed_index.py
```

## 2. Run it

Open three terminals (skip terminal **a** if you are on LiveKit Cloud):

```bash
# a) LiveKit server — local-dev only (skip when using LiveKit Cloud)
livekit-server --dev

# b) the agent (joins rooms automatically)
uv run python agent.py dev

# c) the web UI
cd web
npm install
# create once; do not overwrite an existing Cloud-configured .env.local
[ -f .env.local ] || cp .env.local.example .env.local
npm run dev            # → http://127.0.0.1:3000 (loopback-only; `npm run dev:lan` enables LAN + ALLOW_REMOTE_TOKEN)
```

Open http://127.0.0.1:3000, click **Start the demo**, and talk. The right-hand panel
shows what Moss retrieves on each turn.

> Prefer no UI? `uv run python agent.py console` still works for a mic-only, terminal session.
> For console-only demos you can set `MOSS_REGION=US` or `EU` in `.env`; the web UI picker
> is authoritative when using the browser and overrides that default on connect.

## How the retrieval panel works

On each user turn, `agent.py` queries Moss and publishes the results to the LiveKit room
on the `moss.retrieval` data channel:

```json
{
  "query": "string",
  "docs": [{ "id": "string | null (optional)", "text": "string", "score": 0.0 }],
  "took_ms": 0.0,
  "region": "US | EU"
}
```

The web UI listens on that channel and renders them. The voice pipeline is otherwise untouched.

See [`DEMO_SCRIPT_METADATA.md`](./DEMO_SCRIPT_METADATA.md) for a ready-to-record walkthrough.

## Resources

- [Docs](https://docs.moss.dev/?utm_source=github&utm_medium=readme&utm_campaign=voice-agent)
- [Portal](https://portal.usemoss.dev/?utm_source=github&utm_medium=readme&utm_campaign=voice-agent)
- [GitHub](https://github.com/usemoss/moss)
- [Discord](https://discord.com/invite/eMXExuafBR?utm_source=github&utm_medium=readme&utm_campaign=voice-agent)
