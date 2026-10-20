# Moss client library for JavaScript


`@moss-js/moss` enables **private, on-device semantic search** in your web, mobile, and edge applications - without cloud dependencies.

Built for developers who want **instant, memory-efficient, privacy-first AI features** inside their apps.

## ✨ Features

- ⚡ **On-Device Vector Search** - Sub-millisecond retrieval with zero network latency
- 🔍 **Semantic Search & Hybrid Search** - Beyond keyword matching
- 📦 **Multi-Index Support** - Manage multiple isolated search spaces
- 🛠️ **Tiny SDK** - Optimized for edge deployments
- 🛡️ **Privacy-First by Design** - No server-side cloud calls required to perform searches

## 📦 Installation

```bash
npm install @moss-js/moss
```

## 🚀 Quick Start

```typescript
import { MossClient, DocumentInfo } from "@moss-js/moss";

async function main() {
  // Initialize search client with project credentials
  const mossClient = new MossClient(
    "your-project-id",
    "your-project-key"
  );

  // Prepare documents to index
  const documents: DocumentInfo[] = [
    {
      id: "doc1",
      text: "How do I track my order? You can track your order by logging into your account.",
    },
    {
      id: "doc2", 
      text: "What is your return policy? We offer a 30-day return policy for most items.",
    },
    {
      id: "doc3",
      text: "How can I change my shipping address? Contact our customer service team.",
    },
    // Add more documents here
    // .
    // .
    // .
  ];

  try {
    // Create an index with documents and model
    const indexName = "faqs";
    const created = await mossClient.createIndex(
      indexName,
      documents
    ); // Defaults to the service's `moss-minilm` model when omitted
    console.log("Index created:", created);

    // Load the index before searching
    await mossClient.loadIndex(indexName);

    // Search the index
    const result = await mossClient.query(indexName, "How do I return a damaged product?", {
      topK: 3,
    });

    // Display results
    console.log(`Query: ${result.query}`);
    result.docs.forEach((match) => {
      console.log(`Score: ${match.score.toFixed(4)}`);
      console.log(`ID: ${match.id}`);
      console.log(`Text: ${match.text}`);
      console.log("---");
    });
  } finally {
    // Release the client's underlying resources once you're done with it
    await mossClient.close();
  }
}

main().catch(console.error);
```

To use a host-managed stable id for MAD billing while retaining Moss's own
device UUID for correlation:

```typescript
const mossClient = new MossClient("project", "key", {
  identity: { deviceId: "host-installation-id", userId: "optional-user-id" },
});
```

`deviceId` is billable. `userId` is optional and non-billable. Telemetry also
includes Moss's file-backed UUID as `mossDeviceId`; without a host id, both
device fields contain that Moss UUID.

## Telemetry

The SDK always sends usage telemetry to the Moss cloud, and there is no option
to turn it off. It sends event types, your project id, index names, query and
document counts, query latencies, SDK and model versions, and a device id: a
random UUID stored on the device, or the `identity.deviceId` you supply, plus
`identity.userId` when you set one. Telemetry never includes query text,
document text, metadata, embeddings or file paths. Document text and embeddings
leave the device only when you create, add to or push an index in the cloud.

