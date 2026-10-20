# Changelog

## [Unreleased]

## [1.8.0] - 2026-10-20

### Added

- The `moss_core` package declares its license, PolyForm Shield 1.0.0, as `LicenseRef-PolyForm-Shield-1.0.0`, and it and each NIF archive carry the `LICENSE.txt` it names.
- Each `moss_core` NIF archive carries `LICENSE-THIRD-PARTY.txt`, the license and copyright notices of the third-party code the NIF links: the Rust crates of that target, ONNX Runtime and the components it includes, and the Rust standard library.
- `Moss.Session.save_to_disk/2` and `Moss.Session.load_from_disk/3` take the cache path as optional, and `load_from_disk(session, rebuild_legacy: false)` also works. Without one, or with an empty one, snapshots go in `sessions/<project id>/` under the client's `:cache_path`, else under the `MOSS_SESSION_CACHE_PATH` environment variable, which only session snapshots read, else under `moss` in the default cache directory: `~/.cache/moss` on macOS and Linux, `%LOCALAPPDATA%\moss` on Windows. A path you pass is used as before. `Moss.Client` keeps its `:cache_path`, and `MossCore.Nif.session_save_to_disk/3` and `session_load_from_disk/4` take the client's cache path.

### Changed

- Bumped `moss_core` dependency to 0.25.0.
- `Moss.Session.add_docs/3` on a session with a built-in model embeds the documents in batches of at most 512 padded tokens instead of 8,192, and tokenizes each batch on the thread that embeds it. Each model session runs 2 inference threads on a desktop or server host (macOS, Linux or Windows) with 8 or more cores, and 1 on a smaller host and for `moss-litelm`. Idle threads sleep instead of spinning. Embedding many documents needs less memory, and on a host that runs 2 threads it takes less time. Text queries on other sessions with the same model stay fast while it runs. `MOSS_EMBEDDING_INTRA_OP_THREADS` still sets the thread count on every platform.
- `moss-litelm` embeds each document in its own batch, so a document's vector equals the vector of its text embedded alone. Embedded in a batch, its vectors used to differ from that, with a cosine similarity as low as 0.989.

## [1.7.0] - 2026-10-14

### Added

- `Moss.Client.create_index_from_files/5` takes `:chunk_size` (200 to 2000 characters, default 1200) and `:chunk_overlap` (0 to half of `:chunk_size`, default 200 capped at half of `:chunk_size`) in `parse_options` to control how the parse pipeline splits extracted text. Out-of-range values return `{:error, %Moss.Error{code: :invalid_argument}}` before any upload.

### Changed

- Bumped `moss_core` dependency to 0.24.0.

## [1.6.0] - 2026-10-12

### Added

- `Moss.Session.save_to_disk/2` and `Moss.Session.load_from_disk/3` save a session to disk and restore it. `save_to_disk/2` writes the session under `<cache_path>/<name>/` and returns `:ok`; a failed or interrupted save leaves the last saved snapshot loadable. `load_from_disk/3` restores it into a session with the same name and returns `{:ok, doc_count}`. A missing or damaged snapshot returns `{:error, %Moss.Error{code: :deserialization}}` and leaves the session as it was. A snapshot that an older core saved for a built-in model has no model artifact identity: by default `load_from_disk/3` rebuilds it for a session opened with the same model, re-embedding the stored documents and saving the snapshot back in the same call, which needs the cloud for the model. When the model cannot be loaded it returns `{:error, %Moss.Error{code: :model_unavailable}}` and changes nothing. `rebuild_legacy: false` loads such a snapshot as a custom-model session. After a load, `add_docs/3` and `query/3` use the model the session took from the snapshot, so a custom-model snapshot needs embeddings.
- `Moss.Client.session/3` takes `auto_load_on_init: false` to open the session without loading the cloud index of that name. The session starts empty with `:model_id`, so `Moss.Session.load_from_disk/3` restores a saved session with no index download. `Moss.Session.push_index/1` before any load replaces the cloud index with the session's documents.
- `Moss.Session.model_id/1` returns the embedding model the session uses, or `"custom"`. A load moves the session to the loaded model, and `add_docs/3` and `query/3` read it from the core on every call.

