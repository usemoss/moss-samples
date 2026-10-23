# Moss JavaScript SDK Examples

This project demonstrates the usage of the Moss JavaScript SDK for semantic search and document indexing.

## Setup

1. **Install dependencies:**

   ```bash
   npm install
   ```

2. **Configure environment variables:**
   - Copy `.env.template` to `.env`
   - Fill in your Moss project credentials:

     ```env
     MOSS_PROJECT_ID=your_actual_project_id
     MOSS_PROJECT_KEY=your_actual_project_key
     MOSS_INDEX_NAME=your_existing_index_name
     ```

## Running Samples

### Comprehensive Sample

Run the complete end-to-end example showing all SDK functions:

```bash
npx tsx comprehensive_sample.ts
```

### Load and Query Sample

Run the simple example to load an existing index and perform queries:

```bash
npx tsx load_and_query_sample.ts
```

### Cached Index Loading Sample

Load an existing index with local filesystem caching. First run downloads from the cloud and saves to disk; subsequent runs load instantly from the cache:

```bash
npx tsx cached_load_sample.ts
```

### Custom Embedding Sample

Provision a fresh index (using the name supplied via `MOSS_INDEX_NAME`), push documents with manually generated OpenAI embeddings, and issue sample queries:

```bash
npx tsx custom_embedding_sample.ts
```

### Metadata Filter Operator Samples

Create a temporary index with metadata-rich product documents, load it locally,
run one filtered query, then delete the temporary index. Each script focuses on
one operator so the filter object is easy to copy into another app.

```bash
npm run metadata:eq
npm run metadata:and
npm run metadata:in
npm run metadata:near
```

### Session Sample

Open a local-first `SessionIndex`, add documents in real time (no cloud round trip), query the in-memory index, then `pushIndex` to the cloud so another agent or device can resume it. This is how Moss indexes a live conversation.

```bash
npx tsx session_sample.ts
```

### Session Cache Sample

Build a local-first `SessionIndex`, persist it to the local filesystem with `saveToDisk`, then restore it into a fresh session with `loadFromDisk` — so a session survives a process restart with no cloud round trip (no `pushIndex`). Also shows the client-level `cachePath` option (requires `@moss-dev/moss` >= 1.2.1).

```bash
npx tsx session_cache_sample.ts
```

### Session + Custom Authenticator Sample

Open a local-first session when the client is built with a custom `IAuthenticator` (short-lived tokens / delegated auth) instead of a static project key — the session authenticates through the same token source, so the project key never has to live on the device. Requires `@moss-dev/moss` >= 1.3.0.

```bash
npx tsx session_custom_auth_sample.ts
```

## Requirements

- Node.js (version 20 or higher)
- Valid Moss project credentials
