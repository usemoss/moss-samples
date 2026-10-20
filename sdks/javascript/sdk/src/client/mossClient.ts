import { InternalMossClient } from "./internalMossClient";
import { SessionIndex } from "./sessionIndex";
import type { IAuthenticator, AuthToken } from "../auth/authenticator.interface";
import type {
  SearchResult,
  IndexInfo,
  DocumentInfo,
  GetDocumentsOptions,
  QueryOptions,
  MutationResult,
  JobStatusResponse,
} from "@moss-js/moss-core";
import { validateIndexName } from "@moss-js/moss-core";
import {
  LoadIndexOptions,
  LoadIndexesResult,
  CreateIndexOptions,
  CreateIndexFromFilesOptions,
  ParseFileInput,
  MutationOptions,
  MossModel,
  MossClientOptions,
  ModelArtifactIdentity,
  CreateWebSourceOptions,
  CreateWebSourceResult,
  DeleteWebSourceResult,
  ResyncWebSourceResult,
  UpdateWebSourceOptions,
  UpdateWebSourceResult,
  WebSource,
} from "../models";
import { requestManage } from "../utils/manageHttp";

const DEFAULT_MODEL_ID: MossModel = "moss-minilm";

/**
 * MossClient - Async-first semantic search client for vector similarity operations.
 *
 * All mutations (createIndex, addDocs, deleteDocs) are async operations
 * that run server-side and poll until complete.
 *
 * @example
 * ```typescript
 * import { MossClient } from '@moss-js/moss';
 *
 * const client = new MossClient('your-project-id', 'your-project-key');
 *
 * // Create an index with documents (polls until complete)
 * const result = await client.createIndex('docs', [
 *   { id: '1', text: 'Machine learning fundamentals' },
 *   { id: '2', text: 'Deep learning neural networks' }
 * ]);
 *
 * // Add docs (polls until complete)
 * await client.addDocs('docs', [
 *   { id: '3', text: 'Natural language processing' }
 * ]);
 *
 * // Query the index
 * await client.loadIndex('docs');
 * const results = await client.query('docs', 'AI and neural networks');
 * ```
 */
export class MossClient {
  #internal: InternalMossClient;
  /** Project id; needed to construct `SessionIndex` instances via `session()`. */
  readonly #projectId: string;
  /**
   * Project key from the `(projectId, projectKey)` overload.
   * `null` with an `IAuthenticator`: `session()` then authenticates
   * through the auth bridge, and the web source methods, which need the key, reject.
   */
  readonly #projectKey: string | null;
  /** The `cachePath` option, the default root for session snapshots. */
  readonly #cachePath?: string;
  #closed = false;
  #closePromise?: Promise<void>;
  #sessions = new Set<WeakRef<SessionIndex>>();

  /**
   * Creates a new MossClient instance.
   * @param projectId - Your project identifier.
   * @param projectKey - Your project key (server-side use).
   * @param options - Optional cache path and stable host identity.
   */
  constructor(projectId: string, projectKey: string, options?: MossClientOptions);
  /**
   * Creates a new MossClient instance.
   * @param projectId - Your project identifier.
   * @param authenticator - Custom IAuthenticator (browser/delegated auth use).
   * @param options - Optional cache path and stable host identity.
   */
  constructor(projectId: string, authenticator: IAuthenticator, options?: MossClientOptions);
  constructor(
    projectId: string,
    auth: string | IAuthenticator,
    options?: MossClientOptions,
  ) {
    this.#internal = new InternalMossClient(projectId, auth, options);
    this.#projectId = projectId;
    this.#projectKey = typeof auth === "string" ? auth : null;
    this.#cachePath = options?.cachePath;
  }

  async getAuthToken(): Promise<AuthToken> {
    this.#ensureOpen();
    return this.#internal.getAuthToken();
  }


