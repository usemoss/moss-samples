/**
 * Local-first session index — TypeScript wrapper around the napi
 * `SessionIndex` exposed by `@moss-js/moss-core`.
 *
 * Mirrors the Python SDK's `moss.client.session_index` module 1:1 so
 * the two SDKs present the same conceptual model to users.
 */

import {
  SessionIndex as CoreSessionIndex,
  type AddDocumentsOptions,
  type DocumentInfo,
  type GetDocumentsOptions,
  type LoadFromDiskOptions,
  type LoadSessionOptions,
  type PushIndexResult,
  type QueryOptions,
  type SearchResult,
  type SnapshotInfo,
} from "@moss-js/moss-core";

import { mossError } from "../errors";
import type { ModelArtifactIdentity, MossModel, MutationOptions } from "../models";
import type { IdentityTarget } from "../utils/deviceId";
import { assertModelArtifactContractSupported } from "./helpers";

/**
 * A local in-session index for real-time indexing and querying.
 *
 * All operations (`addDocs`, `deleteDocs`, `query`) run entirely in
 * process memory with no cloud round-trip, on a native worker thread so
 * the Node event loop stays responsive. Call `pushIndex()` at the end of
 * a session to persist the result to the cloud.
 *
 * @example
 * ```typescript
 * const session = await client.session('session-abc');
 * await session.addDocs([
 *   { id: '1', text: 'Customer asked about billing' },
 * ]);
 * const results = await session.query('billing question');
 * const result = await session.pushIndex();
 * ```
 */
export class SessionIndex {
  readonly #inner: CoreSessionIndex;
  readonly #name: string;
  readonly #clientCachePath: string | null;
  #closed = false;
  #closePromise?: Promise<void>;

  /**
   * @internal Construct via `MossClient.session()` — direct instantiation
   * is intentionally unsupported so the auth context flows from the client.
   */
  constructor(name: string, inner: CoreSessionIndex, clientCachePath?: string) {
    this.#name = name;
    this.#inner = inner;
    this.#clientCachePath = clientCachePath ?? null;
  }

  /**
   * @internal Factory used by `MossClient.session()`. Constructs the
   * underlying Rust `SessionIndex` and wraps it. Async because the
   * napi `SessionIndex.create` runs credential validation on a
   * worker thread — `await`ing here keeps the Node main thread
   * responsive while auth is in flight.
   */
  static async _create(
    name: string,
    modelId: MossModel,
    projectId: string,
    projectKey: string,
    clientId?: string,
    applyIdentity?: (target: IdentityTarget) => void,
    modelArtifact?: ModelArtifactIdentity,
    clientCachePath?: string,
  ): Promise<SessionIndex> {
    type IdentityAwareSessionFactory = {
      modelArtifactContractVersion?: () => number;
      create(
        name: string,
        modelId: string,
        projectId: string,
        projectKey: string,
        clientId?: string | null,
        artifactVersion?: string | null,
        manifestSha256?: string | null,
      ): Promise<CoreSessionIndex>;
    };
    const factory = CoreSessionIndex as unknown as IdentityAwareSessionFactory;
    if (modelArtifact) {
      assertModelArtifactContractSupported(factory);
    }
    const inner = await factory.create(
      name,
      modelId,
      projectId,
      projectKey,
      clientId ?? null,
      modelArtifact?.version ?? null,
      modelArtifact?.manifestSha256 ?? null,
    );
    return SessionIndex._fromInner(name, inner, applyIdentity, clientCachePath);
  }

  /**
   * @internal Wrap an already-constructed core `SessionIndex` — used for the
   * custom-authenticator path, where `InternalMossClient` builds the core
   * handle via the auth bridge (`SessionIndex.withAuthenticator`).
   */
  static _fromInner(
    name: string,
    inner: CoreSessionIndex,
    applyIdentity?: (target: IdentityTarget) => void,
    clientCachePath?: string,
  ): SessionIndex {
    applyIdentity?.(inner as unknown as IdentityTarget);
    return new SessionIndex(name, inner, clientCachePath);
  }

  /** The session index name. Identifies the cloud index on `pushIndex` / `loadIndex`. */
  get name(): string {
    return this.#name;
  }

  /**
   * Number of documents currently in the local session. Synchronous and
   * never waits: it reports the count as of the last completed operation.
   * A staged auto-refresh version is applied on a worker thread and shows
   * up on a later read.
   */
  get docCount(): number {
    this.#ensureOpen();
    return this.#inner.docCount;
  }

  /**
   * The model this session embeds with, as of its last completed call.
   * `addDocs` and `query` read it on every call to pick their path, and
   * `loadIndex`, `loadFromDisk` or a version that auto-refresh installs can change it.
   */
  get modelId(): MossModel {
    return this.#inner.modelId as MossModel;
  }