### Changed

- Bumped `moss_core` dependency to 0.23.0.
- `Moss.Session.add_docs/3` and `delete_docs/2` update the keyword index in place instead of rebuilding it, and loads build it in one pass. Scores are unchanged.
- `add_docs/3` checks every document of a call first, so a call with a vector of another length adds nothing.
- A session keeps one copy of each document, and adds and loads move documents into the index instead of copying them.
- `load_index/2` into a session that holds documents replaces them instead of keeping stale copies.
- The token cache keeps a token until 60 seconds before it expires or for 90% of its life, whichever is later, so short-lived tokens are cached too.
- A 401 drops only the token it rejected from the cache, and a refused telemetry request keeps the token.
- A project key session fetches one token for its requests and its telemetry.
- `load_index/2` keeps the session's loaded model when the index uses the same model, instead of loading it again.
- The precompiled `moss_core` NIFs link the custom-minimal ONNX Runtime that the C, JavaScript and Python SDKs ship, with only the operators the built-in models use, instead of the full runtime. The x86_64 Linux NIF is built on Ubuntu 22.04 and needs glibc 2.35 or newer instead of 2.38. No API change.

### Removed

- The `req` dependency, which the SDK does not use, and with it `finch`, `mint` and `hpax`. Their releases with published security advisories no longer reach an app through the SDK. An app that used `req`, or one of its dependencies, through the SDK must declare it in its own `mix.exs`.

### Fixed

- `Moss.Session.load_index/2` moves the session to the model of the index it loads, as `load_from_disk/3` does, so after a custom-model index, or a built-in model index without a model artifact identity, loads into a built-in model session, `add_docs/3` takes the documents' embeddings instead of failing and `query/3` without an embedding returns `{:error, %Moss.Error{code: :invalid_argument}}`. Without `:model_id`, `Moss.Client.session/3` resumes such an index, an empty one included, instead of returning an error while it warms the default model. An explicit `:model_id` the index does not use returns `{:error, %Moss.Error{code: :invalid_argument}}` with a message that names both models.

## [1.5.1] - 2026-10-06

### Changed

- Bumped `moss_core` dependency to 0.22.1.

### Fixed

- `Moss.Session.push_index/1` on a session with a built-in model (`moss-minilm`, `moss-mediumlm`, `moss-litelm`) sends that model's id, so the service re-embeds the text with it and the pushed index loads and answers text queries like one built with `Moss.Client.create_index/4`. It used to be stamped `custom`, so a pushed session could not be resumed with text queries. A custom-model session still pushes its own embeddings.

## [1.5.0] - 2026-10-05

### Added

- `Moss.Session.close/1`, `Moss.IndexManager.close/1` and `Moss.Client.close/1` send the final usage telemetry, waiting until it is delivered or 2 seconds pass, and stop the process. Closing a process that already stopped returns `:ok`.
- `Moss.LoadIndexesResult` has `failed_codes`, mapping each name that did not load to the same code atom `Moss.Error` carries. The reasons in `failed` are the fixed messages, with no URLs, file paths or index names.

### Changed

