# Changelog

## [Unreleased]

## [1.19.0] - 2026-10-20

### Added

- The `license` field names `LICENSE.txt`, the file the package ships, so npm and license scanners find the PolyForm Shield 1.0.0 text.
- `SessionIndex.saveToDisk`, `loadFromDisk` and `inspectSnapshot` take the directory as optional. Without one, or with an empty one, snapshots go in `sessions/<project id>/` under the client's `cachePath` option, else under the `MOSS_SESSION_CACHE_PATH` environment variable, which only session snapshots read, else under `moss` in the default cache directory: `~/.cache/moss` on macOS and Linux, `%LOCALAPPDATA%\moss` on Windows. A directory you pass is used as before.
- `IndexInfo`, `IndexStatus` and `ModelRef` are exported, so code that types the results of `getIndex` and `listIndexes` imports them from `@moss-js/moss`. Import every Moss type from `@moss-js/moss`: `@moss-js/moss-core` is the SDK's native runtime and is not supported for direct use.
- `IndexStatus`, `JobStatus` and `JobPhase` are exported as plain objects with matching string union types, so members such as `IndexStatus.Ready` work at runtime and type-check under `isolatedModules` and `verbatimModuleSyntax` (Vite, Next.js, tsx). Each member also names its own type, as an enum member did, so `let status: JobStatus.Completed` still compiles. The fields that hold them, such as `IndexInfo.status`, accept the same strings.

### Changed