See [Telemetry](https://docs.moss.dev/docs/reference/telemetry) for every field and when it is sent.

## Resource cleanup

`MossClient` and sessions returned by `client.session(...)` hold native resources that must be released explicitly. Call `close()` on each one when you are done with it, in a `finally` block or equivalent. `close()` is idempotent, so it is safe to call more than once.

`client.close()` also closes every live session created from that client. Closing a session individually first is fine; `close()` is idempotent on both.

On Node 24 and later, both `MossClient` and sessions implement `Symbol.asyncDispose`, so you can use `await using` instead of a manual `try/finally`:

```typescript
await using mossClient = new MossClient("your-project-id", "your-project-key");
// mossClient.close() is called automatically when it goes out of scope
```

## 🔥 Example Use Cases

- Smart knowledge base search
- Realtime Voice AI agents
- Personal note-taking search
- Private in-app AI features (recommendations, retrieval)
- Local semantic search in edge devices, AR/VR, mobile apps

## 🧠 Providing custom embeddings

Already using your own embedding model? Supply vectors directly when managing indexes:

```typescript
const documents = [
  {
    id: "doc-1",
    text: "Attach a caller-provided embedding",
    embedding: myEmbeddingModel("doc-1"),
  },
  {
    id: "doc-2",
    text: "Fallback to the built-in model when the field is omitted.",
  },
];

await mossClient.createIndex("custom-embeddings", documents);

await mossClient.loadIndex("custom-embeddings");

const results = await mossClient.query("custom-embeddings", "", {
  embedding: myEmbeddingModel("query"),
  topK: 10,
});
```

Leaving `modelId` undefined defaults to `moss-minilm`. You can still pass `{ modelId: "moss-mediumlm" }` or another supported identifier if you want the service to generate embeddings for documents without the optional `embedding` field.

> **Normalize your vectors.** Moss does not normalize caller-provided embeddings, so
> rankings match cosine similarity only when document and query vectors are unit
> length (L2-normalized). Hosted embedding APIs such as OpenAI return normalized
> vectors already; local models often do not. Un-normalized vectors still return
> results, but the order can differ from what you would compute with cosine similarity.

### Foundation model identity

Moss generates local query embeddings for a foundation-model index only when
the service supplies the exact immutable model artifact identity used to build
that index. This prevents a query from being embedded with different model
bytes than the stored document vectors.

Fresh local sessions using `moss-minilm`, `moss-mediumlm`, or `moss-litelm`
bind that model's official current artifact automatically before model warmup.
Caller-supplied artifact identities are validated and kept, while custom models
are never auto-bound. `saveToDisk` records the exact model id, artifact version,
and manifest SHA-256, so the same session can be restored and queried with raw
text:

```typescript
const first = await mossClient.session("memory");
await first.addDocs([{ id: "refund", text: "Customer requested a refund" }]);
await first.saveToDisk(cachePath);
await first.close();

const restored = await mossClient.session("memory");
await restored.loadFromDisk(cachePath);
const results = await restored.query("refund");
```

Without `cachePath`, `saveToDisk()` and `loadFromDisk()` use `sessions/<project id>/`
under the first of these that is set:

1. the client's `cachePath` option (`new MossClient(id, key, { cachePath })`)
2. the `MOSS_SESSION_CACHE_PATH` environment variable, which only session snapshots
   read: the index cache and the model cache ignore it
3. `moss` in the default cache directory: `~/.cache/moss` on macOS and Linux,
   `%LOCALAPPDATA%\moss` on Windows

A relative `cachePath` resolves against the current working directory, and `~` is not expanded.

Session caches created by older SDKs without an artifact version and manifest
SHA-256 load as `custom` sessions through the legacy fail-closed path. Their raw
text queries require an explicit caller-generated embedding. Rebuild those
caches from their source documents with the current SDK, then save them again
so the automatically bound foundation identity is persisted.

Older indexes without that identity still load and remain queryable, but the
query must include a caller-generated vector of the correct dimension:

```typescript
const results = await mossClient.query("legacy-index", "search text", {
  embedding: myEmbeddingModel("search text"),
  topK: 10,
});
```

If the vector is omitted, the query fails closed with an error stating that an
explicit query embedding is required. Moss does not silently fall back to an
unverified local model or send the query to the cloud.

## Offline-tolerant load

With a `cachePath` set and a snapshot already on disk, a `loadIndex` whose cloud
metadata check fails on a transport error (unreachable network, timeout) serves
the cached snapshot instead of failing, and starts a refresh poller so the index
catches up when the cloud returns. A real "index not found" (404) still fails,
so a deleted index does not come back from cache.

A load served this way opens the index, but a built-in embedding model cannot be
opened until the Moss cloud is reachable, so text queries with `alpha` above 0
fail until then. Keyword-only queries (`alpha: 0`) and queries that pass their
own embedding keep working.

```typescript
await mossClient.loadIndex("my-docs", { cachePath: "/var/cache/moss" });
```

## Multi-index search

Search several loaded indexes in one call and get the global top-k back, with
each result tagged by its source `indexName`. All indexes must be loaded
locally and share the same embedding model.

```typescript
const { loaded, failed } = await mossClient.loadIndexes(["products", "reviews"]);
if (loaded.length === 0) {
  throw new Error(`No indexes loaded: ${JSON.stringify(failed)}`);
}

const results = await mossClient.queryMultiIndex(
  loaded,
  "noise cancelling headphones",
  { topK: 5, alpha: 0.5 },
);
for (const doc of results.docs) {
  console.log(`[${doc.indexName}] ${doc.id}: ${doc.text} (score: ${doc.score.toFixed(3)})`);
}

await mossClient.unloadIndexes(loaded);
```

`alpha` works exactly as in `query` (default 0.8): `1.0` is embedding-only,
`0.0` is keyword-only, and anything in between blends both with Reciprocal
Rank Fusion. Keyword scoring runs each index's own BM25 and merges each index's
raw hits before fusion; because BM25 statistics stay per-corpus, cross-index
keyword ranking is approximate. `topK` (default 10) caps the merged result, not
each index, and `filter` applies to every index. `loadIndexes` is best-effort:
names that fail are reported in `failed` without rolling back the ones that
loaded.

## Web sources

POST the existing `/v1/manage` web-source actions and return typed results.
Poll `jobId` with `getJobStatus`. Set `MOSS_CLOUD_API_BASE_URL` to send manage calls
to a non-default host (defaults to `https://service.usemoss.dev`).

```typescript
const created = await mossClient.createWebSource(
  "https://docs.example.com",
  "knowledge-base",
  { maxPages: 200, refreshCadence: "weekly" },
);
await mossClient.getJobStatus(created.jobId);

const sources = await mossClient.listWebSources("knowledge-base");
const source = await mossClient.getWebSource(created.id);
const updated = await mossClient.updateWebSource(created.id, {
  refreshCadence: "daily",
});
// updated.jobId is set when resync: true enqueued a crawl.
const resync = await mossClient.resyncWebSource(created.id);
const deleted = await mossClient.deleteWebSource(created.id);
// deleted.purgeJobId is set when a purge was enqueued.
```

## Metadata filtering

You can pass a metadata filter in `query` options after loading an index locally:

```typescript
const results = await mossClient.query("my-docs", "running shoes", {
  topK: 5,
  alpha: 0.6,
  filter: {
    $and: [
      { field: "category", condition: { $eq: "shoes" } },
      { field: "price", condition: { $lt: "100" } },
    ],
  },
});
```

## 📄 License

This package is licensed under the [PolyForm Shield License 1.0.0](./LICENSE.txt).

- ✅ Free for any use, including production and commercial use.
- ❌ Not permitted: providing a product that competes with Moss.
- 📩 For commercial licenses, contact: <contact@inferedge.dev>

## 📬 Contact

For support, commercial licensing, or partnership inquiries, contact us: [contact@inferedge.dev](mailto:contact@inferedge.dev)
