# Changelog

## [Unreleased]

## [1.19.0] - 2026-10-20

### Added

- The package metadata declares its license, PolyForm Shield 1.0.0, as `LicenseRef-PolyForm-Shield-1.0.0`, so PyPI and license scanners show it.
- The `inferedge-moss-core` wheels carry `LICENSE-THIRD-PARTY.txt`, the license and copyright notices of the third-party code the extension links: the Rust crates of that target, ONNX Runtime and the components it includes, and the Rust standard library.
- `SessionIndex.save_to_disk` and `load_from_disk` take `cache_path` as optional. Without one, or with an empty one, snapshots go in `sessions/<project id>/` under the client's `cache_path`, else under the `MOSS_SESSION_CACHE_PATH` environment variable, which only session snapshots read, else under `moss` in the default cache directory: `~/.cache/moss` on macOS and Linux, `%LOCALAPPDATA%\moss` on Windows. A directory you pass is used as before.

### Changed

- Requires `inferedge-moss-core` 0.33.0.
- The custom embeddings section of the README says to L2-normalize the vectors you provide. Thanks @VeshRaazThapa (usemoss/moss#529).
- `inferedge-moss-core`, the native runtime of `moss`, is not supported for direct use, and its `moss_core` module no longer exports `Index`. Import every Moss type from `moss`. No change to the `moss` API.
- `SessionIndex.add_docs` on a session with a built-in model embeds the documents in batches of at most 512 padded tokens instead of 8,192, and tokenizes each batch on the thread that embeds it. Each model session runs 2 inference threads on a desktop or server host (macOS, Linux or Windows) with 8 or more cores, and 1 on a smaller host, on Android and iOS, and for `moss-litelm`. Idle threads sleep instead of spinning. Embedding many documents needs less memory, and on a host that runs 2 threads it takes less time. Text queries on other sessions with the same model stay fast while it runs. `MOSS_EMBEDDING_INTRA_OP_THREADS` still sets the thread count on every platform.
- `moss-litelm` embeds each document in its own batch, so a document's vector equals the vector of its text embedded alone. Embedded in a batch, its vectors used to differ from that, with a cosine similarity as low as 0.989.

### Fixed

- Deleting a `MossClient` or `SessionIndex` waits at most 100 ms for a DNS lookup still in progress. It used to hold the GIL until DNS gave up.

## [1.18.0] - 2026-10-14

### Added

- `MossClient.create_index`, `MossClient.add_docs` and `SessionIndex.add_docs` take documents as dicts (or any `collections.abc.Mapping`), JSON array or JSON Lines text, or `.json`, `.jsonl`, `.ndjson`, `.txt`, `.md` and `.markdown` file paths, as well as `DocumentInfo` objects. Text and markdown files are chunked natively into documents `{path}#{n}` with metadata `parentId`. A word longer than `chunk_size` (1200 by default), such as a long URL or a run of text without spaces, is split into `chunk_size` pieces, so no text is dropped. Markdown front matter (a first `---` line through the next `---` or `...` line) is not indexed.
- A keyword-only `chunker` argument on the same methods splits every document's text with your own function. Pass `chunker` or `chunking`, not both: using both raises `TypeError`. Neither can be used with `model_id="custom"`.
- `moss.Chunking` and a keyword-only `chunking` argument on the same methods tune the native chunker within the embedding model's limits, with the names and limits of `ParseOptions`: `chunk_size` 200 to 2000 characters (default 1200), `chunk_overlap` 0 to half of `chunk_size` (default 200, capped at half of `chunk_size`), `mode` `"pages"` or `"sentences"`, and `markdown_header_depth` 1 to 6. With `chunking`, `DocumentInfo`, dict and JSON input is chunked too, not only text and markdown files. Out-of-range values raise `InvalidArgumentError` with `ParseOptions`-style messages, such as `Unsupported chunk_size 100. Supported: 200 to 2000`. Chunks from a user `chunker` longer than 2,000 characters raise `InvalidArgumentError`.
- `moss.DocsInput`, `moss.Chunker` and `moss.Chunking` are new exports.

### Changed

- Requires `inferedge-moss-core` 0.32.0, which adds `moss_core.parse_documents_json` and `moss_core.to_document_infos`.

### Fixed

- The type stub declares `MossClient.create_index_from_files`, `ParseFileInput` and `ParseOptions`, and its `__all__` lists them and `ParentGrouping`. It also declares `SearchResult.model_id`, `IndexStatus.value` and the `JobPhase.CRAWLING` and `JobPhase.PARSING_DOCUMENTS` phases, types `create_index(..., wait=flag)` for a `bool` flag, and declares fields that are read-only at runtime, such as `MutationResult.job_id` and `SessionIndex.name`, as read-only properties. The `LoadIndexesResult` arguments no longer accept `None`, which the core refuses. No runtime change.
- The type stub marks the classes of the native core, such as `DocumentInfo` and `QueryOptions`, final, since Python cannot subclass them, and declares their constructors with `__new__`, as the core defines them. No runtime change.

## [1.17.0] - 2026-10-14

### Added

- `ParseOptions.chunk_size` (200 to 2000 characters, default 1200) and `ParseOptions.chunk_overlap` (0 to half of `chunk_size`, default 200 capped at half of `chunk_size`) control how the parse pipeline splits extracted text. Out-of-range values raise `InvalidArgumentError` before any upload.

### Changed

- Requires `inferedge-moss-core` 0.31.0.

## [1.16.1] - 2026-10-13

### Changed

- Requires `inferedge-moss-core` 0.30.1.

### Fixed

- `MossClient.query`, `query_multi_index`, `unload_index`, `unload_indexes` and `was_served_stale` release the GIL while they run, so the event loop keeps running other tasks during a query or while an unload waits for one.

## [1.16.0] - 2026-10-12

### Added

- `SessionIndex.save_to_disk(cache_path)` and `SessionIndex.load_from_disk(cache_path, *, rebuild_legacy=True)` save a session to disk and restore it. `save_to_disk` writes the session under `<cache_path>/<name>/`, and a failed or interrupted save leaves the last saved snapshot loadable. `load_from_disk` restores it into a session with the same name and returns the number of documents loaded, and the session takes the snapshot's model. A session that already loaded the same model keeps it instead of loading it again. A missing or damaged snapshot raises `MossError` with code `DESERIALIZATION` and leaves the session as it was. A snapshot that an older core saved for a built-in model has no model artifact identity: by default `load_from_disk` rebuilds it for a session opened with the same model, re-embedding the stored documents and saving the snapshot back in the same call, which needs the cloud for the model. When the model cannot be loaded it raises `MossError` with code `MODEL_UNAVAILABLE` and changes nothing. `rebuild_legacy=False` loads such a snapshot as a custom-model session. Code that calls `load_from_disk` on the private `SessionIndex._inner` gets no rebuild unless it passes `rebuild_legacy=True`; the public method rebuilds by default.
- `MossClient.session(name, auto_load_on_init=False)` opens the session without loading the cloud index of that name. The session starts empty with the given model, so `load_from_disk` restores a saved session with no index download. A `push_index` before any load replaces the cloud index with the session's documents.
- `SessionIndex.model_id`, the embedding model the session uses, or `"custom"`. A load moves the session to the loaded model, and `add_docs` and `query` read it on every call. Reading it never waits for a call in progress, and it still reads after `close()`.

### Changed

- Requires `inferedge-moss-core` 0.30.0.
- `SessionIndex.add_docs` and `delete_docs` update the keyword index in place instead of rebuilding it, and loads build it in one pass. Scores are unchanged.
- **Behavior change:** `SessionIndex.add_docs` checks every document of a call first, so a call with a vector whose length differs from the session's vectors raises `InvalidArgumentError` and adds nothing.
- `SessionIndex` keeps one copy of each document, and adds and loads move documents into the index instead of copying them.
- The token cache keeps a token until 60 seconds before it expires or for 90% of its life, whichever is later, so short-lived tokens are cached too.
- A 401 drops only the token it rejected from the cache, and a refused telemetry request keeps the token.
- A project key session fetches one token for its requests and its telemetry.

### Fixed

- `MossClient.session` moves the session to the model of an existing cloud index that has no documents, as it does for one with documents. Without `model_id`, a session on an empty custom-model index opens and takes embeddings instead of raising `InvalidArgumentError` while it warms the default model, and an explicit `model_id` the index does not use raises `ValueError`.
- When `MossClient.session` raises, it closes the session it opened, so the session's final telemetry is sent and its native memory freed then, not at `MossClient.close`.

## [1.15.1] - 2026-10-06

### Fixed

- `SessionIndex.push_index()` on a session with a built-in model (`moss-minilm`, `moss-mediumlm`, `moss-litelm`) sends that model's id, so the service re-embeds the text with it and the pushed index loads and answers text queries like one built with `create_index`. It used to be stamped `custom`, so a pushed session could not be resumed with text queries. A custom-model session still pushes its own embeddings. Requires `inferedge-moss-core` 0.28.1.

## [1.15.0] - 2026-10-05

### Added

- `MossClient.close()` and `SessionIndex.close()`, and both work as `with` and `async with` context managers. `close()` sends the final usage telemetry, waiting until it is delivered or 2 seconds pass, and frees the native memory; `MossClient.close()` also closes the sessions the client opened. Afterwards every `MossClient` method raises `RuntimeError("MossClient is closed")` and every `SessionIndex` method but `name` raises `InvalidArgumentError`. Requires `inferedge-moss-core` 0.27.0.
- `moss.MossError`, a `RuntimeError` subclass raised for every failure the native core reports. `code` is a stable string to branch on: `INVALID_ARGUMENT`, `NOT_FOUND`, `UNAUTHORIZED`, `NETWORK`, `DESERIALIZATION`, `MODEL_UNAVAILABLE` or `INTERNAL`. `moss.InvalidArgumentError` is the `INVALID_ARGUMENT` subclass and is also a `ValueError`. `detail` holds the core error text in released wheels too: diagnostic text for logs and support, at most 512 bytes, and not a stable contract. Requires `inferedge-moss-core` 0.27.0.
- `LoadIndexesResult.failed_codes` maps each index that `load_indexes` could not load to its code, such as `"NOT_FOUND"`. Requires `inferedge-moss-core` 0.27.0.

### Changed

- `MossError.detail` carries no request URL for a cloud or model download error: a cloud timeout, retry or response parse failure names the operation, such as `get_index_info`, and a model download names only the host. Cache, repair, snapshot and `MOSS_CA_BUNDLE` errors name the file, not its absolute path. Parser text from `.moss` payloads and from release and manifest files goes to the debug log, and ONNX Runtime and tokenizer failures give fixed text. A failed response contributes only its HTTP status and the error code its body names, such as `HTTP 403 Forbidden: AccessDenied` from the object store or `HTTP 409 Conflict: INDEX_EXISTS` from the Moss service, never the rest of the body. A `.moss` payload whose JSON does not parse, or whose document count does not match its header, gives the detail `index payload is malformed`; header and length errors keep their own short text, such as `binary data truncated`. A lock left unusable by an earlier panic raises `MossError` with code `INTERNAL` and the detail `internal state is unavailable after an earlier failure`, also when an embedding model load hits it.
- `MossError.detail` names a numbered fault for a damaged on-device vector file or session snapshot, such as `fault 1028` for a vector count that differs from the snapshot metadata, and no longer describes the file layout or the snapshot files.
- **Behavior change:** error messages from the native core are fixed text per kind of failure, such as `Index not found.` or `The Moss service could not be reached.`, and no longer carry URLs, file paths or index names. Code that matched on message text should branch on `MossError.code`. A failed `load_index` or `unload_index` now raises the core's `MossError` directly instead of wrapping it in a `RuntimeError` that names the index. A text query on an index that cannot embed it (a custom-embedding index, or a foundation index without an artifact identity) raises `InvalidArgumentError`, still a `ValueError`, with the core's message. The reasons in `load_indexes().failed` are the same fixed messages. `query` on an index that is not loaded raises `MossError` with code `NOT_FOUND`, still a `RuntimeError`, and its message still names the load call.
- **Behavior change:** only `INVALID_ARGUMENT` failures are still a `ValueError`. These session failures were `ValueError` and are now a `MossError` (a `RuntimeError`) with the code shown: a rejected project key when opening a session (`UNAUTHORIZED`), a service or network failure when opening one (`NETWORK` or another cloud code), a model that cannot be downloaded or loaded during `add_docs` or `query` with text (`MODEL_UNAVAILABLE`), and an embedding failure during those calls (`INTERNAL`). Code that catches `ValueError` around these calls should catch `MossError` as well.
- Built-in model loads (`moss-minilm`, `moss-mediumlm`, `moss-litelm`) are faster, most of all on arm64. No API change. Requires `inferedge-moss-core` 0.27.0.
- `SessionIndex.add_docs` on a session with a built-in model embeds the documents in batches of at most 8,192 padded tokens, grouped by length, instead of one batch padded to the longest document. Large calls need far less memory and time: on an Apple M2, 5,000 short captions in one call took about 20 s with a 0.6 GB peak instead of about 119 s and 9.1 GB. A query embedding for the same model waits for one batch instead of the whole call. Embeddings come back in input order, with the same values to about 1e-7. Requires `inferedge-moss-core` 0.27.0.
- **Behavior change:** a malformed `$near` filter value is rejected with a `ValueError` naming the expected `"lat,lng,maxDistanceMeters"` format instead of matching nothing.
- **Breaking change:** `$gt`, `$gte`, `$lt` and `$lte` compare two plain decimals (`"42"`, `"-3.5"`) as numbers and two other values as text, and never match a plain decimal against any other value. Zero padded numbers such as `"07"` and forms such as `"1e3"` or `"NaN"` are text, so `"07"` no longer matches `$gt: "5"` and `"naming"` never matches `$gt: "999999"`. Sorting `get_docs` by a field (`sort_by`) and assembling a `ParentGrouping` by `order_field` put decimals first in numeric order, zero padded ones included, so `"099"` sorts before `"100"`, then every other value in text order, forms such as `"1e3"` or `"NaN"` included. A condition still never matches a document that lacks the field, `$ne` and `$nin` included.
- Filter validation and ordering come from `inferedge-moss-core` 0.27.0.
- **Behavior change:** `query_multi_index([])` and `query` without an embedding on a custom-model session raise `InvalidArgumentError`, still a `ValueError`, with code `INVALID_ARGUMENT`. A malformed metadata filter that raised a plain `ValueError` raises `InvalidArgumentError` with the same text; a filter value of the wrong type still raises `TypeError`. `InvalidArgumentError.code` is `"INVALID_ARGUMENT"` on the class too.
- A load with a cache path that finds no usable snapshot while the Moss service is unreachable reports `NETWORK` instead of `DESERIALIZATION`. An auth URL that answers 404 or 410 reports `INTERNAL` instead of `NOT_FOUND`. A refused index name keeps the naming rule as its message, and a file with an unsupported content type reads `A file has an unsupported content type.` A text call on a session whose model cannot embed raises `InvalidArgumentError` with the message `This session's model cannot embed text. Pass embeddings with the documents and the query.`
- `IndexManager.query` with an empty query embedding runs keyword-only at `alpha` 0, as `query_multi_index` does, and raises `InvalidArgumentError` at a higher `alpha` on an index that holds vectors.

### Fixed

- Usage telemetry that fails to upload is retried on the next flush, every event under a stable `eventId`, for up to an hour and 20,000 events, instead of being dropped. A client or session garbage collected without `close()` blocks for at most 500 ms on its final flush instead of without limit. Requires `inferedge-moss-core` 0.27.0.
- `load_index` with `auto_refresh=True` compares `updatedAt` as a point in time, so two spellings of one instant are no change, and a tick that finds a new snapshot fetches the index metadata once instead of twice. After a `load_index` served stale from `cache_path`, the first auto refresh that reaches the cloud warms the embedding model even when the snapshot is unchanged. Requires `inferedge-moss-core` 0.27.0.
- A query whose stored vectors have another length than the query raises `MossError` with code `INTERNAL` instead of ranking those documents with score 0. `Index.serialize` in `inferedge-moss-core` raises `ValueError` for a vector it cannot read. Requires `inferedge-moss-core` 0.27.0.

## [1.14.0] - 2026-09-29

### Added

- `MossClient(cache_path=...)` sets a client-level default `cache_path` for `load_index` / `load_indexes`, the directory for the on-disk index cache and the `.moss-device-id` file. A per-call `cache_path` overrides it. With neither, indexes are not cached on disk and the device id stays in `~/.moss`. Parity with the JS SDK's `MossClientOptions.cachePath`.
- Offline-tolerant `load_index` and `load_indexes`. With a `cache_path` and a snapshot already on disk, a load whose cloud metadata check cannot reach the cloud, times out, or gets a 408, 429, 500, 502, 503 or 504 (only a 408, 429, 500 or 503 from the auth service) serves the cached snapshot instead of failing, probes the cloud with a few-second budget rather than the full retry window, and starts a refresh poller so the index self-heals when the cloud returns. A 401, 403 or real 404 still fails, so a forbidden or deleted index does not resurrect from cache. A snapshot written by 1.13.0 or earlier is not served until the index is downloaded again, which happens when the cloud copy changes. A snapshot fetched under another project or cloud origin is never served. `MossClient.was_served_stale(name)` reports whether an index is currently served from such a snapshot. The index loads, but a built-in embedding model cannot be opened until the Moss cloud is reachable, so text queries with `alpha` above 0 fail until then. Keyword-only queries (`alpha == 0`) and queries that pass their own `embedding` keep working, and a later refresh or query warms the model once the cloud returns. Requires `inferedge-moss-core` 0.26.0 (`was_served_stale` on `IndexManager`).
- `QueryOptions.min_score` drops results whose `score` is below it; a query returns up to `top_k` results that clear it, in hybrid order. It takes a value from 0 to 1; anything else raises an error. Keyword-only queries (`alpha == 0`) and queries on indexes that hold no vectors have no embedding to score against, so `min_score` on them raises a clear error. Works in `query` and `query_multi_index`; `SessionIndex.query` ignores it.
- `QueryOptions.candidate_depth` sets how many hits a hybrid query ranks on each signal (vector and keyword) before fusion. A hit outside both lists is never returned, so a deeper list raises recall and query time. Left unset, a hybrid query looks `2 * top_k` deep, as before. A set value must be at least 1 (0 raises an error) and is raised to `top_k` when below it. Keyword-only and vector-only queries (`alpha` 0 or 1) ignore it and rank `top_k` hits, since a deeper list returns the same results. Works in `query` and `query_multi_index`; `SessionIndex.query` ignores it. Requires `inferedge-moss-core` 0.26.0.

### Changed

- **Behavior change:** `score` is the result's relevance to the query from 0 to 1, in `query`, `query_multi_index` and `SessionIndex.query` alike. Results keep their hybrid order, so a lower-ranked result can show a higher score. Scores depend on the embedding model: tune `min_score` on your own queries. Keyword-only queries (`alpha == 0`) score every result 0.0. Code that relied on the top result scoring about 1.0, or on multi-index `alpha=1.0` scores being raw similarity values, needs updating.
- **Behavior change:** a query `embedding` whose length differs from the index dimension raises at `alpha` 0 as it does above 0; it used to be ignored at 0. An empty `embedding=[]` counts as wrong-size in `query` and `SessionIndex.query`, so it raises at every `alpha`, while `query_multi_index` reads it as no embedding. Requires `inferedge-moss-core` 0.26.0.
- **Behavior change:** a blank query (empty or only whitespace) with no `embedding` returns no results at every `alpha` without running the embedding model. It used to embed the empty text above `alpha` 0 and rank every document against it. A blank query with an `embedding` ranks by the embedding. Requires `inferedge-moss-core` 0.26.0.
- Requires `inferedge-moss-core` 0.26.0 (was 0.25.0). That core adds the `min_score` query parameter and the relevance `score`.
- Queries no longer send one telemetry request each. `index.query`, `index.query_multi` and `session.query` events are buffered and sent with the usage flush every 3 seconds and at close, as JSON arrays of up to 500 events, one request per array. Each event keeps the fields it had, including its own `latencyMs`. Up to 10,000 events wait between flushes; events past that are dropped and the count is logged. Usage counts are unchanged. The README lists every telemetry event and its fields. Comes with `inferedge-moss-core` 0.26.0.
- Keyword-only and hybrid queries without a `filter` that match many documents in a large index are faster, since keyword search sorts only the top hits instead of every match. Comes with `inferedge-moss-core` 0.26.0.

### Fixed

- Every call that names a cloud index (`create_index`, `create_index_from_files`, `create_web_source`, `get_index`, `delete_index`, `add_docs`, `delete_docs`, `get_docs`, `load_index`, `SessionIndex.push_index`) raises `RuntimeError` for a name that is blank, `"."` or `".."`, contains `/` or a control character, or is longer than 256 bytes, before any request is sent; `load_indexes` lists such a name in `failed`. The message includes `Validation error: index name must not be blank, "." or "..", must not contain "/" or control characters, and must be at most 256 bytes`, the same text in every SDK. Any other name is percent-encoded, so names with spaces, `%`, `?` or `#` reach their own index. Pass the raw name: a name that is already percent-encoded, for example with `urllib.parse.quote`, is encoded again and addresses a different index. Requires `inferedge-moss-core` 0.26.0.
- `get_docs` percent-encodes each document id, so an id containing `,`, `&` or a space returns that one document. An id with a comma used to arrive as two ids.
- `add_docs` sends `MutationOptions.upsert` to the cloud when set. The service decides how to apply it. Requires `inferedge-moss-core` 0.26.0.
- Malformed index data and tokenizer files raise an ordinary error instead of a `PanicException`. An index whose stored vectors differ in length fails to load. A `tokenizer.json` whose truncation stride is not less than 512 minus its special tokens fails the model load. Deleting from an index stored without vectors works, and adding documents to it raises. Requires `inferedge-moss-core` 0.26.0.
- A vector holding NaN or infinity raises instead of reordering results without an error. Adding documents with one raises for the whole call, naming the document and the position, and stores nothing. A query `embedding` holding one raises at every `alpha`, and loading an index that stores one fails. Requires `inferedge-moss-core` 0.26.0.
- `MossClient.query` with `QueryOptions(top_k=0)` returns no results, as `query_multi_index` and `SessionIndex.query` do. It used to search with `top_k=5`.
- `moss.__version__` now reads the installed distribution metadata (`importlib.metadata.version("moss")`) instead of a hardcoded literal, so it always matches the published package version. In a source tree that is not installed as a distribution it reports `0.0.0+unknown`.
- `load_index` and `load_indexes` with `auto_refresh=True` and `polling_interval_in_seconds=0` poll at the default interval of 600 seconds. Before, the refresh task panicked as it started, so the index never refreshed while the load reported success. An interval above one year polls once a year. Requires `inferedge-moss-core` 0.26.0.
- Keyword-only and hybrid queries order documents with equal keyword scores by their position in the index, so the same query returns the same results on every call. That order used to vary from call to call. Requires `inferedge-moss-core` 0.26.0.
- When the auth service answers 500, 503, 429 or 408, the error names the HTTP status without the service's response body. A 403 from it raises the same invalid-credentials error as a 401. Requires `inferedge-moss-core` 0.26.0.

## [1.13.0] - 2026-09-18

### Changed

- Depends on `inferedge-moss-core` 0.25.0: loading a built-in model (`moss-minilm`, `moss-mediumlm`, `moss-litelm`) now requires the Moss cloud to be reachable and raises an error otherwise. No SDK API change.

## [1.12.0] - 2026-09-14

### Changed

- The per-device id is now sourced by the native core (`inferedge-moss-core` 0.24.0); `moss_core` users get it without the wrapper. Same file (`~/.moss/.moss-device-id`), same id. `moss_core` `set_device_id(None)` and `set_identity(None, ...)` keep the current id.
- Sessions created by a client now inherit that client's resolved device identity, and `load_index` / `load_indexes` create `<cache_path>/.moss-device-id` when it is missing. A client that passes `cache_path` is one Monthly Active Device across its index and session events instead of two. `moss_core.IndexManager` gains `set_identity` and `device_identity`, `moss_core.SessionIndex` gains `set_identity`.

## [1.11.0] - 2026-09-13

### Added

- `load_index` and `load_indexes` accept `cache_path`. The downloaded index is persisted under that directory and reused on later loads while the cloud copy is unchanged, so restarts skip the download; auto-refresh writes through to the same cache. Parity with the JS SDK's `cachePath`. Each load still contacts the cloud to check for a newer version.

## [1.10.0] - 2026-09-13

### Added

- Web source methods on `MossClient`: `create_web_source`, `list_web_sources`, `get_web_source`, `update_web_source`, `resync_web_source`, and `delete_web_source`, typed wrappers over the `/v1/manage` web source actions. `create_web_source`, `resync_web_source`, and `update_web_source` with `resync=True` return a `job_id` to poll with `get_job_status`; `delete_web_source` returns `purge_job_id` while the source's pages are removed.
- Types `WebSource`, `CreateWebSourceResult`, `UpdateWebSourceResult`, `ResyncWebSourceResult`, `DeleteWebSourceResult`, and `ManageApiError` (carries the HTTP `status`).
- `MOSS_CLOUD_API_BASE_URL` overrides the host used by the web source methods.

## [1.9.1] - 2026-09-08

### Fixed

- `load_index` / `load_indexes` no longer hold the GIL while the index downloads, deserializes, and the query model loads. Other Python threads (health probes, request handlers) kept freezing for the whole load, even when the call ran on a worker thread. Requires `inferedge-moss-core` 0.23.1.

## [1.9.0] - 2026-09-08

### Changed

- Reliability improvements to on-device model loading. No API change. Requires `inferedge-moss-core` 0.23.0.

## [1.8.0] - 2026-09-08

### Removed

- The cloud query fallback. `query()` on an index that is not loaded now raises `RuntimeError` telling you to call `load_index` first, instead of calling the retired `/query` service (which returned HTTP 503). `MossClient` no longer depends on `httpx`, and the `MOSS_QUERY_URL` override is gone.

### Added

- **Keyword and hybrid multi-index search.** `query_multi_index` now honors `QueryOptions.alpha` exactly like `query`: `1.0` is embedding-only (unchanged raw cosine scores), `0.0` is keyword-only, and values in between fuse both signals with Reciprocal Rank Fusion. Keyword scoring runs each index's own BM25 and merges hits by score before fusion, the same per-shard merge search engines use by default.

### Changed

- Foundation models (`moss-minilm`, `moss-mediumlm`, `moss-litelm`) download in the native model format when the project has access to it, and resume interrupted downloads. Other projects keep the existing model files. No API change.
- `query_multi_index` defaults `alpha` to `0.8` to match `query`. Callers who relied on the previous embedding-only behavior without passing `alpha` should pass `QueryOptions(alpha=1.0)`. Requires a matching `inferedge-moss-core` release.

### Fixed

- Local `query` treated `QueryOptions(alpha=0.0)` as unset and silently used `0.8`, making keyword-only search unreachable on loaded indexes. `alpha=0.0` is now forwarded as given.
- Keyword-only text queries (`alpha=0.0`) no longer embed the query first, so they no longer load an embedding model and now work on custom-model and identity-less indexes without a caller-supplied vector. Applies to both `query` and `query_multi_index`.
- Non-finite `alpha` (NaN, infinities) is rejected with a clear error instead of producing NaN scores.

## [1.7.3] - 2026-08-26

### Added

- `create_index_from_files` accepts `parse_options` (`ParseOptions`): `use_high_resolution`, `segmentation_method` ("smart_layout_detection" or "page_by_page"), `ocr_mode` ("auto_ocr" or "full_ocr"), and `merge_tables`.
- `session()` accepts `artifact_version` and `manifest_sha256` keyword arguments to pin a foundation model's immutable publisher release.

### Changed

- Supported `content_type` values are `application/pdf` and the DOCX MIME, matching the parse service's admission check.
- `JobPhase` includes the crawl and parse pipeline phases.
- Requires `inferedge-moss-core` 0.21.3 (parse options support and the moss-mediumlm 512 dimension fix).

### Fixed

- Local text queries on foundation indexes without an exact model artifact identity keep the core's actionable error instead of a misleading "custom embeddings" message.

## [1.7.2] - 2026-07-20

### Dependencies

- Bump `inferedge-moss-core` to `0.21.0`. The core now publishes an **abi3 wheel** (`cp310-abi3`, installs on Python 3.10–3.14) and a **glibc ≥ 2.35 x86_64 wheel**, so `moss` installs in common older-runtime environments — notably the TEN Framework dev container (Ubuntu 22.04 / Python 3.10), where the previous `cp312+` / `manylinux_2_38` wheels did not resolve. No API changes.

## [1.7.1] - 2026-07-09

### Added

- **Verbatim payload round-trip** (`DocumentInfo.payload`): store an opaque structured payload (e.g. a JSON string) verbatim alongside a document and get it back as-is on query/get — never embedded or searched.
- **Stable per-device id for usage tracking**: the SDK now sources a persisted device id (`~/.moss/.moss-device-id`) and hands it to the core, making per-device usage attribution stable across restarts.
- **Non-blocking `create_index`.** `create_index(..., wait=False)` returns a `JobHandle` as soon as the build is submitted, instead of blocking until it completes:
  - `handle.job_id` is available immediately.
  - `handle.status()` gives a live progress readout (phase + percent) as a `JobStatusResponse`.
  - `handle.wait()` blocks until the build finishes and returns the terminal `JobStatusResponse`. It polls asynchronously, so it parks no threads and never holds the GIL.
  - New `MossClient.wait_for_job(job_id)` blocks by `job_id` alone — submit, tear down the machine, then reconnect in a fresh process to wait on or poll the build.
  - The build runs server-side, so a submitted job completes regardless of the client. `wait` defaults to `True` and is keyword-only, so existing blocking callers are unaffected.

### Dependencies

- Requires `inferedge-moss-core==0.20.1`.

## [1.7.0] - 2026-07-07 — superseded by 1.7.1

- First cut of non-blocking `create_index`. **Use 1.7.1 instead**, which finalized the API (`wait` is keyword-only; `JobHandle.wait()` and `MossClient.wait_for_job()` return `JobStatusResponse`) and fixed a GIL hold that could freeze the event loop while a build was submitted or awaited.

## [1.6.0] - 2026-06-30

### Added

- **Exact / graph retrieval on `SessionIndex`, at parity with the iOS SDK.** `get_docs` now accepts a deterministic-fetch `GetDocumentsOptions` — fetch by `doc_ids`, by a metadata `filter` (same dict shape as query filters; no query vector, no ranking), with `sort_by`/`ascending` ordering, and `group_by` parent grouping. New `ParentGrouping(parent_field, order_field)` collapses sibling chunks into one result per unit. `QueryOptions.group_by` applies the same grouping to semantic queries.

```python
from moss import GetDocumentsOptions, ParentGrouping
scenes = await session.get_docs(GetDocumentsOptions(
    filter={"field": "level", "condition": {"$eq": "scene"}}, sort_by="chunk_index"))
units = await session.get_docs(GetDocumentsOptions(
    group_by=ParentGrouping("unit_id", "chunk_index")))
```

### Dependencies

- Bumped `inferedge-moss-core` to `0.19.0` (adds the graph-retrieval surface).

## [1.5.0] - 2026-06-30

### Added

- **Verbatim document `payload`.** `DocumentInfo` now carries an optional `payload` string — an opaque structured value (e.g. JSON) stored and returned unchanged, never embedded or searched. Set it when building/adding documents and read it back from `get_docs` / query results. Useful for keeping the full structured record alongside the embeddable `text`. Requires the new core and a current Moss backend.

### Fixed

- Managed (cloud) query results now surface `payload` (previously dropped when mapping the response).

### Dependencies

- Bumped `inferedge-moss-core` to `0.18.0` (adds payload support through the upload/build pipeline).

## [1.4.1] - 2026-06-15

### Fixed

- Loading `moss-litelm` indexes could fail with `Deserialization error: unsupported version: 3`. These indexes use the v3 index format, which requires `inferedge-moss-core` `0.17.0`; installing `moss` now brings in that core version automatically, so `moss-litelm` indexes load out of the box with no manual dependency steps. (`moss-minilm` / `moss-mediumlm` indexes are unaffected.)

### Dependencies

- Pinned `inferedge-moss-core==0.17.0`.

## [1.4.0] - 2026-06-02

### Dependencies

- Bumped `inferedge-moss-core` to `0.17.0`.

## [1.3.0] - 2026-05-18

### Added

- **Local-first session indexing** (merged from the separate `moss-session` package):
  - `MossClient.session(index_name, model_id?)` — creates a `SessionIndex`; auto-loads from cloud if an index with that name already exists, otherwise starts empty.
  - `SessionIndex.add_docs(docs, options?)` / `delete_docs(doc_ids)` / `get_docs(options?)` — local in-memory mutations and reads.
  - `SessionIndex.query(query, options?)` — semantic search over the local session index (~1–10ms, no network). Supports the same filter syntax as `MossClient.query()`.
  - `SessionIndex.push_index()` — uploads the session index to cloud, creating or replacing the index with the same name. Documents are pushed with their locally-computed embeddings; no server-side re-embedding.
  - New exports from `moss`: `SessionIndex`, `PushIndexResult`.
- `model_id="custom"` is supported for sessions — bring your own embeddings via `DocumentInfo.embedding` and `QueryOptions.embedding`; no local model is loaded.

## [1.2.0] - 2026-05-27

### Changed

- **`pip install moss` is now ~64% smaller.**

### Fixed

- Built-in model downloads (`moss-minilm`, `moss-mediumlm`) survive slow networks: resume after an interrupted connection instead of restarting, with automatic retries and exponential backoff on transient failures. (Also in 1.1.1.)

### Dependencies

- Bumped `inferedge-moss-core` to `0.14.0`.

## [1.1.1] - 2026-05-27

### Fixed

- Built-in model downloads (`moss-minilm`, `moss-mediumlm`) survive slow networks: resume after an interrupted connection instead of restarting, with automatic retries and exponential backoff on transient failures.
- Bumped `inferedge-moss-core` to `0.12.1`.

## [1.1.0] - 2026-05-06

### Added

- `query_multi_index(names, query, options)`: search across multiple loaded indexes; returns the global top-K with each doc tagged by source `index_name`. Embedding-only; `options.alpha` is ignored.
- `load_indexes(names, ...)` / `unload_indexes(names)`: bulk lifecycle. `load_indexes` is best-effort and returns `LoadIndexesResult { loaded, failed }`.
- `index_name` field on `QueryResultDocumentInfo` (set on multi-index results).
- Bumped `inferedge-moss-core` to `0.11.0`.

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

- Bumped `inferedge-moss-core` dependency to `0.5.0` to support session index telemetry and `push_index` improvements

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
- CDN-backed model downloads for fast model loading
- Multi-index support for isolated search spaces
- Add, update, and remove items across indexes
- Query interface with configurable result count
- Performance metrics tracking
