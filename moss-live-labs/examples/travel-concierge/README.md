# Travel Concierge — pre-loaded catalog + live session

A voice travel concierge that answers from **two Moss indexes at once**:

- a **pre-loaded catalog** (long-term, shared across every call)
- a **live session** that captures what you say on *this* call (short-term, in-memory)

Each turn it recalls your stated preferences (session) and recommends trips (catalog). The
web UI shows both indexes side by side, lighting up per turn.

```
Browser (web/)  ⟷  LiveKit room  ⟷  agent.py (STT → LLM → TTS)  ⟷  Moss (catalog + session)
```

## What you need
- A [Moss](https://moss.dev) account · [LiveKit](https://livekit.io) (local) · OpenAI (LLM),
  Deepgram (STT), Cartesia (TTS) keys · Python 3.14+ (`uv`) and Node 18.18+.

## Setup
```bash
uv sync
cp .env.example .env          # fill in Moss + provider keys
python agent.py download-files
```

## 1. Seed the catalog (the cloud index)
```bash
python seed_index.py
```
The live session is built at runtime by the agent — nothing to seed there.

## 2. Run (three terminals)
```bash
livekit-server --dev
python agent.py dev
cd web && npm install && cp .env.local.example .env.local && npm run dev   # localhost:3000
```

Click **Start planning**, then talk: tell it your budget, dates, and who's coming, ask it
to recall them, and ask for a recommendation.

## How it works
Per turn, `agent.py`:
1. queries the **live session** (recall what you've said),
2. queries the **pre-loaded catalog** (matching trips),
3. injects both into the model, then
4. **distills your turn into facts and stores only those** in the session, so later turns
   recall clean preferences — not questions or filler.

Both result sets are published on the `moss.retrieval` data channel; the UI renders
**Catalog (cloud)** and **This call (session)**. See [`DEMO_SCRIPT.md`](./DEMO_SCRIPT.md).

## Resources
- [Docs — Sessions](https://docs.moss.dev/docs/integrate/sessions)
- [GitHub](https://github.com/usemoss/moss)
