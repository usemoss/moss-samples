# LiveKit + Moss Support Voice Agent

This project hosts a realtime LiveKit voice assistant that queries a Moss semantic search index of FAQs before responding. Every user request is grounded in Moss results, which are logged and injected directly into the LLM conversation.

## Repository layout

```text
livekit-agent/
├── agent.py               # Customer support voice agent with Moss integration
├── create_index.py        # Helper script to (re)build the FAQ index in Moss
├── faqs.json              # Local FAQ dataset ingested into Moss
├── pyproject.toml         # Python dependencies managed with uv
└── README.md              # You are here
```

## Prerequisites

- Python 3.9+
- [uv](https://github.com/astral-sh/uv) for dependency management (`pip install uv`)
- Microphone and speakers for console testing
- Accounts and credentials for:
  - Azure OpenAI (llm)
  - Deepgram (speech-to-text)
  - Cartesia (text-to-speech)
  - Moss (semantic search)

## Installation

```bash
cd livekit-agent
uv sync
```

## Configure environment variables

Copy `.env.example` to `.env` and populate the values below. All keys are required unless noted.

| Variable | Purpose |
|----------|---------|
| `OPENAI_ENDPOINT` | Azure OpenAI endpoint URL, e.g. `https://<resource>.openai.azure.com` |
| `OPENAI_DEPLOYMENT` | Azure OpenAI chat deployment name |
| `OPENAI_API_KEY` | Azure OpenAI API key |
| `OPENAI_API_VERSION` | Azure OpenAI API version (e.g. `2024-02-15-preview`) |
| `DEEPGRAM_API_KEY` | Deepgram Nova STT key |
| `CARTESIA_API_KEY` | Cartesia Sonic TTS API key |
| `MOSS_PROJECT_ID` | Moss project identifier |
| `MOSS_PROJECT_KEY` | Moss project API key |
| `MOSS_INDEX_NAME` | Name of the FAQ index to query |
| `MOSS_MODEL_ID` | *(Optional)* Moss embedding model (defaults to `moss-minilm` if omitted) |

Optional LiveKit cloud deployment variables (`LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`) can stay unset when running in console mode.

The bundled `.env.example` file already lists these keys—copy it to `.env` and replace the placeholder values with your real credentials.

## Build or refresh the Moss FAQ index

The agent expects an existing Moss index populated with the FAQ entries from `faqs.json` in this directory. Run the helper whenever you update the dataset:

```bash
uv run python create_index.py
```

The script validates the JSON data, uploads every FAQ to Moss, and reports the index creation response. Ensure your Moss credentials are present in `.env` before running.

## Run the voice agent locally

```bash
uv run python agent.py console
```

Console mode streams audio through your default microphone and speakers. The assistant:

- Loads the configured Moss index on first use.
- Executes a Moss query for every user utterance.
- Logs the query alongside the full text of the top matches.
- Feeds the Moss results into the LLM context to produce grounded answers.

Stop the session with Ctrl+C.

## Notes

- `agent.py` uses Deepgram Nova-2 for speech-to-text, Azure OpenAI for LLM + Cartesia Sonic-2 for TTS, and Silero VAD for turn detection. Adjust providers in the `AgentSession` definition if needed.
- Long Moss documents will appear verbatim in the logs and in the context sent to the LLM. Trim or post-process text in `search_support_faqs` if you need shorter prompts.
- To integrate with LiveKit Cloud instead of console mode, configure the optional LiveKit environment variables and call `uv run python agent.py start` from a deployment environment.