- Bumped `moss_core` dependency to 0.22.0.
- **Behavior change:** `Moss.Session` and `Moss.IndexManager` trap exits, so a supervisor shutdown or the abnormal exit of a linked process runs the same close before the process stops. A process that starts one with `start_link/1` closes it when it exits, even normally. `Moss.Client.new/3` and `Moss.Client.session/3` start unlinked and then link, so a normal exit of their caller leaves the manager and the session running as before.
- **Breaking:** every `{:error, reason}` from this SDK carries a `%Moss.Error{}` instead of a binary. `code` is an atom to match on: `:invalid_argument`, `:not_found`, `:unauthorized`, `:network`, `:deserialization`, `:model_unavailable` or `:internal`. `message` is fixed text per kind of failure (for example `"Index not found."`) with no URLs, file paths or index names, and `detail` holds the native error text in release and debug NIF builds alike: diagnostic text for logs and support, at most 512 bytes, and not a stable contract. That text names the operation or host in place of a request URL, and the file in place of an absolute path. A failed response contributes only its HTTP status and the error code its body names, such as `HTTP 403 Forbidden: AccessDenied` from the object store or `HTTP 409 Conflict: INDEX_EXISTS` from the Moss service, never the rest of the body. `Moss.Error` is an exception and implements `String.Chars`, so `raise reason`, `Exception.message(reason)`, `inspect(reason)` and `"#{reason}"` keep working; code that treats `reason` as a binary (`reason <> ...`, `reason =~ ...`, `when is_binary(reason)`) must read `reason.message` or match on `reason.code` instead. Option errors the NIF raises itself (`parse_options`, metadata filters, file maps) keep their descriptive text as the `message` with code `:invalid_argument`. A text query on an index that cannot embed text returns the core's message, `"This index cannot embed text queries. Pass a query embedding, or use alpha 0 for keyword-only search."`, instead of a reworded one. The NIF no longer uses Rust `Debug` formatting for error text.
- The `detail` for a damaged on-device vector file or session snapshot names a numbered fault, such as `fault 1028` for a vector count that differs from the snapshot metadata, and no longer describes the file layout or the snapshot files.
- Built-in model loads (`moss-minilm`, `moss-mediumlm`, `moss-litelm`) are faster, most of all on arm64. No API change.
- `Moss.Session.add_docs/3` on a session with a built-in model embeds the documents in batches of at most 8,192 padded tokens, grouped by length, instead of one batch padded to the longest document. Large calls need far less memory and time: on an Apple M2, 5,000 short captions in one call took about 20 s with a 0.6 GB peak instead of about 119 s and 9.1 GB. A query embedding for the same model waits for one batch instead of the whole call. Embeddings come back in input order, with the same values to about 1e-7.
- **Behavior change:** a malformed `$near` filter value is rejected with an error naming the expected `"lat,lng,maxDistanceMeters"` format instead of matching nothing.
- **Breaking change:** `$gt`, `$gte`, `$lt` and `$lte` compare two plain decimals (`"42"`, `"-3.5"`) as numbers and two other values as text, and never match a plain decimal against any other value. Zero padded numbers such as `"07"` and forms such as `"1e3"` or `"NaN"` are text, so `"07"` no longer matches `$gt: "5"` and `"naming"` never matches `$gt: "999999"`. A condition still never matches a document that lacks the field, `$ne` and `$nin` included.
- A load with a cache path that finds no usable snapshot while the Moss service is unreachable reports `:network` instead of `:deserialization`. An auth URL that answers 404 or 410 reports `:internal` instead of `:not_found`. A refused index name keeps the naming rule as its message, and a file with an unsupported content type reads `A file has an unsupported content type.` A text call on a session whose model cannot embed returns `:invalid_argument` with the message `"This session's model cannot embed text. Pass embeddings with the documents and the query."`

### Fixed

- Usage telemetry that fails to upload is retried on the next flush, every event under a stable `eventId`, for up to an hour and 20,000 events, instead of being dropped.
- `load_index/3` on a `moss-minilm` or `moss-mediumlm` index returns `{:ok, info}` instead of `{:error, reason}` when the cloud is unreachable and it serves a `:cache_path` snapshot. The core warms the model inside the load and tolerates a warm that fails offline, so the SDK makes no second warm call after the load. The embedding model cannot be opened until the Moss cloud is reachable, so text queries with `alpha` above 0 fail until then. Keyword-only queries (`alpha: 0.0`) and queries that pass an `:embedding` keep working, and a later refresh or query warms the model once the cloud returns.
- `refresh_index/2` downloads nothing and returns `was_updated: false` when the cloud snapshot is no newer than the loaded one and uses the same model. It used to download the whole index and return `was_updated: true` every time. On an index served stale from its cache, such a refresh still warms the embedding model.
- A query whose stored vectors have another length than the query returns `{:error, %Moss.Error{code: :internal}}` instead of ranking those documents with score 0.

