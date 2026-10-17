# Moss client library for Python

`moss` enables **private, on-device semantic search** in your Python applications with cloud storage capabilities.

Built for developers who want **instant, memory-efficient, privacy-first AI features** with seamless cloud integration.

## ✨ Features

- ⚡ **On-Device Vector Search** - Sub-millisecond retrieval with zero network latency
- 🔍 **Semantic, Keyword & Hybrid Search** - Embedding search blended with Keyword matching
- ☁️ **Cloud Storage Integration** - Automatic index synchronization with cloud storage
- 📦 **Multi-Index Support** - Manage multiple isolated search spaces
- 🛡️ **Privacy-First by Design** - Computation happens locally, only indexes sync to cloud
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

## 🔥 Example Use Cases

- Smart knowledge base search with cloud backup
- Realtime Voice AI agents with persistent indexes
- Personal note-taking search with sync across devices
- Private in-app AI features with cloud storage
- Local semantic search in edge devices with cloud fallback

## Available Models

- `moss-minilm`: Lightweight model optimized for speed and efficiency
- `moss-mediumlm`: Balanced model offering higher accuracy with reasonable performance
- `custom`: Bring your own embeddings (BYOE) — supply pre-computed vectors via `DocumentInfo(embedding=...)`

## 🔧 Getting Started

### Prerequisites

- Python 3.10 or higher
- Valid Moss project credentials

### Environment Setup

1. **Install the package:**

```bash
pip install moss
```

2. **Get your credentials:**

Sign up at [moss.dev](https://moss.dev) to get your `project_id` and `project_key`.

3. **Set up environment variables (optional):**

```bash
export MOSS_PROJECT_ID="your-project-id"
export MOSS_PROJECT_KEY="your-project-key"
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

### Metadata filtering

You can pass a metadata filter directly to `query()` after loading an index locally:

```python
results = await client.query(
    "my-docs",
    "running shoes",
    QueryOptions(
        top_k=5,
        alpha=0.6,
        filter={
            "$and": [
                {"field": "category", "condition": {"$eq": "shoes"}},
                {"field": "price", "condition": {"$lt": "100"}},
            ]
        },
    ),
)
```

For a complete runnable example, see [`examples/python/metadata_filtering.py`](../../examples/python/metadata_filtering.py).

### Reranking (High Precision)

If you need higher precision at the top of the result list than first-stage retrieval gives, you can enable the optional local cross-encoder reranker.

When `rerank=True` is provided, Moss will fetch a larger pool of candidates (`rerank_top_k`, default 50) and locally re-score them using a `sentence-transformers` cross-encoder before returning the final `top_k` results.

First, install the optional dependencies:
```bash
pip install 'moss[rerank]'
```

Then, enable it in your query:
```python
results = await client.query(
    "my-docs",
    "How to process a refund?",
    QueryOptions(
        top_k=5, 
        rerank=True, 
        rerank_top_k=50, # Optional: number of candidates to fetch for reranking
        # rerank_model="cross-encoder/ms-marco-MiniLM-L-6-v2" # Optional override
    ),
)
```

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

## 📄 License

[BSD 2-Clause License](./LICENSE)

