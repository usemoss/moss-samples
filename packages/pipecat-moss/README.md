# Pipecat Moss Integration

Moss delivers sub-10ms semantic retrieval, ensuring your Pipecat AI voice agents respond naturally without noticeable delays.

## Installation

Install the package

```bash
pip install pipecat-moss
```

## Prerequisites
- Moss project ID and project key (get them from [Moss Portal](https://portal.usemoss.dev))
- Deepgram, OpenAI, Cartesia API keys (to run the example)

## Usage with Pipecat Pipeline

Pipecat-Moss integrates seamlessly into a Pipecat pipeline, enabling efficient retrieval-based operations. It leverages Pipecat's modular architecture to inject semantic context for Voice AI Agents.

```python
import os
from pipecat.pipeline.pipeline import Pipeline
from pipecat_moss import MossRetrievalService

# One service per process, shared by every bot the process runs.
moss_service = MossRetrievalService(
    project_id=os.getenv("MOSS_PROJECT_ID"),
    project_key=os.getenv("MOSS_PROJECT_KEY"),
    system_prompt="Relevant passages from the Moss knowledge base:\n\n",
    # A writable directory; use persistent storage in production so a new process reads from disk.
    cache_path=os.getenv("MOSS_CACHE_PATH", "./moss-cache"),
)

async def build_pipeline(transport, stt, llm, tts, context_aggregator) -> Pipeline:
    # Before the pipeline starts: loads the index, or checks a loaded one for a newer version.
    await moss_service.load_index(os.getenv("MOSS_INDEX_NAME"))

    return Pipeline([
        transport.input(),               # audio/user input
        stt,                             # speech to text
        context_aggregator.user(),       # add user text to context
        moss_service.query(os.getenv("MOSS_INDEX_NAME"), top_k=5, alpha=0.8),  # retrieve relevant docs from Moss
        llm,                             # LLM generates response
        tts,                             # TTS synthesis
        transport.output(),              # stream audio back to user
        context_aggregator.assistant(),  # store assistant response
    ])

# In each bot: pipeline = await build_pipeline(...), then run it with a
# PipelineTask and PipelineRunner, as examples/moss-retrieval-demo.py does.
```

Await `load_index` before the pipeline starts. A service loads each index once: later and concurrent calls wait for that same load, so every bot in the process shares one copy of the index and the embedding model. A new service, or a new process, holds its own copy. See `examples/moss-retrieval-demo.py` for a complete working example, which starts the load while the transport connects.

## Pipecat Compatibility

Requires `pipecat-ai` 1.5 or later and `moss` 1.14 or later. Tested with `pipecat-ai` 1.13 and `moss` 1.19.

## Contributing

If you are contributing or want to build from source, follow the [CONTRIBUTING.md](CONTRIBUTING.md) setup steps.

## Running the Example

### Setup Environment Variables

Create a `.env` file in the root directory with the following content:

```env
MOSS_PROJECT_ID= Your Moss Project ID
MOSS_PROJECT_KEY= Your Moss Project Key
MOSS_INDEX_NAME= Your Moss Index Name

DEEPGRAM_API_KEY= Your DEEPGRAM API KEY
CARTESIA_API_KEY= Your CARTESIA API KEY
OPENAI_API_KEY= Your OpenAI Key
```

Or pass them directly when creating the MossRetrievalService.

### Creating a Moss Index (One-time Setup)

Before using Moss in your pipeline, you need to create an index and populate it with documents:

```bash
python examples/moss-create-index-demo.py
```

### Run the Example

```bash
python examples/moss-retrieval-demo.py
```

## Configuration Options

### MossRetrievalService

- `project_id` (required): Moss project ID (defaults to env var `MOSS_PROJECT_ID`)
- `project_key` (required): Moss project key (defaults to env var `MOSS_PROJECT_KEY`)
- `system_prompt` (default: "Here is additional context retrieved from database:\n\n"): Prefix added ahead of retrieved documents
- `cache_path` (default: none): Directory that keeps downloaded indexes on disk, so a load in a new process reads an unchanged index from disk instead of downloading it
- `load_index(index_name, *, auto_refresh=False)`: Awaitable method that loads the given index, or checks a loaded one for a newer cloud version. `auto_refresh=True` keeps the index on the latest version while the process runs, but its periodic refresh counts as session time, so a long-running process with it on is billed for session minutes around the clock, calls or not. Leave it off unless the index must follow edits between calls
- `query(index_name, *, top_k=5)`: Returns a `MossIndexProcessor` for the specified index; `top_k` controls result count, `alpha` blends semantic vs keyword scoring (0.0 keyword-only, 1.0 semantic-only)

## License

This integration is licensed under the BSD 2-Clause License. See `LICENSE`.

## Support

- [Moss Docs](https://docs.usemoss.dev)
- [Moss Discord](https://discord.com/invite/eMXExuafBR)
- [Pipecat Docs](https://docs.pipecat.ai)
