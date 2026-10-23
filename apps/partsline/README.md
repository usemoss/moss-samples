# PartsLine

A browser-based voice agent for auto parts counters, built on [Moss](https://github.com/usemoss/moss) for retrieval and [LiveKit](https://livekit.io) for voice.

A caller asks: *"Do you have front brake pads for a 2013 Honda Civic?"* PartsLine looks it up against a real parts catalog and answers from what it actually finds. If the caller's car isn't in the catalog, it says so, instead of quoting the nearest-sounding part.

## Why auto parts counters

A parts counter is a noisy, small-margin shop, usually with a couple of phones ringing and one person trying to answer them while also helping whoever's standing at the counter. The call is almost always the same shape: someone reads off a year, make, model, and asks if a part's in stock. That's a lot of repetitive lookups against the same catalog, all day.

It's also a good stress test for Moss specifically. A shop's network isn't always great, and nobody's going to tolerate a voice agent that goes quiet for a second while a query round-trips to some cloud vector database — a pause that long just reads as "the line dropped." Moss loads the catalog into the agent's own process, so a lookup is a function call, not a network request. That's what makes it possible to search a real catalog *while someone's mid-sentence* and still sound like a person, not a phone tree.

## What it actually does

- Caller connects in a browser and talks to the agent.
- Every lookup shows up live as a small card in the transcript — what vehicle it searched, and what it found.
- Some cars have two engine options for the same part. If the agent isn't sure which one, it asks.
- Some parts get discontinued and replaced. The agent tells the caller that, then quotes the current part.
- If the vehicle isn't in the catalog at all, it says so — it won't quote something close and hope it fits.
- A caller can ask to have a found part held under their name, or get bumped to a person for anything more complicated (returns, fleet pricing, modifications).
- Every finished call lands in a simple call log — vehicle, part, outcome.

[Demo video](./promo/demo.mp4) <!-- add once recorded -->

## Quickstart

### You'll need

- Python 3.11+
- Node.js 18+
- A [Moss](https://usemoss.dev) account and project credentials
- A [LiveKit Cloud](https://cloud.livekit.io) project (the free tier is enough)
- API keys for Deepgram, Cartesia, and an LLM provider (Anthropic here, but any tool-calling model works)

### 1. Install

```bash
cd apps/partsline
pip install -r agent/requirements.txt
npm install
```

### 2. Set up your `.env`

```bash
cp .env.example .env
```

Fill in `MOSS_PROJECT_ID`, `MOSS_PROJECT_KEY`, `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`, `DEEPGRAM_API_KEY`, `CARTESIA_API_KEY`, `ANTHROPIC_API_KEY`.

### 3. Load the catalog into Moss

```bash
python seed.py
```

`catalog/demo_catalog.json` is a small, intentionally messy catalog: a car with two engine options, a discontinued part with a current replacement, a universal-fit part, and a car that isn't in the catalog at all, on purpose.

### 4. Start the agent

```bash
python -m agent.main dev
```

### 5. Start the web app

```bash
npm run dev
```

Open `http://localhost:3000`, hit **Talk**, and try:

- *"Do you have front brake pads for a 2013 Honda Civic?"* — a normal, in-stock lookup.
- *"I need a serpentine belt for a 2014 Subaru Outback"* — that car has two engine options; leave yours out and see what it asks.
- *"Do you have front brake pads for a 2019 Toyota RAV4?"* — not in the catalog. Watch it say so instead of guessing.
- *"I need an oil filter for a 2015 Toyota Camry"* — this one's discontinued; watch it catch that and quote the replacement.

## How it's put together

```
Browser (Next.js, LiveKit client)
  ⇄ LiveKit room ⇄ Agent worker (Python)
      Deepgram (STT) → Claude Haiku (LLM) ⇄ Moss (retrieval, function tool)
                     → Cartesia (TTS)
  → SQLite (call log) → /calls page
```

- **`agent/`** — the voice agent. `main.py` sets up the LiveKit session. `tools/lookup_part.py` is the only retrieval tool the model has, and it won't run without a year, make, and model — there's no path in the code for an unfiltered search to slip through.
- **`agent/tools/set_aside.py`**, **`transfer.py`** — hold a part under a caller's name; hand off to a human with the vehicle and part already noted down.
- **`agent/outcome.py`**, **`db.py`** — the call record, and writing it to SQLite once a call ends.
- **`app/`** — the demo page, the live transcript with the retrieval cards, and the `/calls` log.
- **`catalog/demo_catalog.json`**, **`seed.py`**, **`query.py`** — the seed catalog plus the scripts that load and query it.

The lookup tool builds a Moss filter out of the vehicle info (and guesses the part category from what the caller asked for, so a belt request literally can't come back as a filter), queries an index that's loaded once when the agent starts, and sorts the result into one of four buckets: a clean match, more than one match, a part that's been replaced, or nothing. It never falls back to a fuzzy search to find something "close enough."

## Testing

```bash
pytest
ruff check .
mypy .
npm run lint
npm run typecheck
```

## What's not in here

- One part per call — no handling multiple parts in the same conversation.
- Browser only, no phone line.
- No real POS or inventory system behind it — prices and stock come from the seed catalog.
- Parts that change mid-model-year (like a spec change partway through 2014) aren't handled yet.

## License

MIT — see [LICENSE](./LICENSE).