  /**
   * Add or update documents in the local session index.
   *
   * For models other than `"custom"`, embeddings are generated locally
   * via the Rust core on a native worker thread, with no cloud round-trip
   * and no main-thread stall while a large batch is embedded. For
   * `modelId="custom"`, each document **must** carry an `.embedding` field.
   *
   * @returns `{ added, updated }` counts.
   */
  async addDocs(
    docs: DocumentInfo[],
    options?: MutationOptions,
  ): Promise<{ added: number; updated: number }> {
    this.#ensureOpen();
    // `AddDocumentsOptions` is emitted as a plain TS interface by napi-rs,
    // not a class — construct it as an object literal.
    const rustOpts: AddDocumentsOptions | undefined = options
      ? { upsert: options.upsert ?? true }
      : undefined;

    if (this.modelId === "custom") {
      const embeddings = SessionIndex.#requireCustomEmbeddings(docs);
      // Strip `.embedding` from each doc before crossing the napi
      // boundary. The Rust core drops `doc.embedding` immediately
      // (vectors flow through the parallel `embeddings` array), so
      // sending them inside `docs` is wasted marshalling — for
      // dense vectors over many docs this can be megabytes.
      const slimDocs = docs.map((doc) => {
        const slimDoc = { ...doc };
        delete slimDoc.embedding;
        return slimDoc;
      });
      const result = await this.#inner.addDocuments(slimDocs, embeddings, rustOpts);
      return { added: result.added, updated: result.updated };
    }

    const result = await this.#inner.addDocumentsText(docs, rustOpts);
    return { added: result.added, updated: result.updated };
  }

  /** Delete documents from the local session by id. Returns the number actually removed. */
  async deleteDocs(docIds: string[]): Promise<number> {
    this.#ensureOpen();
    return await this.#inner.deleteDocuments(docIds);
  }

  /** Fetch documents currently in the local session. Pass `options.docIds` to filter. */
  async getDocs(options?: GetDocumentsOptions): Promise<DocumentInfo[]> {
    this.#ensureOpen();
    return await this.#inner.getDocuments(options ?? null);
  }