## [1.4.0] - 2026-09-29

### Added

- With a `:cache_path` and a snapshot of the index already on disk, `load_index/3` makes one metadata request with a 5 second budget instead of retrying. When that request fails on a transport error, or the auth service answers 500, 503, 429 or 408, the load serves the snapshot and starts the refresh poller, even without `auto_refresh: true`. A 404, 401 or 403 still returns `{:error, reason}`. Only a snapshot saved by `moss_core` 0.21.0 or later under the same project and cloud origin is served. For an index on `moss-minilm` or `moss-mediumlm`, `load_index/3` also opens the embedding model, which needs the cloud, so the load can still return `{:error, reason}` while the cloud is unreachable, though the index stays loaded.

### Changed

- Bumped `moss_core` dependency to 0.21.0.
- **Behavior change:** `Moss.QueryResultDoc.score` is the relevance of the hit to the query, from 0 to 1, in `query/4`, `query_multi_index/4` and `Moss.Session.query/3` alike. Results stay in hybrid order, so a lower-ranked result can show a higher score. Scores depend on the embedding model. A keyword-only query (`alpha: 0.0`) scores every hit 0.0. Code that relied on the top result scoring about 1.0, or on `query_multi_index/4` scores at `alpha: 1.0` being raw similarity, needs updating. A relevance floor (`:min_score`) is not available in this SDK.
- **Behavior change:** a query `:embedding` whose length differs from the index dimension returns `{:error, reason}` at `alpha: 0.0` as it does above 0; it used to be ignored at 0. An empty `embedding: []` counts as wrong-size in `query/4` and `Moss.Session.query/3`, so it returns `{:error, reason}` at every `alpha`, while `query_multi_index/4` reads it as no embedding. An `:embedding` of all zeros returns `{:error, reason}` when `alpha` is above 0. A blank query (empty or only whitespace) with no `:embedding` returns no hits at every `alpha` without running the embedding model (a `"custom"` session still requires `:embedding`), and with an `:embedding` ranks by it when `alpha` is above 0.
- Queries no longer send one telemetry request each. `index.query`, `index.query_multi` and `session.query` events are buffered and sent with the usage flush every 3 seconds and when the client or session process stops, as JSON arrays of up to 500 events, one request per array. Each event keeps the fields it had, including its own `latencyMs`. Up to 10,000 events wait between flushes; events past that are dropped and the count is logged. Usage counts are unchanged.
- Broad keyword-only and hybrid queries on large indexes are faster.

### Fixed

- A vector holding NaN or infinity returns `{:error, reason}` instead of reordering results without an error. Adding documents with one fails the whole call, naming the document and the position, and stores nothing. A query `:embedding` holding one fails at every `alpha`, and loading an index that stores one fails.
- Malformed index data and tokenizer files return `{:error, reason}` instead of raising from the NIF. An index whose stored vectors differ in length fails to load. A `tokenizer.json` whose truncation stride is not less than 512 minus its special tokens fails the model load. Deleting from an index stored without vectors works, and adding documents to it returns `{:error, reason}`.
- `load_index/3` and `load_indexes/3` with `auto_refresh: true` and `polling_interval: 0` poll at the default interval of 600 seconds. Before, the refresh task panicked as it started, so the index never refreshed while the load reported success. An interval above one year polls once a year.
- `Moss.Client` calls that name a cloud index (`create_index`, `create_index_from_files`, `get_index`, `delete_index`, `add_docs`, `delete_docs`, `get_docs`, `load_index`), `Moss.Session.load_index/2` and `Moss.Session.push_index/1` return an error for a name that is blank, `"."` or `".."`, contains `/` or a control character, or is longer than 256 bytes, before any request is sent, with a message that includes `Validation error: index name must not be blank, "." or "..", must not contain "/" or control characters, and must be at most 256 bytes`. `load_indexes` lists such a name in `failed`. Any other name is percent-encoded, and `get_docs` percent-encodes each document id, so an id containing `,`, `&` or a space returns that one document. Pass the raw name: a name that is already percent-encoded is encoded again and addresses a different index.
- `Moss.Client.add_docs/4` sends the `:upsert` option to the cloud when set. The service decides how to apply it.
- Keyword-only and hybrid queries order documents with equal keyword scores by their position in the index, so the same query returns the same results on every call. That order used to vary from call to call.
- When the auth service answers 500, 503, 429 or 408, the error includes `Authentication service temporarily unavailable (HTTP N)` and no response body. A 403 from the auth service returns `Authentication failed: invalid credentials`, as a 401 does.