  /**
   * Creates a new index with the provided documents via async upload.
   *
   * Handles the full flow: init → upload → build → poll until complete.
   * Returns when the index is ready.
   *
   * When all documents have pre-computed embeddings, they are serialized as raw
   * float32 in the binary upload. When no documents have embeddings, the server
   * generates embeddings in batches (dimension=0 flow).
   *
   * Mixed documents (some with embeddings, some without) are rejected.
   *
   * @param indexName - Name of the index to create.
   * @param docs - Documents, optionally with pre-computed embeddings.
   * @param options - Optional model ID and progress callback.
   * @returns Promise that resolves to MutationResult when the index is ready.
   * @throws {Error} If the index already exists or creation fails.
   *
   * @example
   * ```typescript
   * const result = await client.createIndex('knowledge-base', [
   *   { id: 'doc1', text: 'Introduction to AI' },
   *   { id: 'doc2', text: 'Machine learning basics' }
   * ], {
   *   onProgress: (p) => console.log(`${p.status} ${p.progress}%`),
   * });
   * ```
   */
  async createIndex(
    indexName: string,
    docs: DocumentInfo[],
    options?: CreateIndexOptions,
  ): Promise<MutationResult> {
    this.#ensureOpen();
    let resolvedModelId: string;
    if (options?.modelId !== undefined) {
      resolvedModelId = options.modelId;
    } else {
      const hasEmbeddings = docs.some(
        (doc) => Array.isArray(doc.embedding) && doc.embedding.length > 0,
      );
      resolvedModelId = hasEmbeddings ? "custom" : DEFAULT_MODEL_ID;
    }
    return this.#internal.createIndex(indexName, docs, resolvedModelId, options);
  }

  /**
   * Creates a new index by uploading raw files for server-side parsing and embedding.
   *
   * Handles the full flow: init → upload files → confirm → poll until complete.
   * Returns when the index is ready.
   *
   * @param indexName - Name of the index to create.
   * @param files - File descriptors. `name` and `contentType` are required on
   * each; supply either `path` or `data`. Supported types are PDF and DOCX.
   * @param options - Model ID (defaults to "moss-minilm"), extraction controls
   * via `parseOptions`, and a progress callback.
   * @returns Promise that resolves to MutationResult when the index is ready.
   * @throws {Error} If files is empty, exceeds 20 files, or creation fails.
   *
   * @example
   * ```typescript
   * const result = await client.createIndexFromFiles('knowledge-base', [
   *   {
   *     name: 'report.pdf',
   *     contentType: 'application/pdf',
   *     path: '/docs/report.pdf',
   *   },
   *   {
   *     name: 'manual.docx',
   *     contentType:
   *       'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
   *     path: '/docs/manual.docx',
   *   },
   * ]);
   * ```
   *
   * @example Scanned documents with no text layer need OCR forced on.
   * ```typescript
   * await client.createIndexFromFiles('scans', files, {
   *   parseOptions: { ocrMode: 'full_ocr' },
   * });
   * ```
   */
  async createIndexFromFiles(
    indexName: string,
    files: ParseFileInput[],
    options?: CreateIndexFromFilesOptions,
  ): Promise<MutationResult> {
    this.#ensureOpen();
    return this.#internal.createIndexFromFiles(indexName, files, options);
  }

  /**
   * Gets information about a specific index.
   *
   * @param indexName - Name of the index to retrieve.
   * @returns Promise that resolves to IndexInfo object.
   * @throws {Error} If the index does not exist.
   *
   * @example
   * ```typescript
   * const info = await client.getIndex('knowledge-base');
   * console.log(`Index has ${info.docCount} documents`);
   * ```
   */
  async getIndex(indexName: string): Promise<IndexInfo> {
    this.#ensureOpen();
    return this.#internal.getIndex(indexName);
  }

  /**
   * Lists all available indexes.
   *
   * @returns Promise that resolves to array of IndexInfo objects.
   *
   * @example
   * ```typescript
   * const indexes = await client.listIndexes();
   * indexes.forEach(index => {
   *   console.log(`${index.name}: ${index.docCount} docs`);
   * });
   * ```
   */
  async listIndexes(): Promise<IndexInfo[]> {
    this.#ensureOpen();
    return this.#internal.listIndexes();
  }

  /**
   * Deletes an index and all its data.
   *
   * @param indexName - Name of the index to delete.
   * @returns Promise that resolves to true if successful.
   * @throws {Error} If the index does not exist.
   *
   * @example
   * ```typescript
   * const deleted = await client.deleteIndex('old-index');
   * ```
   */
  async deleteIndex(indexName: string): Promise<boolean> {
    this.#ensureOpen();
    return this.#internal.deleteIndex(indexName);
  }


