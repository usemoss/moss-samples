# Changelog

## [1.0.0] - 2026-03-29

First stable release of the `moss` Python SDK (previously published as `inferedge-moss`).

**Import path changed:** `from moss import MossClient` (was `from inferedge_moss import ...`)

### Features

- **Semantic search** with built-in on-device models (`moss-minilm`, `moss-mediumlm`); embedding computation runs in Rust for speed; custom embeddings supported via `QueryOptions.embedding`
- **Hybrid search** with keyword + semantic search and configurable alpha blending
- **Metadata filtering** on locally loaded indexes with rich operators (`$eq`, `$ne`, `$gt`, `$gte`, `$lt`, `$lte`, `$in`, `$nin`, `$and`, `$or`, `$near` for geo-distance)
- **Cloud query fallback**: `query()` automatically falls back to the cloud API when the index is not loaded locally
- **Hot reload & auto-refresh**: `load_index()` supports `auto_refresh` with configurable polling interval to detect and reload updated indexes
- **Async bulk index pipeline**: binary upload, server-side build, poll until completion
- **Index mutations**: `create_index`, `add_docs`, `delete_docs` return `MutationResult` with `job_id`, `index_name`, `doc_count`
- **Multi-index support** for isolated search spaces
- **Metrics & tracing hooks**: Opt-in `on_query` callbacks on `MossClient` and `query()` emit `QueryMetrics` with execution latency, document counts, local vs. cloud routing, and error status to user-provided sinks
- **Python 3.10 to 3.14** supported

## [1.0.0-beta.19] - 2026-03-24

- Updated `inferedge-moss-core` dependency to `0.8.7`
- Telemetry improvements
- Embedding computation for built-in models (`moss-minilm`, `moss-mediumlm`) now runs in Rust; custom embeddings continue to be supported via `QueryOptions.embedding`
- Fixed `list_indexes()` failing when the cloud API returns `null` for certain `IndexInfo` fields on indexes created by older SDK versions

## [1.0.0-beta.18] - 2026-03-12

- Telemetry improvements

## [1.0.0-beta.17] - 2026-02-26

### Added
- **Metadata Filtering**: `query()` now accepts an optional `filter` dict to narrow results by document metadata on locally loaded indexes
  - Comparison operators: `$eq`, `$ne`, `$gt`, `$gte`, `$lt`, `$lte`
  - Set operators: `$in`, `$nin`
  - Composable with `$and` / `$or` for complex predicates (supports arbitrary nesting)
  - Numeric coercion: int and float filter values are automatically converted to strings for consistent matching
- **Geo-distance filtering**: new `$near` operator filters documents by haversine distance from a `"lat,lng,radiusMeters"` value
- When `filter` is passed to `query()` but the index is not loaded locally, a warning is logged and the filter is skipped (cloud query API does not yet support filtering)
- Updated `inferedge-moss-core` dependency to `0.6.0`

## [1.0.0-beta.16] - 2026-02-23

- Bumped `inferedge-moss-core` dependency to `0.5.0` to support index telemetry and `push_index` improvements

## [1.0.0-beta.15] - 2026-02-17

- All index mutations and reads now go through the Rust ManageClient, replacing the Python HTTP layer
- Index creation uses an async bulk pipeline: binary upload → server-side build → poll until completion
- `load_index` supports both V1 and V2 binary formats, with cloud query fallback when index isn't loaded locally
- New return type `MutationResult` (with `job_id`, `index_name`, `doc_count`) for `create_index`, `add_docs`, `delete_docs`
- `get_docs` takes `doc_ids` directly instead of wrapping in `GetDocumentsOptions`

## [1.0.0-beta.14] - 2026-02-06

- Query latency reduced from ~2,300ms to ~10ms for 100K vectors
- Optimized search pipeline reducing memory allocations
- Significantly reduced memory overhead for large indexes (100K+ documents) in the context of hybrid search (keyword + semantic)
- Enhanced performance across all index sizes

## [1.0.0-beta.13] - 2026-02-02

### Added
- **Hot Reload & Auto-Refresh**: Indexes can now automatically detect and reload when updated in the cloud.
  - `load_index()` now accepts optional `auto_refresh` and `polling_interval_in_seconds` parameters
  - When `auto_refresh` is enabled, the SDK polls for updates at the configured interval (default: 600 seconds)
  - To stop auto-refresh, call `load_index()` again without the `auto_refresh` option
- `load_index()` now allows reloading an already-loaded index (previously threw an error)
- Index management now uses Rust core for improved performance and reliability

## [1.0.0-beta.12] - 2026-01-30

- Adds partial support for Python 3.14 by disabling local embedding service functionality. Full support coming soon.

## [1.0.0-beta.11] - 2026-01-29

- Adds support for user-supplied embeddings.
- `query()` now automatically falls back to the cloud API when the index is not loaded locally, enabling queries without requiring `load_index()` first.
- Adds better scoring evaluation for search results

## [1.0.0-beta.10] - 2026-01-26

- Removes the '<2' upper bound on numpy dependency. 

## [1.0.0-beta.9] - 2026-01-14

- Drops support for Python 3.9 and below.
- Bug fix: Keyword search now functions correctly after `load_index()`.
- New service endpoint with significant infrastructure upgrades. Management operations are now ~3× faster across most real-world use cases, providing faster index operations while also supporting larger payloads.

## [1.0.0-beta.8] - 2025-12-15

- Updates `inferedge-moss-core` dependency to version 0.2.3 for new ARM64 wheel support.

## [1.0.0-beta.7] - 2025-12-01

Adds IntelliSense support in all the IDEs

## [1.0.0-beta.6] - 2025-11-29

Adds support for keyword search and alpha blending between keyword and semantic search.

## [1.0.0-beta.5] - 2025-10-23

Removes Pipecat integration and MossContextRetriever from the SDK. Will be offered as a pipecat extension instead soon.

## [1.0.0-beta.4] - 2025-10-09

Performance improvements for query() calls.

## [1.0.0-beta.3] - 2025-10-09

### New Features

- **MossContextRetriever**: Added Pipecat integration for real-time voice AI applications
  - Automatically enhances LLM conversations with semantic search results from Moss indexes
  - Seamless integration with OpenAI LLM context frames

## [1.0.0-beta.1] - 2025-09-14

Initial release of inferedge-moss with core features:

- Semantic search using transformer-based embeddings
- Lightweight embedding models for edge computing; supports proprietary "moss-minilm" model
- API key validation with secure host access
- Cloudflare CDN support for fast model loading
- Multi-index support for isolated search spaces
- Add, update, and remove items across indexes
- Query interface with configurable result count
- Performance metrics tracking