## [1.3.0] - 2026-09-18

### Changed

- Bumped `moss_core` dependency to 0.20.0.
- Loading a built-in model (`moss-minilm`, `moss-mediumlm`, `moss-litelm`) now requires the Moss cloud to be reachable and fails with an error otherwise. No API change.

## [1.2.0] - 2026-09-08

### Added

- `Moss.Client.query_multi_index/4`: search several loaded indexes in one call and get the global top-k, each result tagged with its source `index_name` on `Moss.QueryResultDoc`. `:alpha` works as in `query/4` (default 0.8): `1.0` embedding-only, `0.0` keyword-only, in between hybrid via Reciprocal Rank Fusion; keyword scoring runs each index's own BM25 and merges hits by score before fusion. `:top_k` (default 10) caps the merged result. Local-only: every name must be loaded and share one embedding model.
- `Moss.Client.load_indexes/3`: best-effort bulk load returning `%Moss.LoadIndexesResult{loaded, failed}`; `Moss.Client.unload_indexes/2` to release loaded indexes idempotently.
- Requires a `moss_core` NIF release with `manager_load_indexes`, `manager_unload_indexes`, `manager_query_multi_index`, and `manager_query_multi_index_text`.

### Changed

- The per-device id is now sourced by the native core; `Moss.DeviceId` is removed. Same file (`~/.moss/.moss-device-id`), same id. `Moss.Client.new/3`'s `:cache_path` is forwarded to the core's `load_index`, which adopts `<cache_path>/.moss-device-id` (created when missing, as before) and also caches loaded indexes on disk under that directory; a blank `:cache_path` is treated as unset, and the `$XDG_CACHE_HOME/moss` location is no longer consulted. `Moss.Client.session/3` copies the client manager's resolved identity onto the session. `MossCore.Nif.manager_set_device_id/2` and `session_set_device_id/2` keep the current id when given `nil`; `manager_device_identity/1` and `session_set_identity/4` are new.
- Foundation models (`moss-minilm`, `moss-mediumlm`, `moss-litelm`) download in the native model format when the project has access to it, and resume interrupted downloads. Other projects keep the existing model files. No API change.

## [1.1.0] - 2026-08-26

### Added

- `Client.create_index_from_files/5` accepts a `parse_options` map controlling server-side extraction: `:use_high_resolution`, `:segmentation_method` ("smart_layout_detection" or "page_by_page"), `:ocr_mode` ("auto_ocr" or "full_ocr"), and `:merge_tables`. Atom or string keys are accepted; unknown keys and wrong value types raise a clear error.

### Changed

- Supported parse content types are `application/pdf` and the DOCX MIME, matching the parse service's admission check. Docs now state that `:name`, `:content_type`, and `:path` are all required per file.
- Job status `current_phase` includes the crawl and parse phases ("crawling", "parsing_documents", and the parser phases).
- Bumped `moss_core` dependency to 0.18.0.

### Fixed

- `Client.session/3` with invalid credentials returns `{:error, reason}` instead of exiting the calling process; sessions start unlinked and link on success.

### Included from earlier unreleased work

- Device-id contract for usage tracking: `Moss.Client.new/3` resolves a stable per-device id once and applies it to both manager and session telemetry, so a device counts once toward Monthly Active Devices across the whole client.

---