  /**
   * Adds or updates documents in an index asynchronously.
   *
   * The index rebuild happens server-side. This method polls until
   * the rebuild is complete and then returns.
   *
   * @param indexName - Name of the target index.
   * @param docs - Documents to add or update.
   * @param options - Optional configuration (upsert, onProgress callback).
   * @returns Promise that resolves to MutationResult when the operation is complete.
   * @throws {Error} If the index does not exist.
   *
   * @example
   * ```typescript
   * const result = await client.addDocs('knowledge-base', [
   *   { id: 'new-doc', text: 'New content to index' }
   * ], { upsert: true });
   * console.log(`Job ${result.jobId} completed`);
   * ```
   */
  async addDocs(
    indexName: string,
    docs: DocumentInfo[],
    options?: MutationOptions,
  ): Promise<MutationResult> {
    this.#ensureOpen();
    return this.#internal.addDocs(indexName, docs, options);
  }

  /**
   * Deletes documents from an index by their IDs asynchronously.
   *
   * The index rebuild happens server-side. This method polls until
   * the rebuild is complete and then returns.
   *
   * @param indexName - Name of the target index.
   * @param docIds - Array of document IDs to delete.
   * @param options - Optional configuration (onProgress callback).
   * @returns Promise that resolves to MutationResult when the operation is complete.
   * @throws {Error} If the index does not exist.
   *
   * @example
   * ```typescript
   * const result = await client.deleteDocs('knowledge-base', ['doc1', 'doc2']);
   * console.log(`Job ${result.jobId} completed`);
   * ```
   */
  async deleteDocs(
    indexName: string,
    docIds: string[],
    options?: MutationOptions,
  ): Promise<MutationResult> {
    this.#ensureOpen();
    return this.#internal.deleteDocs(indexName, docIds, options);
  }


  /**
   * Gets the current status of an async job.
   *
   * @param jobId - The job ID returned by createIndex, addDocs, or deleteDocs.
   * @returns Promise that resolves to JobStatusResponse with progress details.
   *
   * @example
   * ```typescript
   * const status = await client.getJobStatus(jobId);
   * console.log(`${status.status} — ${status.progress}%`);
   * ```
   */
  async getJobStatus(jobId: string): Promise<JobStatusResponse> {
    this.#ensureOpen();
    return this.#internal.getJobStatus(jobId);
  }