- Requires `@moss-js/moss-core` 0.34.0.
- `@moss-js/moss-core` declares `IndexStatus`, `JobStatus` and `JobPhase` as types only, so code that imported their values from it, such as `IndexStatus.Ready`, imports them from `@moss-js/moss` instead.
- The published type declarations no longer include internal members. No runtime change.
- The custom embeddings section of the README says to L2-normalize the vectors you provide. Thanks @VeshRaazThapa (usemoss/moss#529).
- `dist/index.esm.js` ships as plain JavaScript, not minified, so stack traces name the SDK's own functions. No API change.
- `SessionIndex.addDocs` on a session with a built-in model embeds the documents in batches of at most 512 padded tokens instead of 8,192, and tokenizes each batch on the thread that embeds it. Each model session runs 2 inference threads on a desktop or server host (macOS, Linux or Windows) with 8 or more cores, and 1 on a smaller host, on Android and iOS, and for `moss-litelm`. Idle threads sleep instead of spinning. Embedding many documents needs less memory, and on a host that runs 2 threads it takes less time. Text queries on other sessions with the same model stay fast while it runs. `MOSS_EMBEDDING_INTRA_OP_THREADS` still sets the thread count on every platform.
- `moss-litelm` embeds each document in its own batch, so a document's vector equals the vector of its text embedded alone. Embedded in a batch, its vectors used to differ from that, with a cosine similarity as low as 0.989.

## [1.18.0] - 2026-10-14

### Added

- `ParseOptions.chunkSize` (200 to 2000 characters, default 1200) and `ParseOptions.chunkOverlap` (0 to half of `chunkSize`, default 200 capped at half of `chunkSize`) control how the parse pipeline splits extracted text. Out-of-range values reject before any upload.

### Changed

- Requires `@moss-js/moss-core` 0.33.0.

## [1.17.0] - 2026-10-12

### Added

- `MossModel` includes `"moss-litelm"`, so `session(name, "moss-litelm")` type-checks and `SessionIndex.modelId` names every model the core reports.

### Changed

- Requires `@moss-js/moss-core` 0.32.0.
- `@moss-js/moss-core` ships its native binary only in the `@moss-js/moss-core-<platform>` package that npm installs for the host as an optional dependency, so an install is about 60 MB smaller. Keep optional dependencies on: after an install with `npm install --omit=optional`, `optional=false` in `.npmrc` or `pnpm --no-optional`, importing `@moss-js/moss` throws `Cannot find native binding` with a hint to reinstall without that option. The same happens on `npm ci` from a lockfile that npm older than 11.3 rebuilt while `node_modules` existed, because that lockfile keeps only that machine's platform package. Before installing on another platform, regenerate it with `node_modules` removed, or with npm 11.3 or newer. No API change.
- `SessionIndex.addDocs` and `deleteDocs` update the keyword index in place instead of rebuilding it, and loads build it in one pass. Scores are unchanged.
- **Behavior change:** `SessionIndex.addDocs` checks every document of a call first, so a call with a vector of another length adds nothing.
- `SessionIndex` keeps one copy of each document, and adds and loads move documents into the index instead of copying them.
- A token is cached until 60 seconds before it expires or for 90% of its life, whichever is later, for custom authenticators and project keys.
- With a project key, a 401 drops only the token it rejected, and a refused telemetry request keeps the cached token instead of fetching a new one.
- A project key session fetches one token for its requests and its telemetry.
- A session filled by `loadIndex` or restored by `loadFromDisk` keeps its loaded model when the index uses the same model, instead of loading it again.

### Fixed

- `loadIndex` into a session that held documents kept them beside the loaded index, and `saveToDisk` then failed. A load now replaces them.
- With a custom authenticator, the retry after a 401 resent the same cached token. It now drops the rejected token and asks the authenticator for a new one.
- A client with a custom authenticator kept Node running after `close()`. The process now exits once its work is done.
- On Windows, a process that first loaded the native addon from a `worker_threads` worker could crash with an access violation when that worker exited. The addon now stays loaded until the process exits, as on Linux and macOS.
- `SessionIndex.modelId` is the model the native core reports after the last completed call, and `addDocs` and `query` pick their path by it on every call. `loadIndex` and `loadFromDisk` move the session to the model of the index or snapshot they load, which is `custom` for a custom-model one and for a built-in model one without a model artifact identity (such as a legacy snapshot loaded with `rebuildLegacy: false`), and auto-refresh can install a custom-model version into a built-in model session. After such a change, `addDocs` takes the documents' embeddings instead of rejecting, and `query` without an embedding rejects with code `INVALID_ARGUMENT`.

## [1.16.1] - 2026-10-06

### Fixed

- `SessionIndex.pushIndex()` on a session with a built-in model (`moss-minilm`, `moss-mediumlm`, `moss-litelm`) sends that model's id, so the service re-embeds the text with it and the pushed index loads and answers text queries like one built with `createIndex`. It used to be stamped `custom`, so a pushed session could not be resumed with text queries. A custom-model session still pushes its own embeddings. Requires `@moss-js/moss-core` 0.31.1.

## [1.16.0] - 2026-10-05

### Added

- `isMossError(error)` and the `MossError` / `MossErrorCode` types. An error from the native core is an `Error` whose `code` is one of `INVALID_ARGUMENT`, `NOT_FOUND`, `UNAUTHORIZED`, `NETWORK`, `DESERIALIZATION`, `MODEL_UNAVAILABLE` or `INTERNAL`; branch on `code` instead of the message. `detail` holds the core error text, diagnostic text for logs and support rather than a stable contract. Requires `@moss-js/moss-core` 0.31.0.
- `LoadIndexesResult.failedCodes` maps each index that `loadIndexes` could not load to its `MossErrorCode`. Requires `@moss-js/moss-core` 0.31.0.

### Changed

- **Behavior change:** errors from the native core carry fixed messages per kind of failure, such as `Index not found.`, with no URLs, file paths or index names. The reasons in `loadIndexes().failed` are the same fixed messages. `query` on an index that is not loaded rejects with code `NOT_FOUND`, and its message still names the load call. `queryMultiIndex` on an index that cannot embed text rejects with the core's own error (code `INVALID_ARGUMENT`, message `This index cannot embed text queries. Pass a query embedding, or use alpha 0 for keyword-only search.`) instead of rewording it.
- Built-in model loads (`moss-minilm`, `moss-mediumlm`, `moss-litelm`) are faster, most of all on arm64. No API change. Requires `@moss-js/moss-core` 0.31.0.
- `SessionIndex.addDocs` on a session with a built-in model embeds the documents in batches of at most 8,192 padded tokens, grouped by length, instead of one batch padded to the longest document. Large calls need far less memory and time: on an Apple M2, 5,000 short captions in one call took about 20 s with a 0.6 GB peak instead of about 119 s and 9.1 GB. A query embedding for the same model waits for one batch instead of the whole call. Embeddings come back in input order, with the same values to about 1e-7. Requires `@moss-js/moss-core` 0.31.0.
- **Behavior change:** a malformed `$near` filter value is rejected with an error naming the expected `"lat,lng,maxDistanceMeters"` format instead of matching nothing.
- **Breaking change:** `$gt`, `$gte`, `$lt` and `$lte` compare two plain decimals (`"42"`, `"-3.5"`) as numbers and two other values as text, and never match a plain decimal against any other value. Zero padded numbers such as `"07"` and forms such as `"1e3"` or `"NaN"` are text, so `"07"` no longer matches `$gt: "5"` and `"naming"` never matches `$gt: "999999"`. A number in a filter is compared in its plain decimal form, so `0.000001` still orders as a number. A condition still never matches a document that lacks the field, `$ne` and `$nin` included.
- **Behavior change:** saving a session keeps vectors that were loaded as INT8 in INT8. It used to widen them to FP32, a file about four times larger with no gain in precision.
- Filter validation and ordering come from `@moss-js/moss-core` 0.31.0.
- `queryMultiIndex([])` and `SessionIndex.query` without an embedding on a custom-model session throw an `Error` with code `INVALID_ARGUMENT`, so `isMossError` accepts them.
- A load with a cache path that finds no usable snapshot while the Moss service is unreachable reports `NETWORK` instead of `DESERIALIZATION`. An auth URL that answers 404 or 410 reports `INTERNAL` instead of `NOT_FOUND`. A refused index name keeps the naming rule as its message, and a file with an unsupported content type reads `A file has an unsupported content type.` Requires `@moss-js/moss-core` 0.31.0.

### Fixed

- `MossClient.close()` and `SessionIndex.close()` resolve once the final usage telemetry is delivered or 2 seconds pass, retrying a failing endpoint in that time, so a process that exits right after `await client.close()` reports its last queries. Telemetry a periodic flush could not deliver is retried on the next flush instead of dropped. Requires `@moss-js/moss-core` 0.31.0.
- `loadIndex` with `autoRefresh` and session auto refresh compare `updatedAt` as a point in time, so two spellings of one instant are no change, and a tick that finds a new snapshot fetches the index metadata once instead of twice. After a `loadIndex` served stale from `cachePath`, the first auto refresh that reaches the cloud warms the embedding model even when the snapshot is unchanged. Requires `@moss-js/moss-core` 0.31.0.
- A query whose stored vectors have another length than the query rejects with code `INTERNAL` instead of ranking those documents with score 0. Requires `@moss-js/moss-core` 0.31.0.

## [1.15.0] - 2026-09-29

### Added

- `QueryOptions.minScore` drops hits whose `score` is below the threshold, from 0 to 1; a query returns up to `topK` hits that clear it, in hybrid order. A value outside 0 to 1 is rejected, and so is setting it on a keyword-only query (`alpha === 0`) or when no queried index holds vectors. `query` and `queryMultiIndex` forward it to all four native query methods; session queries ignore it.
- `QueryOptions.candidateDepth` sets how many hits a hybrid query ranks on each signal (vector and keyword) before fusion. A hit outside both lists is never returned, so a deeper list raises recall and query time. Left unset, a hybrid query looks `2 * topK` deep, as before. A set value must be at least 1 (0 is rejected) and is raised to `topK` when below it. Keyword-only and vector-only queries (`alpha` 0 or 1) ignore it and rank `topK` hits, since a deeper list returns the same results. `query` and `queryMultiIndex` forward it to all four native query methods; session queries ignore it. Requires `@moss-js/moss-core` 0.30.0.
- `loadIndex` and `loadIndexes` with a `cachePath` serve the snapshot saved there when the cloud is unreachable, instead of failing. When a snapshot is on disk, the cloud check makes one attempt within 5 seconds. A transport error (unreachable network, timeout) or an HTTP 408, 429, 500, 502, 503 or 504 (only a 408, 429, 500 or 503 from the auth service) loads the snapshot and starts a refresh poller, even without `autoRefresh`, so the index catches up when the cloud returns. A 404 still fails, as does a 401 or 403, so a deleted or forbidden index does not come back from cache. A snapshot saved by an SDK before 1.15.0, or under another project or cloud origin, is not served, and the load fails after that one attempt. A load that finds the cloud copy unchanged keeps the old snapshot, so a snapshot saved before 1.15.0 is served only after the index is downloaded again, which happens when the cloud copy changes. After a load from the snapshot, text queries with `alpha` above 0 fail until the Moss cloud is reachable, since a built-in embedding model cannot open offline, unless the same model is already open in this process. Keyword-only queries (`alpha: 0`) and queries that pass their own embedding keep working. Requires `@moss-js/moss-core` 0.30.0.

### Changed

- **Behavior change:** `score` is the relevance of the hit to the query, from 0 to 1, in `query`, `queryMultiIndex` and `SessionIndex.query` alike. Results stay in hybrid order, so a lower-ranked result can show a higher score. Scores depend on the embedding model: tune `minScore` on your own queries. A keyword-only query (`alpha === 0`) scores every hit 0.
- Requires `@moss-js/moss-core` 0.30.0, which adds the `minScore` query parameter and the relevance `score`.
- **Behavior change:** a query `embedding` whose length differs from the index dimension rejects at `alpha` 0 as it does above 0; it used to be ignored at 0. An empty `embedding: []` counts as wrong-size in `query` and `SessionIndex.query`, so it rejects at every `alpha`, while `queryMultiIndex` reads it as no embedding. Requires `@moss-js/moss-core` 0.30.0.
- **Behavior change:** a blank query (empty or only whitespace) with no `embedding` returns no results at every `alpha` without running the embedding model. It used to embed the empty text above `alpha` 0 and rank every document against it. A blank query with an `embedding` ranks by the embedding. Requires `@moss-js/moss-core` 0.30.0.
- Queries no longer send one telemetry request each. `index.query`, `index.query_multi` and `session.query` events are buffered and sent with the usage flush every 3 seconds and at close, as JSON arrays of up to 500 events, one request per array. Each event keeps the fields it had, including its own `latencyMs`. Up to 10,000 events wait between flushes; events past that are dropped and the count is logged. Usage counts are unchanged. The README lists every telemetry event and its fields. Requires `@moss-js/moss-core` 0.30.0.
- `MossClient.close()` and `SessionIndex.close()` resolve after the final telemetry flush is sent, so a process that exits right after `await close()` keeps its buffered query events. A flush waits at most 5 seconds for authentication, once for all its events, and 3 seconds per request. Requires `@moss-js/moss-core` 0.30.0.
- Keyword-only and hybrid queries without a `filter` that match many documents in a large index are faster, since keyword search sorts only the top hits instead of every match. Keyword scores are the same. Requires `@moss-js/moss-core` 0.30.0.

### Fixed

- Malformed index data and tokenizer files reject with an ordinary error instead of a native panic. An index whose stored vectors differ in length fails to load. A `tokenizer.json` whose truncation stride is not less than 512 minus its special tokens fails the model load. Deleting from an index stored without vectors works, and adding documents to it rejects. Requires `@moss-js/moss-core` 0.30.0.
- A vector holding NaN or infinity rejects instead of reordering results without an error. `SessionIndex.addDocs` with one rejects the whole call, naming the document and the position, and stores nothing. A query `embedding` holding one rejects at every `alpha`, and loading an index that stores one fails. Requires `@moss-js/moss-core` 0.30.0.
- Every call that names a cloud index (`createIndex`, `createIndexFromFiles`, `createWebSource`, `getIndex`, `deleteIndex`, `addDocs`, `deleteDocs`, `getDocs`, `loadIndex`, `SessionIndex.loadIndex`, `SessionIndex.pushIndex`) rejects a name that is blank, `"."` or `".."`, contains `/` or a control character, or is longer than 256 bytes, before any request is sent; `loadIndexes` lists such a name in `failed`. The error message includes `Validation error: index name must not be blank, "." or "..", must not contain "/" or control characters, and must be at most 256 bytes`, the same text in every SDK. Any other name is percent-encoded, so names with spaces, `%`, `?` or `#` reach their own index. Pass the raw name: a name that is already percent-encoded, for example with `encodeURIComponent`, is encoded again and addresses a different index. Requires `@moss-js/moss-core` 0.30.0.
- `getDocs` percent-encodes each document id, so an id containing `,`, `&` or a space returns that one document. An id with a comma used to arrive as two ids. Requires `@moss-js/moss-core` 0.30.0.
- `addDocs` sends `MutationOptions.upsert` to the cloud when set. The service decides how to apply it. Requires `@moss-js/moss-core` 0.30.0.
- `loadIndex` and `loadIndexes` with `autoRefresh: true` and `pollingIntervalInSeconds: 0` poll at the default interval of 600 seconds. Before, the refresh task panicked as it started, so the index never refreshed while the load reported success. An interval above one year polls once a year. Requires `@moss-js/moss-core` 0.30.0.
- Keyword-only and hybrid queries order documents with equal keyword scores by their position in the index, so the same query returns the same results on every call. That order used to vary from call to call. Requires `@moss-js/moss-core` 0.30.0.
- With a project key, when the auth service answers 408, 429, 500 or 503, the error names the HTTP status without the service's response body. A 403 from it rejects with the same invalid-credentials error as a 401. Web source methods and `getAuthToken` are not affected. Requires `@moss-js/moss-core` 0.30.0.

## [1.14.0] - 2026-09-20

### Added

- `SessionIndex.loadFromDisk` rebuilds a snapshot that was saved for a built-in model by an SDK older than 1.8: those snapshots carry no model provenance, so the core could only restore them as custom-model sessions and text `addDocs`/`query` failed with "requires explicit embeddings". `loadFromDisk` now asks the core to rebuild such a snapshot, which it does only for a session opened with the same built-in model: the stored documents are re-embedded with the current model and the upgraded snapshot is saved back, in one operation, so the rebuild runs once per device (a minute or so for 10k chunks, off the main thread, with the cloud reachable for the model). Pass `{ rebuildLegacy: false }` to opt out. Custom-model sessions, snapshots that already carry provenance, and snapshots of a different model load as before. When the rebuild cannot load the model, for example offline, `loadFromDisk` rejects with a message starting "Legacy snapshot rebuild needs the embedding model" and changes nothing, so retry later instead of discarding the snapshot.
- `SessionIndex.inspectSnapshot(cachePath)` describes a snapshot without loading it; `SnapshotInfo` and `LoadFromDiskOptions` are exported. Requires `@moss-js/moss-core` 0.29.0.

## [1.13.0] - 2026-09-20

### Changed

- Depends on `@moss-js/moss-core` 0.28.0: every `SessionIndex` operation (`addDocs`, `deleteDocs`, `getDocs`, `query`, `saveToDisk`, `loadFromDisk`) and the model warm-up inside `MossClient.session()` now run their native work on a worker thread instead of the Node main thread, so the event loop and every socket connection keep serving while a large batch is embedded or a session is persisted. No SDK API change: these methods already returned Promises, but previously the underlying native calls blocked the main thread until they finished. Operations on one `SessionIndex` still run strictly in call order, one at a time, even when not awaited. `docCount` stays synchronous and never waits: it reports the count as of the last completed operation.

## [1.12.0] - 2026-09-18

### Changed

- Depends on `@moss-js/moss-core` 0.27.0: loading a built-in model (`moss-minilm`, `moss-mediumlm`, `moss-litelm`) now requires the Moss cloud to be reachable and rejects with an error otherwise. No SDK API change.

## [1.11.0] - 2026-09-14

### Changed

- The per-device id is now sourced by the native core (`@moss-js/moss-core` 0.26.0); `@moss-js/moss-core` users get it without the wrapper. Same file (`~/.moss/.moss-device-id`), same id. `MossClientOptions.cachePath` still uses `<cachePath>/.moss-device-id` (adopting an existing id, or creating one when the file is missing), and `identity.deviceId` still overrides the billable id. Sessions opened through `client.session()` carry the client's resolved identity, including an id adopted by `loadIndex(name, { cachePath })`; the first id resolved on a client stays on every surface, and a per-call `loadIndex(name, { cachePath })` still creates `<cachePath>/.moss-device-id` when it is missing.

## [1.10.0] - 2026-09-13

### Added

- Web source methods on `MossClient`: `createWebSource`, `listWebSources`, `getWebSource`, `updateWebSource`, `resyncWebSource`, and `deleteWebSource`, typed wrappers over the `/v1/manage` web source actions. `createWebSource`, `resyncWebSource`, and `updateWebSource` with `resync: true` return a `jobId` to poll with `getJobStatus`; `deleteWebSource` returns `purgeJobId` while the source's pages are removed.
- Types `WebSource`, `CreateWebSourceOptions`, `CreateWebSourceResult`, `UpdateWebSourceOptions`, `UpdateWebSourceResult`, `ResyncWebSourceResult`, `DeleteWebSourceResult`, and `ManageApiError` (carries the HTTP `status`).
- `MOSS_CLOUD_API_BASE_URL` overrides the host used by the web source methods.

## [1.9.0] - 2026-09-08

### Changed

- Reliability improvements to on-device model loading. No API change. Requires `@moss-js/moss-core` 0.25.0.

## [1.8.0] - 2026-09-08

### Changed

- Published as `@moss-js/moss`, depending on `@moss-js/moss-core` 0.24.0. Install with `npm install @moss-js/moss`. `@moss-dev/moss` stays at 1.7.1 and receives no further releases.
- Foundation models (`moss-minilm`, `moss-mediumlm`, `moss-litelm`) download in the native model format when the project has access to it, and resume interrupted downloads. Other projects keep the existing model files. No API change.

### Removed

- The cloud query fallback. `query` on an index that is not loaded now rejects with an error telling you to call `loadIndex` first, instead of calling the retired `/query` service (which returned HTTP 503). The `MOSS_QUERY_URL` override is gone.

### Added

- `MossClient.queryMultiIndex(indexNames, query, options)`: search several loaded indexes in one call and get the global top-k, each result tagged with its source `indexName`. `options.alpha` works as in `query` (default 0.8): `1.0` embedding-only, `0.0` keyword-only, in between hybrid via Reciprocal Rank Fusion; keyword scoring runs each index's own BM25 and merges hits by score before fusion. `options.topK` (default 10) caps the merged result. Local-only: every name must be loaded and share one embedding model.
- `MossClient.loadIndexes(indexNames, options)`: best-effort bulk load returning `LoadIndexesResult { loaded, failed }`; `MossClient.unloadIndex(indexName)` and `MossClient.unloadIndexes(indexNames)` to release loaded indexes.
- `QueryResultDocumentInfo.indexName` (set on multi-index results) and the `LoadIndexesResult` type.
- These methods require a `@moss-dev/moss-core` release with the multi-index API; on an older core they fail fast with an upgrade error instead of a raw `TypeError`.

## [1.7.1] - 2026-08-26

### Fixed

- `createIndexFromFiles` with in-memory `data` (Uint8Array, ArrayBuffer, Blob, or File) failed at the native boundary with "Failed to get Array length on JsParseFileInput.data"; bytes are now marshalled in the representation the binding accepts. The `path` flow was unaffected.

## [1.7.0] - 2026-08-26

- New `CreateIndexFromFilesOptions.parseOptions` (`ParseOptions`, now exported): control server-side extraction with `useHighResolution`, `segmentationMethod` (`smart_layout_detection` or `page_by_page`), `ocrMode` (`auto_ocr` or `full_ocr`, the latter for scanned documents with no text layer), and `mergeTables`. Requires `@moss-dev/moss-core` `0.23.0`.
- `ParseFileInput.contentType` supports `application/pdf` and the DOCX MIME, matching the parse service's admission check; unsupported types fail fast locally with a clear error.
- `JobProgress.currentPhase` includes the crawl and parse pipeline phases (`queued`, `crawling`, `parsing_documents`, `parsing`, `waiting_for_parser`, `parsing_complete`).
- Local text queries on server-built foundation indexes without an exact model artifact identity are refused with an actionable error instead of embedding against a guessed artifact; explicit query embeddings and cloud queries are unaffected.

## [1.6.0] - 2026-08-06

- New `MossClientOptions.identity` (`MossIdentity`): pass a stable caller-managed `deviceId` and optional `userId` at construction. The caller's `deviceId` is emitted as the billable telemetry `deviceId` (Monthly Active Device key); Moss's stable UUID is always emitted alongside as `mossDeviceId` for correlation; `userId` is never billable. Values must be 1-256 UTF-8 bytes with no surrounding whitespace, control or format characters, lone surrogates, or replacement characters; invalid values throw at construction. Without a configured identity, `deviceId` and `mossDeviceId` both carry Moss's UUID, so existing billing behavior is unchanged. Requires `@moss-dev/moss-core` `0.22.0`; constructing with an identity on an older core fails fast with an actionable error.

## [1.4.0] - 2026-07-13

- New: SessionIndex.close() and MossClient.close(), both idempotent, plus Symbol.asyncDispose support so `await using` works on Node 24. Closing releases the native index, pollers, and the session's reference to the shared embedding model (the service is dropped when the last session using it closes; the allocator retains and reuses those pages for the next load, so footprint stays bounded at one model per model id). Threads are no longer per-session. Concurrent close() callers share one completion promise and all settle when disposal finishes.
- Published type declarations no longer force consumers to enable the ESNext.Disposable lib (the bundle carries the reference itself); consumers need TypeScript 5.2 or newer.
- README and samples now demonstrate the close() / await using lifecycle.
- MossClient.close() now also closes every live session created by that client (tracked via weak references); sessions can still be closed individually first.
- close() fails loudly when the installed @moss-dev/moss-core predates the lifecycle API instead of silently leaking; this release requires @moss-dev/moss-core 0.20.0.
- Declared engines: node >= 20.4 (first Node release where Symbol.asyncDispose exists).

## [1.3.2] - 2026-07-09

### Changed

- Picks up `@moss-dev/moss-core` `0.19.2` (dependency currency; native-binding `DocumentInfo.payload` round-trip fix). No SDK API changes. (Prior `1.3.1` release re-run failed because the version was not bumped; this restores a publishable version.)

## [1.3.1] - 2026-06-26

### Fixed

- **Fixed a native crash when re-saving an on-disk session.** Calling `saveToDisk` on a session previously restored with `loadFromDisk` could crash the process while writing the on-disk index, because the index file was rewritten in place while the loaded session was still reading from it. `saveToDisk` still persists immediately, but now writes to a temporary file and atomically renames it into place, so the file the live session is reading from is never rewritten underneath it. Requires `@moss-dev/moss-core` `0.19.1`.

## [1.3.0] - 2026-06-25

### Added

- **Sessions work with a custom `IAuthenticator`.** `MossClient.session()` now works when the client is constructed with a custom authenticator (short-lived tokens / delegated auth), not just a static project key — it previously threw. The session authenticates (credential validation, `pushIndex`, `loadIndex`) and reports usage through the same auth bridge as `loadIndex`. Requires `@moss-dev/moss-core` `0.19.0` (adds the `SessionIndex.withAuthenticator` napi factory).

## [1.2.1] - 2026-06-25

### Added

- **Client-level `cachePath`.** `new MossClient(projectId, key, { cachePath })` (and the `IAuthenticator` overload) sets one location for the per-device telemetry id, honored by every operation that emits telemetry — `loadIndex`, `session`, and so on. Set it once instead of per call.

### Fixed

- **Session telemetry now carries the per-device id.** `MossClient.session()` now attaches the anonymous `deviceId` to `session.*` telemetry events, matching `loadIndex`. Previously only the `loadIndex` path attached a `deviceId`, so usage from session-only clients was reported without one.
- The per-device id is now resolved once and shared across `loadIndex` and `session()` within a client, so a client that uses both surfaces reports a single, consistent id.

### Changed

- The per-device id location is now resolved with this precedence: the client-level `cachePath`, then the `cachePath` passed to `loadIndex` (back-compat), then a per-user fallback, `<home>/.moss/.moss-device-id`. Previously the id was only written when `loadIndex` was given a `cachePath`.

## [1.2.0] - 2026-06-23

### Added

- **Usage telemetry on the custom-authenticator path.** Automatic, privacy-light usage telemetry now works when the client is constructed with a custom `IAuthenticator` (e.g. short-lived tokens), not just a plain project key — previously it was silently disabled on that path. This enables device-level usage reporting for client-side / delegated-auth deployments.
- A stable, anonymous per-device id is generated once and persisted at `<cachePath>/.moss-device-id` (the `cachePath` you already pass to `loadIndex`), then attached to telemetry as `deviceId`. It is a random UUID — no hardware identifier, no PII.
- Bumped `@moss-dev/moss-core` to `0.18.0` (adds the `setDeviceId` napi binding and auth-provider telemetry).

## [1.1.0] - 2026-06-03

### Added

- **`MossClient.session(name, modelId?)`** — local-first session index. Construct a session, add/delete/get documents and run queries entirely in-process (no cloud round-trip per operation), then `pushIndex()` to persist to the cloud. Also `loadIndex(indexName, { autoRefresh, pollingIntervalInSeconds })` to pull an existing cloud index into the session.
- New top-level exports: `SessionIndex`, `PushIndexResult`, `LoadSessionOptions`.
- Bumped `@moss-dev/moss-core` to `0.17.0` (adds the `SessionIndex` napi binding).

## [1.0.2] - 2026-05-05

### Changed

- Bumped `@moss-dev/moss-core` dependency from `0.9.1` to `0.10.0`, which adds prebuilt binaries for `x86_64-apple-darwin` (Intel Macs) and realigns the npm package version with the underlying Rust core.

## [1.0.1] - 2026-04-17

### Added

- **Custom authenticator** for browser-safe authentication: new `MossClient.withAuthenticator()` and `IndexManager.withAuthenticator()` factory methods accept a JS-side token callback, backed by `JsAuthBridge` in `@moss-dev/moss-core`.

### Changed

- `CLOUD_API_MANAGE_URL` replaced by granular constants: `CLOUD_API_IDENTITY_URL`, `CLOUD_API_AUTH_URL`, etc.

## [1.0.0] - 2026-04-01

### Architecture

- **Rust-native core**: The SDK now delegates all index management, querying, and embedding generation to `@moss-dev/moss-core` (Rust via NAPI-RS), replacing the previous pure-JavaScript implementations
- **Node-only**: Dropped browser/WASM support; the SDK targets Node.js 20+ exclusively
- Query embeddings are now generated in Rust (`queryText` / `loadQueryModel`), matching the Python SDK architecture

### Changed

- Package renamed from `@inferedge/moss` to `@moss-dev/moss`
- NAPI binding renamed from `moss-core` to `@moss-dev/moss-core` (v0.8.7, tracking Rust core version)
- `query()` uses Rust-native `queryText()` for local queries (no JS embedding pipeline)
- `query()` with `embedding` option uses Rust `query()` directly
- `query()` falls back to cloud HTTP when index is not loaded locally

## [1.0.0-beta.8] - 2026-03-30

### Added
- **Filesystem Index Caching**: `loadIndex()` now accepts an optional `cachePath` in `LoadIndexOptions` to cache index binaries and documents to disk (Node.js/Bun only)
  - Cache is automatically invalidated when the cloud index is updated
  - Auto-refresh also persists refreshed data to the cache
  - Atomic writes prevent cache corruption from partial/interrupted writes
  - Path traversal protection on index names
  - Graceful fallback to re-download if cached data is corrupted
- **Metadata Filtering**: `query()` now accepts an optional `filter` in `QueryOptions` to narrow results by document metadata on locally loaded indexes
  - Comparison operators: `$eq`, `$ne`, `$gt`, `$gte`, `$lt`, `$lte`
  - Set operators: `$in`, `$nin`
  - Composable with `$and` / `$or` for complex predicates (supports arbitrary nesting)
  - Numeric coercion: number filter values are automatically stringified for consistent matching
- **Geo-distance filtering**: new `$near` operator filters documents by haversine distance from a `"lat,lng,radiusMeters"` value
- New exported types: `FilterCondition`, `MetadataFilter`

## [1.0.0-beta.7] - 2026-02-18

### Added
- Async job-based mutations (`createIndex`, `addDocs`, `deleteDocs`) with built-in polling and `onProgress` callbacks
- Large index support — up to 100k documents via presigned upload + server-side build
- New binary index format with smaller payloads and faster deserialization; existing indexes using the previous format are still supported

## [1.0.0-beta.6] - 2026-02-02

### Added
- **Hot Reload & Auto-Refresh**: Indexes can now automatically detect and reload when updated in the cloud.
  - `loadIndex()` now accepts optional `LoadIndexOptions` with `autoRefresh` and `pollingIntervalInSeconds` parameters
  - When `autoRefresh` is enabled, the SDK polls for updates at the configured interval (default: 600 seconds)
  - To stop auto-refresh, call `loadIndex()` again without the `autoRefresh` option
- `loadIndex()` now allows reloading an already-loaded index (previously threw an error)

## [1.0.0-beta.5] - 2025-01-29

### Added
- Query optimizations for custom-embedding workflow

## [1.0.0-beta.4] - 2025-01-28

### Fixed

- Fixed `ReferenceError: process is not defined` crash in browser environments. The SDK now works seamlessly across all JavaScript runtimes including browsers, Node.js, Deno, and Bun.

## [1.0.0-beta.3] - 2025-01-24

### Added

- Support for user-supplied document embeddings during ingestion. The SDK supports optional `embedding` arrays in `DocumentInfo` payloads without using the native embedding service from moss.
- Query overloads now accept `QueryOptions` so users can provide a custom embedding alongside query text.
- Relaxed `modelId` requirement when creating indexes. The SDK aligns with the service default of `moss-minilm` when no explicit model is provided.
- `query()` now automatically falls back to the cloud API when the index is not loaded locally, enabling queries without requiring `loadIndex()` first.

### Enhancements

- New service endpoint with significant infrastructure upgrades. Management operations are now ~3× faster across most real-world use cases, providing faster index operations while also supporting larger payloads.

## [1.0.0-beta.2] - 2025-11-30

### Fixed

- Fixed ESM (ES Module) import compatibility issue. The package now correctly exports as an ES module and can be imported using standard ESM syntax.

### Upgrade Instructions

- Migrate from CommonJS (`require`) to ES Module syntax (`import`).

## [1.0.0-beta.1] - 2025-10-01

Initial release of @moss-dev/moss with core features:

- Semantic search using transformer-based embeddings
- Lightweight embedding models for edge computing; supports proprietary "moss-minilm" and "moss-mediumlm" models
- Multi-index support for isolated search spaces
- Add, update, and remove documents across indexes
- Blazing fast querying support after loading indexes
- TypeScript support with full type definitions
