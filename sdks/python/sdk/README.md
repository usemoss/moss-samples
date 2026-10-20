# Moss client library for Python

`moss` enables **private, on-device semantic search** in your Python applications with cloud storage capabilities.

Built for developers who want **instant, memory-efficient, privacy-first AI features** with seamless cloud integration.

## ✨ Features

- ⚡ **On-Device Vector Search** - Sub-millisecond retrieval with zero network latency
- 🔍 **Semantic, Keyword & Hybrid Search** - Embedding search blended with Keyword matching
- ☁️ **Cloud Storage Integration** - Automatic index synchronization with cloud storage
- 📦 **Multi-Index Support** - Manage multiple isolated search spaces
- 🛡️ **Privacy-First by Design** - Computation happens locally. Indexes sync to the cloud, and usage telemetry is sent (see [Telemetry](#telemetry))
- 🚀 **High-Performance Rust Core** - Built on optimized Rust bindings for maximum speed
- 🧠 **Custom Embedding Overrides** - Provide your own document and query vectors when you need full control

## 📦 Installation

```bash
pip install moss
```

## 🚀 Quick Start

```python
import asyncio
from moss import MossClient, DocumentInfo, QueryOptions

async def main():
    # Initialize search client with project credentials
    client = MossClient("your-project-id", "your-project-key")

    # Prepare documents to index
    documents = [
        DocumentInfo(
            id="doc1",
            text="How do I track my order? You can track your order by logging into your account.",
            metadata={"category": "shipping"}
        ),
        DocumentInfo(
            id="doc2", 
            text="What is your return policy? We offer a 30-day return policy for most items.",
            metadata={"category": "returns"}
        ),
        DocumentInfo(
            id="doc3",
            text="How can I change my shipping address? Contact our customer service team.",
            metadata={"category": "support"}
        )
    ]

    # Create an index with documents (syncs to cloud)
    index_name = "faqs"
    await client.create_index(index_name, documents)  # Defaults to moss-minilm
    print("Index created and synced to cloud!")

    # Load the index (from cloud or local cache)
    await client.load_index(index_name)

    # Search the index
    result = await client.query(
        index_name,
        "How do I return a damaged product?",
        QueryOptions(top_k=3, alpha=0.6),
    )

    # Display results
    print(f"Query: {result.query}")
    for doc in result.docs:
        print(f"Score: {doc.score:.4f}")
        print(f"ID: {doc.id}")
        print(f"Text: {doc.text}")
        print("---")

asyncio.run(main())
```

### Scores and `min_score`

Each result's `score` is its relevance to the query from 0 to 1. Results are
ordered by hybrid relevance, so a lower result can show a higher score. Scores
depend on the embedding model: tune `min_score` on your own queries.

`QueryOptions(min_score=0.5)` drops results whose score is below 0.5; a query
returns up to `top_k` results that clear it, in hybrid order. It takes a value
from 0 to 1. Keyword-only queries (`alpha=0.0`) have no embedding to score
against: every result scores 0.0 and `min_score` raises an error.

## 🔥 Example Use Cases

- Smart knowledge base search with cloud backup
- Realtime Voice AI agents with persistent indexes
- Personal note-taking search with sync across devices
- Private in-app AI features with cloud storage
- Local semantic search in edge devices, fully on-device

## Available Models

- `moss-minilm`: Lightweight model optimized for speed and efficiency
- `moss-mediumlm`: Balanced model offering higher accuracy with reasonable performance

## 🔧 Getting Started

### Prerequisites

- Python 3.8 or higher
- Valid InferEdge project credentials

### Environment Setup

1. **Install the package:**

```bash
pip install moss
```

2. **Get your credentials:**

Sign up at [InferEdge Platform](https://platform.inferedge.dev) to get your `project_id` and `project_key`.

3. **Set up environment variables (optional):**

```bash
export MOSS_PROJECT_ID="your-project-id"
export MOSS_PROJECT_KEY="your-project-key"
# Optional: override the manage API host (defaults to https://service.usemoss.dev)
export MOSS_CLOUD_API_BASE_URL="https://service.usemoss.dev"
```

### Basic Usage

```python
import asyncio
from moss import MossClient, DocumentInfo, QueryOptions

async def main():
    # Initialize client
    client = MossClient("your-project-id", "your-project-key")
    
    # Create and populate an index
    documents = [
        DocumentInfo(id="1", text="Python is a programming language"),
        DocumentInfo(id="2", text="Machine learning with Python is popular"),
    ]
    
    await client.create_index("my-docs", documents)
    await client.load_index("my-docs")
    
    # Search
    results = await client.query(
        "my-docs",
        "programming language",
        QueryOptions(alpha=1.0),
    )
    for doc in results.docs:
        print(f"{doc.id}: {doc.text} (score: {doc.score:.3f})")

asyncio.run(main())
```

### Hybrid Search Controls

`alpha` lets you decide how much weight to give semantic similarity versus keyword relevance when running `query()`:

```python
# Pure keyword search
await client.query("my-docs", "programming language", QueryOptions(alpha=0.0))

# Mixed results (default 0.8 => semantic heavy)
await client.query("my-docs", "programming language")

# Pure embedding search
await client.query("my-docs", "programming language", QueryOptions(alpha=1.0))
```

Pick any value between 0.0 and 1.0 to tune the blend for your use case.

### Disk cache

Pass `cache_path` to persist the downloaded index to disk. Later loads reuse the
cached copy while the cloud version is unchanged, so restarts skip the download.
Auto-refresh writes through to the same cache. Each load still contacts the cloud
to check for a newer version.

```python
await client.load_index(
    "my-docs",
    auto_refresh=True,
    polling_interval_in_seconds=300,
    cache_path="/var/cache/moss",
)
```

Set `cache_path` once on the client to make it the default for every load. A
per-call `cache_path` overrides it, and both override the native default
(`~/.moss`). The chosen directory also holds the `.moss-device-id` file that
keys Monthly Active Device billing.

```python
client = MossClient(
    "your-project-id",
    "your-project-key",
    cache_path="/var/cache/moss",
)

# Uses /var/cache/moss.
await client.load_index("my-docs", auto_refresh=True)

# Overrides it for this load only.
await client.load_index("other-docs", cache_path="/tmp/moss")
```

### Offline-tolerant load

With a `cache_path` set and a snapshot already on disk, a load whose cloud
metadata check fails on a transport error (unreachable network, timeout) serves
the cached snapshot instead of failing, so a restart during an outage still
answers queries. The probe uses a few-second budget, not the full retry window,
and the load starts a refresh poller so the index self-heals when the cloud
returns. A real "index not found" (404) still fails, so a deleted index does not
resurrect from cache.

A load served this way opens the index, but a built-in embedding model cannot be
opened until the Moss cloud is reachable, so text queries with `alpha` above 0
fail until then. Keyword-only queries (`alpha=0.0`) and queries that pass their
own `embedding` keep working, and a later refresh or query warms the model once
the cloud returns.

`was_served_stale(name)` reports whether an index is currently served from such a
snapshot; it clears once a refresh reconfirms it against the cloud.

```python
await client.load_index("my-docs", cache_path="/var/cache/moss")
if await client.was_served_stale("my-docs"):
    # Serving a cached copy; the cloud was unreachable at load.
    ...
```

### Save a session to disk

`client.session(name)` opens a local session index. `save_to_disk(cache_path)`
writes it under `<cache_path>/<name>/`, and `load_from_disk(cache_path)` restores
it into a later session with the same name and returns the number of documents
loaded. Open that session with `auto_load_on_init=False`: it then skips the cloud
index load that the snapshot would replace, so the restore downloads no index. A
failed or interrupted save leaves the last saved snapshot loadable. A relative
`cache_path` resolves against the current working directory, and `~` is not expanded.

```python
session = await client.session("memory")
await session.add_docs([DocumentInfo(id="refund", text="Customer requested a refund")])
await session.save_to_disk("/var/cache/moss")
await session.close()

restored = await client.session("memory", auto_load_on_init=False)
await restored.load_from_disk("/var/cache/moss")
results = await restored.query("refund")
```

Without `cache_path`, `save_to_disk()` and `load_from_disk()` use
`sessions/<project id>/` under the first of these that is set:

1. the client's `cache_path` (`MossClient(..., cache_path=...)`)
2. the `MOSS_SESSION_CACHE_PATH` environment variable, which only session snapshots
   read: the index cache and the model cache ignore it
3. `moss` in the default cache directory: `~/.cache/moss` on macOS and Linux,
   `%LOCALAPPDATA%\moss` on Windows

A snapshot that an older core saved for a built-in model has no model artifact
identity. `load_from_disk` rebuilds it for a session opened with the same model:
the stored documents are re-embedded with the current model and the upgraded
snapshot is saved back, so the rebuild runs once per device. It needs the cloud
for the model. When the model cannot be loaded, it raises `MossError` with code
`MODEL_UNAVAILABLE` and changes nothing, so retry later. Pass
`rebuild_legacy=False` to load such a snapshot as a custom-model session, whose
queries need an explicit embedding.

### Multi-index search

Search several loaded indexes in one call and get the global top-K back, with
each result tagged by its source `index_name`. All indexes must be loaded
locally and share the same embedding model.

```python
loaded = await client.load_indexes(["products", "reviews"])
if not loaded.loaded:
    raise RuntimeError(f"no indexes loaded: {loaded.failed}")

results = await client.query_multi_index(
    loaded.loaded,
    "noise cancelling headphones",
    QueryOptions(top_k=5, alpha=0.5),
)
for doc in results.docs:
    print(f"[{doc.index_name}] {doc.id}: {doc.text} (score: {doc.score:.3f})")

await client.unload_indexes(loaded.loaded)
```

`alpha` works exactly as in `query()` (default 0.8): `1.0` is embedding-only,
`0.0` is keyword-only, and anything in between blends both with Reciprocal
Rank Fusion. Keyword scoring runs each index's own BM25 and merges each index's
raw hits before fusion; because BM25 statistics stay per-corpus, cross-index
keyword ranking is approximate. `top_k` caps the merged result, not each index,
and `filter` applies to every index. `load_indexes` is best-effort: names that
fail are reported in `failed` without rolling back the ones that loaded.

### Web sources

POST the existing `/v1/manage` web-source actions and return typed results.
Poll `job_id` with `get_job_status`. Set `MOSS_CLOUD_API_BASE_URL` to send manage calls
to a non-default host (defaults to `https://service.usemoss.dev`).

```python
created = await client.create_web_source(
    "https://docs.example.com",
    "knowledge-base",
    max_pages=200,
    refresh_cadence="weekly",
)
await client.get_job_status(created.job_id)

sources = await client.list_web_sources(index_name="knowledge-base")
source = await client.get_web_source(created.id)
updated = await client.update_web_source(created.id, refresh_cadence="daily")
# updated.job_id is set when resync=True enqueued a crawl.
resync = await client.resync_web_source(created.id)
deleted = await client.delete_web_source(created.id)
# deleted.purge_job_id is set when a purge was enqueued.
```

### Metadata filtering

You can pass a metadata filter directly to `query()` after loading an index locally:

```python
results = await client.query(
    "my-docs",
    "running shoes",
    QueryOptions(top_k=5, alpha=0.6),
    filter={
        "$and": [
            {"field": "category", "condition": {"$eq": "shoes"}},
            {"field": "price", "condition": {"$lt": "100"}},
        ]
    },
)
```

For a complete runnable example, see [`examples/python/metadata_filtering.py`](https://github.com/usemoss/moss/blob/main/examples/python/metadata_filtering.py).

### Load documents from JSON, text and markdown

`create_index`, `add_docs` and `SessionIndex.add_docs` take documents as `DocumentInfo` objects, dicts (or any `collections.abc.Mapping`) with the same fields, JSON text, or file paths:

```python
from pathlib import Path

await client.create_index("faqs", '[{"id": "1", "text": "Track your order in your account."}]')
await client.create_index("faqs-jsonl", Path("faqs.jsonl"))  # one JSON object per line
await client.add_docs("faqs", [{"id": "2", "text": "30-day returns.", "metadata": {"days": 30}}])
await client.create_index("handbook", [Path("docs/handbook.md"), Path("docs/faq.txt")])
```

- Each JSON object uses the `DocumentInfo` fields: `id`, `text`, and optional `metadata`, `embedding` and `payload`. Integer ids and number or boolean metadata values become strings. `$gt` and `$lt` filters still compare plain decimals as numbers; `$eq` and `$in` compare the stored string exactly, so store numbers you filter by equality as integers or strings (for example `30` or `"30"`, not `30.0`). Booleans are stored as `"true"` and `"false"`, so filter them with those strings (for example `{"$eq": "true"}`), not with Python `True`.
- `.txt`, `.md` and `.markdown` files are chunked natively so long files stay fully searchable. Chunk ids are `{path}#{n}` and each chunk's metadata has `parentId`. Markdown chunks start with their heading path, such as `Returns > Refunds`. Pass relative paths for stable ids. Use `create_index_from_files` for PDF and DOCX.
- Front matter at the top of a markdown file, from a first `---` line (not followed by a blank line) through the next `---` or `...` line outside a code fence, is not indexed, and markdown sections with no letters or digits, such as a lone `---` rule, produce no chunk.
- Pass `chunker=` to split text yourself. It runs on a worker thread for every document, files included, and must be synchronous:

```python
await client.create_index("kb", Path("notes.md"), chunker=lambda text: text.split("\n---\n"))
```

- `chunking=Chunking(...)` tunes the native chunker within bounds sized for the embedding model's input limit (about 512 tokens of English), with the names and limits of `ParseOptions`: `chunk_size` 200 to 2000 characters (default 1200), `chunk_overlap` 0 to half of `chunk_size` (default 200, capped at half of `chunk_size`), `mode="pages"` (packed sentences, default) or `"sentences"` (one sentence per chunk, no overlap), and `markdown_header_depth` 1 to 6 (deepest heading that starts a section, default 6). Out-of-range values raise `InvalidArgumentError`. With `chunking=`, `DocumentInfo`, dict and JSON input is chunked too. Pass `chunker` or `chunking`, not both:

```python
from moss import Chunking

await client.create_index("kb", Path("notes.md"), chunking=Chunking(chunk_size=800, chunk_overlap=100))
```

- Chunks from your own `chunker` may have at most 2,000 characters (about 512 tokens of English, the embedding model's input limit); a longer one raises `InvalidArgumentError` naming the document.
- Re-ingesting a file that now has fewer chunks leaves its old higher-numbered chunks in the index; remove them with `delete_docs`.
- A document's `payload` is copied onto every chunk, so its size is multiplied by the chunk count.
- There is no client-side batching. `create_index` uploads one blob and `add_docs` sends one request body, and the service can reject a very large one, which surfaces as `InvalidArgumentError`. As a guide, a 5 MB markdown file becomes about 5,000 chunks and about 6 MB of request body.
- Native chunking is tuned for English. A word longer than `chunk_size`, such as a long URL, is split into `chunk_size` pieces, so no text is dropped. Sentence ends are only `.`, `!` and `?`, and text in scripts without spaces, such as Chinese or Japanese, is split by length only; at the default `chunk_size` of 1200, a chunk of it exceeds the embedding model's 512-token limit, so pass a smaller `chunk_size` for such text.

## 🧠 Providing custom embeddings

Already using your own embedding model? Supply vectors directly when managing
indexes and queries:

```python
import asyncio

from moss import DocumentInfo, MossClient, QueryOptions


def my_embedding_model(text: str) -> list[float]:
    """Placeholder for your custom embedding generator."""
    ...


async def main() -> None:
    client = MossClient("your-project-id", "your-project-key")

    documents = [
        DocumentInfo(
            id="doc-1",
            text="Attach a caller-provided embedding.",
            embedding=my_embedding_model("doc-1"),
        ),
        DocumentInfo(
            id="doc-2",
            text="Fallback to the built-in model when the field is omitted.",
            embedding=my_embedding_model("doc-2"),
        ),
    ]

    await client.create_index("custom-embeddings", documents)  # Defaults to moss-minilm
    await client.load_index("custom-embeddings")

    results = await client.query(
        "custom-embeddings",
        "<query text>",
        QueryOptions(embedding=my_embedding_model("<query text>"), top_k=10),
    )

    print(results.docs[0].id, results.docs[0].score)


asyncio.run(main())
```

Leaving the model argument undefined defaults to `moss-minilm`.
Pass `QueryOptions` to reuse your own embeddings or to override `top_k` on a per-query basis.

> **Normalize your vectors.** Moss does not normalize caller-provided embeddings, so
> rankings match cosine similarity only when document and query vectors are unit
> length (L2-normalized). Hosted embedding APIs such as OpenAI return normalized
> vectors already; local models often do not. Un-normalized vectors still return
> results, but the order can differ from what you would compute with cosine similarity.

## Telemetry

The SDK always sends usage telemetry to the Moss cloud, and there is no option
to turn it off. It sends event types, your project id, index names, query and
document counts, query latencies, SDK and model versions, and a device id, which
is a random UUID stored on the device. Telemetry never includes query text,
document text, metadata, embeddings or file paths. Document text and embeddings
leave the device only when you create, add to or push an index in the cloud.

See [Telemetry](https://docs.moss.dev/docs/reference/telemetry) for every field and when it is sent.

## 📄 License

This package is licensed under the [PolyForm Shield License 1.0.0](./LICENSE.txt).

- ✅ Free for any use, including production and commercial use.
- ❌ Not permitted: providing a product that competes with Moss.
- 📩 For commercial licenses, contact: <contact@usemoss.dev>

## 📬 Contact

For support, commercial licensing, or partnership inquiries, contact us: [contact@usemoss.dev](mailto:contact@usemoss.dev)