## [1.0.2] - 2026-08-06 (not published to Hex)

### Changed

- Repository-only version bump during the CLI/Elixir layout restructure; no package release was made. Hex releases jump from 1.0.1 directly to 1.1.0.

---

## [1.0.1] - 2026-04-05

### Changed

- Bumped `moss_core` dependency to 0.9.0.
- Session authentication now uses short-lived JWT tokens (enterprise plan required).
- Removed `validate_credentials` call from `Client.session/3`; credential exchange happens inside the Rust core during session init.
- Updated package metadata and README.

---

## [1.0.0] - 2026-04-01

### Changed

- Renamed package from `moss_session` to `moss`.
- Published as a public Hex package (no longer requires `organization: "moss"`).
- Bumped version to 1.0.0 stable.

---

## [1.0.0-beta.5] - 2026-03-16

### Changed

- Bumped `moss_core` dependency to 0.8.7, which fixes the precompiled NIF tarball for macOS — the file inside the archive is now named with the versioned filename so RustlerPrecompiled places it correctly in `priv/native`.

---

## [1.0.0-beta.4] - 2026-03-16

### Changed

- Bumped `moss_core` dependency to 0.8.6, which fixes precompiled NIF packaging for macOS — the binary is now correctly distributed as `.so` (required by RustlerPrecompiled) instead of `.dylib`.

---

## [1.0.0-beta.3] - 2026-03-16

### Changed

- Bumped `moss_core` dependency to 0.8.5.

---

## [1.0.0-beta.1] - 2026-03-12

Initial release of the `moss_session` Elixir SDK (later renamed to `moss` in 1.0.0) with local-first session indexing.

### Added

- **`Moss.Client`** — single entry point for all operations
  - `new/3` — creates a client; starts an internal local index manager
  - `session/3` — auto-loads from cloud if the named index exists; starts empty otherwise; pre-warms built-in models (`"moss-minilm"` / `"moss-mediumlm"`) to eliminate cold-start delay on first query
  - Cloud CRUD: `create_index/4` (model_id optional, defaults to `"moss-minilm"`), `add_docs/4`, `delete_docs/3`, `get_job_status/2`, `get_index/2`, `list_indexes/1`, `delete_index/2`, `get_docs/3`
  - Local index ops: `load_index/3`, `unload_index/2`, `has_index/2`, `query/4`, `refresh_index/2`, `get_index_info/2`
  - Generates a per-client UUID (`client_id`) propagated to all sessions and managers for telemetry correlation
- **`Moss.Session`** GenServer — local in-session index backed by Rust core
  - `add_docs/3` — built-in models embed automatically; `model_id: "custom"` reads `.embedding` from each `DocumentInfo`; returns `{added, updated}`
  - `delete_docs/2` — remove documents by ID
  - `get_docs/2` — retrieve documents (optionally filtered by ID list)
  - `query/3` — semantic search; built-in models embed automatically; `model_id: "custom"` requires `embedding:` opt; accepts metadata filters
  - `load_index/2` — load an existing cloud index into the session
  - `push_index/1` — push local index to cloud (create or replace); flushes telemetry
- **`Moss.Models`** — Elixir structs: `DocumentInfo`, `SearchResult`, `QueryResultDoc`, `IndexInfo`, `PushIndexResult`, `RefreshResult`, `SerializedIndex`, `MutationResult`, `JobStatusResponse`, `CredentialsInfo`, `ModelRef`
- **Metadata filtering** — all query functions accept `:filter` map with full operator support
  - Field conditions: `$eq`, `$ne`, `$gt`, `$gte`, `$lt`, `$lte`, `$in`, `$nin`, `$near`
  - Logical combinators: `$and`, `$or` (fully nestable)
- **Background telemetry** — aggregated telemetry handled by the Rust core
- **Built-in models** — `"moss-minilm"` (fast) and `"moss-mediumlm"` (higher quality); embedding computation runs entirely in the Rust core via ONNX Runtime
- **`model_id: "custom"`** — bring your own pre-computed embeddings; no local model required