  /**
   * POST `createWebSource` and return the typed source plus `jobId` for
   * `getJobStatus`. Server-release notes: see the package README Web sources
   * section.
   */
  async createWebSource(
    rootUrl: string,
    indexName: string,
    options?: CreateWebSourceOptions,
  ): Promise<CreateWebSourceResult> {
    this.#ensureOpen();
    validateIndexName(indexName);
    return this.#requestManage<CreateWebSourceResult>("createWebSource", {
      rootUrl,
      indexName,
      maxPages: options?.maxPages,
      maxDocuments: options?.maxDocuments,
      maxDepth: options?.maxDepth,
      includePaths: options?.includePaths,
      excludePaths: options?.excludePaths,
      respectRobots: options?.respectRobots,
      parseDocuments: options?.parseDocuments,
      refreshCadence: options?.refreshCadence,
      modelId: options?.modelId,
    });
  }

  /**
   * POST `listWebSources` and return the typed sources. When `indexName` is
   * given, only sources for that index are returned.
   */
  async listWebSources(indexName?: string): Promise<WebSource[]> {
    this.#ensureOpen();
    const result = await this.#requestManage<{ sources: WebSource[]; }>(
      "listWebSources",
      indexName !== undefined ? { indexName } : undefined,
    );
    const sources = result.sources ?? [];
    if (indexName === undefined) {
      return sources;
    }
    return sources.filter((source) => source.indexName === indexName);
  }

  /**
   * POST `getWebSource` and return the typed source: crawl status, last run,
   * and page/document counts.
   */
  async getWebSource(sourceId: string): Promise<WebSource> {
    this.#ensureOpen();
    return this.#requestManage<WebSource>("getWebSource", { sourceId });
  }

  /**
   * POST `updateWebSource` and return the typed source. `jobId` is present
   * when `resync` is true and the server enqueued a crawl; poll with
   * `getJobStatus`. `refreshCadence` is live today. Other fields: see the
   * package README Web sources section.
   */
  async updateWebSource(
    sourceId: string,
    options: UpdateWebSourceOptions,
  ): Promise<UpdateWebSourceResult> {
    this.#ensureOpen();
    return this.#requestManage<UpdateWebSourceResult>("updateWebSource", {
      sourceId,
      refreshCadence: options.refreshCadence,
      rootUrl: options.rootUrl,
      includePaths: options.includePaths,
      excludePaths: options.excludePaths,
      maxDepth: options.maxDepth,
      maxPages: options.maxPages,
      resync: options.resync,
    });
  }

  /**
   * POST `resyncWebSource` and return a `jobId` to poll with `getJobStatus`.
   * See the package README Web sources section.
   */
  async resyncWebSource(sourceId: string): Promise<ResyncWebSourceResult> {
    this.#ensureOpen();
    return this.#requestManage<ResyncWebSourceResult>("resyncWebSource", {
      sourceId,
    });
  }

  /**
   * POST `deleteWebSource` and return `{ deleted, id }`. `purgeJobId` is
   * present when a purge was enqueued; poll with `getJobStatus`. Does not
   * delete the index.
   */
  async deleteWebSource(sourceId: string): Promise<DeleteWebSourceResult> {
    this.#ensureOpen();
    return this.#requestManage<DeleteWebSourceResult>("deleteWebSource", {
      sourceId,
    });
  }

  async #requestManage<T>(
    action: string,
    data?: Record<string, unknown>,
  ): Promise<T> {
    if (this.#projectKey === null) {
      throw new Error(
        "Web source methods require a project key. Construct MossClient with (projectId, projectKey).",
      );
    }
    return requestManage<T>(this.#projectId, this.#projectKey, action, data);
  }


  /**
   * Retrieves documents from an index.
   *
   * @param indexName - Name of the target index.
   * @param options - Optional configuration for retrieval.
   * @returns Promise that resolves to array of documents.
   * @throws {Error} If the index does not exist.
   *
   * @example
   * ```typescript
   * // Get all documents
   * const allDocs = await client.getDocs('knowledge-base');
   *
   * // Get specific documents
   * const specificDocs = await client.getDocs('knowledge-base', {
   *   docIds: ['doc1', 'doc2']
   * });
   * ```
   */
  async getDocs(
    indexName: string,
    options?: GetDocumentsOptions,
  ): Promise<DocumentInfo[]> {
    this.#ensureOpen();
    return this.#internal.getDocs(indexName, options);
  }


  /**
   * Downloads an index from the cloud into memory for fast local querying.
   *
   * **How it works:**
   * 1. Fetches the index assets from the cloud
   * 2. Loads the exact embedding model when the index has an immutable model
   *    artifact identity
   * 3. Executes a local similarity match between the query embedding and the retrieved index.
   *
   * A foundation index without an exact artifact identity can still be loaded,
   * but local queries must provide `QueryOptions.embedding`. The client will
   * not generate an embedding from an unverified model artifact.
   *
   * **Why use this?**
   * - `query()` requires a loaded index; without `loadIndex()` it rejects with a not-loaded error
   * - With `loadIndex()`: Queries run entirely in-memory (~1-10ms) with no network round-trip
   *
   * **Reload behavior:**
   * If the index is already loaded, calling `loadIndex()` again will:
   * - Stop any existing auto-refresh polling
   * - Download a fresh copy from the cloud
   * - Replace the in-memory index
   *
   * **Auto-refresh (optional):**
   * Enable `autoRefresh: true` to periodically poll the cloud for updates.
   * When a newer version is detected, the index is automatically hot-swapped
   * without interrupting queries.
   *
   * @param indexName - Name of the index to load.
   * @param options - Optional configuration including auto-refresh settings.
   * @returns Promise that resolves to the index name.
   * @throws {Error} If the index does not exist in the cloud or loading fails.
   *
   * @example
   * ```typescript
   * // Simple load - enables fast local queries
   * await client.loadIndex('my-index');
   *
   * // Now queries run locally (fast, no network calls)
   * // A text-only query requires an exact immutable model artifact identity.
   * const results = await client.query('my-index', 'search text');
   *
   * // Load with auto-refresh to keep index up-to-date
   * await client.loadIndex('my-index', {
   *   autoRefresh: true,
   *   pollingIntervalInSeconds: 300, // Check cloud every 5 minutes
   * });
   *
   * // Stop auto-refresh by reloading without the option
   * await client.loadIndex('my-index');
   * ```
   */
  async loadIndex(indexName: string, options?: LoadIndexOptions): Promise<string> {
    this.#ensureOpen();
    return this.#internal.loadIndex(indexName, options);
  }

  /**
   * Loads several indexes into memory in one call. Best-effort: a name that
   * fails (typo, deleted index, download error) is reported in `failed` and
   * does not roll back the indexes that loaded. `options` apply to the whole
   * batch, and each distinct embedding model is warmed once.
   *
   * @param indexNames - Names of the indexes to load.
   * @param options - Auto-refresh and cache settings shared by the batch.
   * @returns `{ loaded, failed }` where `failed` maps a name to its error.
   *
   * @example
   * ```typescript
   * const { loaded, failed } = await client.loadIndexes(['products', 'reviews']);
   * ```
   */
  async loadIndexes(indexNames: string[], options?: LoadIndexOptions): Promise<LoadIndexesResult> {
    this.#ensureOpen();
    return this.#internal.loadIndexes(indexNames, options);
  }

  /**
   * Removes a loaded index from memory and stops its auto-refresh poller.
   * Subsequent `query` calls for that name fail until it is loaded again.
   */
  async unloadIndex(indexName: string): Promise<void> {
    this.#ensureOpen();
    return this.#internal.unloadIndex(indexName);
  }

  /**
   * Removes several loaded indexes from memory. Best-effort and idempotent:
   * names that are not loaded are ignored.
   */
  async unloadIndexes(indexNames: string[]): Promise<void> {
    this.#ensureOpen();
    return this.#internal.unloadIndexes(indexNames);
  }

  /**
   * Performs a semantic similarity search against a locally loaded index.
   *
   * The index must have been loaded via `loadIndex()` or `loadIndexes()`;
   * queries run entirely in-memory with no network round-trip. Querying an
   * index that is not loaded rejects with a `NOT_FOUND` error naming the load call.
   *
   * Loaded foundation indexes require an exact model artifact identity before
   * Moss can generate query embeddings locally. For an older identity-less
   * index, provide a caller-generated vector through `options.embedding`.
   *
   * A blank `query` (empty or only whitespace) with no `options.embedding`
   * returns no results at every `alpha`, without running the embedding model.
   * With an embedding, a blank `query` ranks by the embedding alone. An
   * embedding holding NaN or infinity, or one whose length differs from the
   * index dimension, rejects at every `alpha`.
   *
   * @param indexName - Name of the target index to search.
   * @param query - The search query text.
   * @param options - Optional query configuration including topK (default: 5; 0 returns no results), embedding overrides, minScore, and candidateDepth.
   * @returns Promise that resolves to SearchResult with matching documents.
   * @throws {Error} If the index is not loaded.
   *
   * @example
   * ```typescript
   * await client.loadIndex('knowledge-base');
   * const results = await client.query('knowledge-base', 'machine learning');
   * results.docs.forEach(doc => {
   *   console.log(`${doc.id}: ${doc.text} (score: ${doc.score})`);
   * });
   * ```
   */
  async query(
    indexName: string,
    query: string,
    options?: QueryOptions,
  ): Promise<SearchResult> {
    this.#ensureOpen();
    return this.#internal.query(indexName, query, options);
  }

  /**
   * Searches several loaded indexes in one call and returns the global top-k
   * across all of them, with each result's `indexName` set to its source.
   *
   * All names must already be loaded (`loadIndex` / `loadIndexes`) and share
   * the same embedding model; there is no cloud fallback. `options.alpha`
   * works exactly as in `query` (default 0.8): `1.0` is embedding-only, `0.0`
   * is keyword-only, and values in between fuse both signals. Every mix returns
   * results in hybrid order with the same relevance `score` as single-index
   * `query`, and `options.minScore` filters on that score. Keyword scoring
   * runs each index's own BM25 and merges hits before fusion. `options.topK`
   * (default 10) caps the merged result, not each index, and 0 returns no
   * results. `options.filter` applies uniformly to every index. A blank
   * `query` with no `options.embedding` returns no results and embeds nothing.
   *
   * @param indexNames - Names of the loaded indexes to search.
   * @param query - The search query text.
   * @param options - Optional topK, alpha, embedding, filter, minScore, and candidateDepth.
   * @returns SearchResult whose docs carry `indexName`.
   * @throws {Error} If no names are given, a name is not loaded, or models differ.
   *
   * @example
   * ```typescript
   * await client.loadIndexes(['products', 'reviews']);
   * const results = await client.queryMultiIndex(
   *   ['products', 'reviews'],
   *   'noise cancelling headphones',
   *   { topK: 5, alpha: 0.5 },
   * );
   * results.docs.forEach(doc => console.log(doc.indexName, doc.id, doc.score));
   * ```
   */
  async queryMultiIndex(
    indexNames: string[],
    query: string,
    options?: QueryOptions,
  ): Promise<SearchResult> {
    this.#ensureOpen();
    return this.#internal.queryMultiIndex(indexNames, query, options);
  }

  /**
   * Create a local-first session index for real-time, in-process indexing
   * and querying. The session starts empty; call `loadIndex` to pull an
   * existing cloud index in, `addDocs` to populate, `query` to search,
   * and `pushIndex` at session end to persist to the cloud.
   *
   * @param indexName Logical name for the session. Identifies the cloud
   *   index when `pushIndex` / `loadIndex` is called.
   * @param modelId Embedding model to use. Defaults to `moss-minilm`.
   *   Pass `"custom"` if you'll supply embeddings yourself.
   *
   * Works with both a static project key and a custom `IAuthenticator`,
   * which the session uses the same way `loadIndex` does.
   *
   * @example
   * ```typescript
   * const session = await client.session('chat-session-123');
   * await session.addDocs([{ id: '1', text: 'Customer asked about billing' }]);
   * const results = await session.query('billing question');
   * await session.pushIndex();
   * ```
   */
  async session(
    indexName: string,
    modelId: MossModel = DEFAULT_MODEL_ID,
    modelArtifact?: ModelArtifactIdentity,
  ): Promise<SessionIndex> {
    this.#ensureOpen();
    const applyIdentity = this.#internal.applySessionIdentity;
    let session: SessionIndex;
    if (this.#projectKey !== null) {
      session = await SessionIndex._create(
        indexName,
        modelId,
        this.#projectId,
        this.#projectKey,
        undefined,
        applyIdentity,
        modelArtifact,
        this.#cachePath,
      );
    } else {
      // Custom-authenticator path: build the core session through the auth
      // bridge (no static project key), then wrap it.
      const inner = await this.#internal.createAuthenticatedSessionInner(
        indexName,
        modelId,
        modelArtifact,
      );
      session = SessionIndex._fromInner(indexName, inner, applyIdentity, this.#cachePath);
    }
    // Pre-load the bundled embedding model for built-in modelIds so the
    // first `addDocs`/`query` doesn't pay cold-start latency. No-op for
    // `"custom"` (no local model in that case).
    await session._warmModel();
    for (const ref of this.#sessions) {
      if (!ref.deref()) this.#sessions.delete(ref);
    }
    this.#sessions.add(new WeakRef(session));
    return session;
  }

  #ensureOpen(): void {
    if (this.#closed) {
      throw new Error("MossClient is closed");
    }
  }

  /**
   * Release the client's native resources (the index manager's loaded
   * indexes, pollers, and telemetry). Idempotent. All client methods
   * reject with "MossClient is closed" afterwards. Does not stop the
   * process-wide shared runtime.
   *
   * Also closes every live session created by this client (sessions can
   * still be closed individually first; close is idempotent).
   */
  close(): Promise<void> {
    // A rejected close stays cached: the only rejection path is the
    // version-mismatch guard (native close is infallible), which no
    // retry can fix.
    this.#closePromise ??= this.#closeInner();
    return this.#closePromise;
  }

  async #closeInner(): Promise<void> {
    this.#closed = true;
    const sessions = [...this.#sessions]
      .map((ref) => ref.deref())
      .filter((s): s is SessionIndex => s !== undefined);
    this.#sessions.clear();
    await Promise.all(sessions.map((s) => s.close()));
    await this.#internal.close();
  }

  async [Symbol.asyncDispose](): Promise<void> {
    return this.close();
  }

}
