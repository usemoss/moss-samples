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
import asyncio
from pipecat_moss import MossRetrievalService

moss_service = MossRetrievalService(
    project_id=os.getenv("MOSS_PROJECT_ID"),
    project_key=os.getenv("MOSS_PROJECT_KEY"),
    system_prompt="Relevant passages from the Moss knowledge base:\n\n",
)

async def setup_indexes():
    await moss_service.load_index(os.getenv("MOSS_INDEX_NAME"))

asyncio.run(setup_indexes())

pipeline = Pipeline([
    transport.input(),               # audio/user input
    stt,                             # speech to text
    context_aggregator.user(),       # add user text to context
    moss_service.query(os.getenv("MOSS_INDEX_NAME"), top_k=5, alpha=0.8),  # retrieve relevant docs from Moss
    llm,                             # LLM generates response
    tts,                             # TTS synthesis
    transport.output(),              # stream audio back to user
    context_aggregator.assistant(),  # store assistant response
])
```

`setup_indexes()` must be awaited before the pipeline starts so the service can load the Moss index. See `examples/moss-retrieval-demo.py` for a complete working example.

## Pipecat Compatibility

Tested with Pipecat v0.0.99. Please upgrade to this version (or newer) to ensure API compatibility with the snippets below.

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

- `project_id` (required): Moss project ID (can use env var `MOSS_PROJECT_ID`)
- `project_key` (required): Moss project key (can use env var `MOSS_PROJECT_KEY`)
- `system_prompt` (default: "Here is additional context retrieved from database:\n\n"): Prefix added ahead of retrieved documents
- `load_index(index_name)`: Awaitable method that loads the given index before the pipeline runs
- `query(index_name, *, top_k=5)`: Returns a `MossIndexProcessor` for the specified index; `top_k` controls result count, `alpha` blends semantic vs keyword scoring (0.0 keyword-only, 1.0 semantic-only)

## License

This integration is licensed under the BSD 2-Clause License. See `LICENSE`.

## Support

- [Moss Docs](https://docs.usemoss.dev)
- [Moss Discord](https://discord.com/invite/eMXExuafBR)
- [Pipecat Docs](https://docs.pipecat.ai)