  /**
   * Hybrid (keyword + semantic) search over the local session index.
   * Runs entirely in-memory, no cloud call.
   *
   * For `modelId="custom"`, an explicit `options.embedding` is required.
   * For built-in models the query is embedded locally by the Rust core
   * on a native worker thread if `options.embedding` is omitted.
   *
   * A blank `query` (empty or only whitespace) with no `options.embedding`
   * returns no results at every `alpha`, without running the embedding model.
   * With an embedding, a blank `query` ranks by the embedding alone.
   * A custom-model session still needs `options.embedding`.
   * `options.topK` defaults to 5, and 0 returns no results.
   */
  async query(query: string, options?: QueryOptions): Promise<SearchResult> {
    this.#ensureOpen();
    const topK = options?.topK ?? 5;
    const alpha = options?.alpha ?? 0.8;
    const filter = options?.filter ?? null;
    const queryEmbedding = options?.embedding;

    if (queryEmbedding === undefined || queryEmbedding === null) {
      if (this.modelId === "custom") {
        throw mossError(
          "INVALID_ARGUMENT",
          "This session uses custom embeddings. " +
            "Provide a query embedding via QueryOptions.embedding.",
        );
      }
      return await this.#inner.queryText(query, topK, alpha, filter);
    }

    return await this.#inner.query(
      query,
      topK,
      Array.from(queryEmbedding),
      alpha,
      filter,
    );
  }

  /**
   * Load an existing cloud index into the session by name. With
   * `options.autoRefresh = true`, the SDK polls the cloud index and
   * pulls newer versions in on subsequent reads; the poller pauses
   * while local un-pushed edits exist.
   *
   * The index replaces this session's documents and model, so after a
   * custom-model index loads, `addDocs` and `query` need embeddings.
   * Auto-refresh can install a custom-model version the same way.
   *
   * @returns Number of documents loaded into the session.
   */
  async loadIndex(
    indexName: string,
    options?: LoadSessionOptions,
  ): Promise<number> {
    this.#ensureOpen();
    return this.#inner.loadIndex(indexName, options ?? null);
  }

  /**
   * Upload the session to the cloud, creating or replacing the index
   * with the same name. A custom-model session keeps its locally-computed
   * embeddings; for a built-in model the server re-embeds the text with
   * that model, so the index loads and answers text queries like one
   * built with `createIndex`.
   */
  async pushIndex(): Promise<PushIndexResult> {
    this.#ensureOpen();
    return this.#inner.pushIndex();
  }

  /**
   * Persist the session to `<cachePath>/<name>/` for offline reuse
   * without a cloud round-trip.
   *
   * A relative `cachePath` resolves against the current working directory,
   * and `~` is not expanded. Without `cachePath` the snapshot goes in
   * `sessions/<project id>/` under the client's `cachePath` option, else under the
   * `MOSS_SESSION_CACHE_PATH` environment variable, which only session snapshots
   * read, else under `moss` in the default cache directory (`~/.cache` on macOS
   * and Linux, `%LOCALAPPDATA%` on Windows).
   */
  async saveToDisk(cachePath?: string): Promise<void> {
    this.#ensureOpen();
    await this.#inner.saveToDisk(cachePath ?? null, this.#clientCachePath);
  }

  /**
   * Restore a session previously written by `saveToDisk`. Without
   * `cachePath` it reads the directory `saveToDisk` uses without one.
   *
   * The snapshot replaces this session's documents and model, so after a
   * custom-model snapshot loads, `addDocs` and `query` need embeddings.
   *
   * A snapshot saved by an SDK older than 1.8 for a built-in model carries
   * no model artifact provenance, so the core can only restore it as a
   * custom-model session. This method asks the core to rebuild such a
   * snapshot instead, which it does only for a session opened with the same
   * built-in model: the stored documents are re-embedded with the current
   * model (one-time cost, needs the cloud for the model) and the upgraded
   * snapshot is saved back, all in one operation, so it happens once per
   * device. Custom-model sessions and a snapshot of a different model load
   * as before. Pass `{ rebuildLegacy: false }` to opt out.
   *
   * When the rebuild cannot load the model, for example offline, the
   * call rejects with a message starting "Legacy snapshot rebuild needs the
   * embedding model" and changes nothing: the snapshot is intact and the
   * session is as it was. Retry later; do not treat it as a corrupt cache.
   * @returns Number of documents loaded.
   */
  async loadFromDisk(cachePath?: string, options?: LoadFromDiskOptions): Promise<number> {
    this.#ensureOpen();
    const rebuildLegacy = options?.rebuildLegacy ?? true;
    return await this.#inner.loadFromDisk(
      cachePath ?? null,
      { rebuildLegacy },
      this.#clientCachePath,
    );
  }

  /**
   * Describe the snapshot under `<cachePath>/<name>/` without loading it:
   * the model it was saved with, whether it carries model artifact
   * provenance, and its size. `modelId` is a built-in model with
   * `hasModelArtifact: false` for snapshots saved before 1.8, which
   * `loadFromDisk` rebuilds by default. Without `cachePath` it reads the
   * directory `saveToDisk` uses without one.
   */
  async inspectSnapshot(cachePath?: string): Promise<SnapshotInfo> {
    this.#ensureOpen();
    return await this.#inner.inspectSnapshot(cachePath ?? null, this.#clientCachePath);
  }

  #ensureOpen(): void {
    if (this.#closed) {
      throw new Error(`SessionIndex '${this.#name}' is closed`);
    }
  }

  /**
   * Release the session's native resources deterministically: the
   * auto-refresh poller, the in-memory index, and this session's
   * reference to the shared embedding model. Safe to call more than
   * once. Afterwards `name` and `modelId` stay readable (`modelId` as
   * of the last call); `docCount` and all methods throw "is closed".
   *
   * Also invoked by `await using` (Symbol.asyncDispose).
   */
  close(): Promise<void> {
    // A rejected close stays cached: the native close is infallible, so the
    // only rejection is the version-mismatch guard below, which no retry
    // can fix and every caller should keep hearing about.
    this.#closePromise ??= this.#closeInner();
    return this.#closePromise;
  }

  async #closeInner(): Promise<void> {
    this.#closed = true;
    const close = (this.#inner as unknown as { close?: () => Promise<void> }).close;
    if (typeof close !== "function") {
      // A silent no-op here would leak the native session and model memory.
      throw new Error(
        "@moss-js/moss-core >= 0.20.0 is required for SessionIndex.close()",
      );
    }
    await close.call(this.#inner);
  }

  async [Symbol.asyncDispose](): Promise<void> {
    return this.close();
  }

  // -- Compatibility warm-up hook --

  /**
   * @internal Pre-loads the bundled embedding model for built-in
   * `modelId`s; no-op for `"custom"`. Called by `MossClient.session()`
   * so the first `addDocs` / `query` doesn't pay cold-start latency. The
   * download and runtime initialization run on a native worker thread.
   */
  async _warmModel(): Promise<void> {
    this.#ensureOpen();
    if (this.modelId !== "custom") {
      await this.#inner.loadModel();
    }
  }

  static #requireCustomEmbeddings(docs: DocumentInfo[]): number[][] {
    const missing = docs
      .filter((d) => !d.embedding || d.embedding.length === 0)
      .map((d) => d.id);
    if (missing.length > 0) {
      throw new Error(
        `Documents missing .embedding for custom model: ${missing.join(", ")}. ` +
          "All documents must have .embedding set when using modelId='custom'.",
      );
    }
    return docs.map((d) => Array.from(d.embedding ?? []));
  }
}
