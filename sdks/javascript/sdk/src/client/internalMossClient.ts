import {
  LoadIndexOptions,
  LoadIndexesResult,
  CreateIndexOptions,
  CreateIndexFromFilesOptions,
  ParseFileInput,
  MutationOptions,
  ModelArtifactIdentity,
  MossClientOptions,
  MossIdentity,
  JobProgress,
  JobStatus,
  QueryOptions as SdkQueryOptions,
} from "../models";
import type {
  DocumentInfo,
  GetDocumentsOptions,
  IndexInfo,
  SearchResult,
  JobStatusResponse,
  MutationResult,
} from "@moss-js/moss-core";
import * as MossCore from "@moss-js/moss-core";
import type { IAuthenticator, AuthToken } from "../auth/authenticator.interface";
import { MossServerAuthenticator } from "../auth/moss-server.authenticator";
import { CachingAuthenticator } from "../auth/caching.authenticator";
import {
  identitySupplied,
  resolveCachePathDeviceId,
  validateMossIdentity,
  type IdentityTarget,
} from "../utils/deviceId";
import { assertModelArtifactContractSupported } from "./helpers";
import { mossError } from "../errors";

type NativeProgressCallback = (
  error: Error | null,
  progress: JobProgress,
) => void;

/** Optional settings the native query methods take after `filter`. */
interface NativeQueryTuning {
  minScore?: number;
  candidateDepth?: number;
}

/** The tuning fields of `options`, or undefined when none is set. */
function queryTuning(options?: SdkQueryOptions): NativeQueryTuning | undefined {
  if (options?.minScore === undefined && options?.candidateDepth === undefined) {
    return undefined;
  }
  return { minScore: options.minScore, candidateDepth: options.candidateDepth };
}

/** Render an unknown throwable as a diagnostic string without throwing again. */
function describeCause(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

/**
 * Validate a native progress payload against the `JobProgress` schema, and
 * return why it is unusable, or `null` when it is well formed.
 *
 * The check is structural, not enumerated: `status` and `currentPhase` are
 * validated as strings rather than against the value sets this SDK's typings
 * currently spell out, because the core owns those enums and adds members to
 * them (`parsing`, `queued`, ...) independently of an SDK release. Dropping a
 * forward-compatible phase would silently degrade a working progress stream,
 * whereas the shapes rejected here - `{}`, `[]`, a partial object, a `NaN`
 * percentage - can only come from a malformed runtime and would surface to the
 * caller's callback as a field access on something that is not a progress
 * event.
 */
function describeMalformedProgress(progress: unknown): string | null {
  if (progress === null || typeof progress !== "object") {
    return `received ${String(progress)}`;
  }
  if (Array.isArray(progress)) {
    return "received an array where a JobProgress object was expected";
  }
  const candidate = progress as Partial<Record<keyof JobProgress, unknown>>;
  if (typeof candidate.jobId !== "string" || candidate.jobId.length === 0) {
    return `received a progress event with a missing or empty jobId (${String(candidate.jobId)})`;
  }
  if (typeof candidate.status !== "string" || candidate.status.length === 0) {
    return `received a progress event with a missing or empty status (${String(candidate.status)})`;
  }
  if (typeof candidate.progress !== "number" || !Number.isFinite(candidate.progress)) {
    return `received a progress event with a non-finite progress value (${String(candidate.progress)})`;
  }
  if (
    candidate.currentPhase !== undefined &&
    candidate.currentPhase !== null &&
    typeof candidate.currentPhase !== "string"
  ) {
    return `received a progress event with a non-string currentPhase (${String(candidate.currentPhase)})`;
  }
  return null;
}

/**
 * Internal client — mutations go through Rust ManageClient,
 * local queries go through Rust IndexManager (including embedding generation).
 */

/** Structural shape of the native ParseOptions object. */
interface ParseOptionsInput {
  useHighResolution?: boolean;
  segmentationMethod?: string;
  ocrMode?: string;
  mergeTables?: boolean;
  chunkSize?: number;
  chunkOverlap?: number;
}

/**
 * The native auth bridge's request callback. `rejectedToken` is set on the
 * retry after a 401 and holds the token the Moss service rejected.
 */
type AuthNotifyFn = (
  err: Error | null,
  requestId: number,
  rejectedToken?: string | null,
) => void;

export class InternalMossClient {
  private authenticator: CachingAuthenticator;
  private readonly manageClient: {
    createIndex(name: string, docs: DocumentInfo[], modelId: string, onProgress?: NativeProgressCallback | null): Promise<MutationResult>;
    createIndexFromFiles(name: string, files: Array<{ name: string; contentType: string; path?: string | null; data?: number[] | null }>, modelId: string, onProgress?: NativeProgressCallback | null, parseOptions?: ParseOptionsInput | null): Promise<MutationResult>;
    addDocs(name: string, docs: DocumentInfo[], options?: MutationOptions | null, onProgress?: NativeProgressCallback | null): Promise<MutationResult>;
    deleteDocs(name: string, docIds: string[], onProgress?: NativeProgressCallback | null): Promise<MutationResult>;
    getJobStatus(jobId: string): Promise<JobStatusResponse>;
    getIndex(name: string): Promise<IndexInfo>;
    listIndexes(): Promise<IndexInfo[]>;
    deleteIndex(name: string): Promise<boolean>;
    getDocs(name: string, options?: GetDocumentsOptions | null): Promise<DocumentInfo[]>;
  };
  private readonly indexManager: {
    loadIndex(indexName: string, options?: LoadIndexOptions | null): Promise<IndexInfo>;
    unloadIndex(indexName: string): Promise<void>;
    hasIndex(indexName: string): Promise<boolean>;
    query(
      indexName: string,
      query: string,
      queryEmbedding: number[],
      topK?: number,
      alpha?: number,
      filter?: Record<string, unknown>,
      tuning?: NativeQueryTuning,
    ): Promise<SearchResult>;
    queryText(
      indexName: string,
      query: string,
      topK?: number,
      alpha?: number,
      filter?: Record<string, unknown>,
      tuning?: NativeQueryTuning,
    ): Promise<SearchResult>;
    loadQueryModel(indexName: string): Promise<void>;
    // Multi-index API. Optional because the SDK must still type-check and
    // load against a core that predates it; `requireMultiIndexCore` gates use.
    queryMultiIndex?(
      indexNames: string[],
      query: string,
      queryEmbedding: number[],
      topK?: number,
      alpha?: number,
      filter?: Record<string, unknown>,
      tuning?: NativeQueryTuning,
    ): Promise<SearchResult>;
    queryMultiIndexText?(
      indexNames: string[],
      query: string,
      topK?: number,
      alpha?: number,
      filter?: Record<string, unknown>,
      tuning?: NativeQueryTuning,
    ): Promise<SearchResult>;
    loadIndexes?(indexNames: string[], options?: LoadIndexOptions | null): Promise<LoadIndexesResult>;
    unloadIndexes?(indexNames: string[]): Promise<void>;
    refreshIndex(indexName: string): Promise<{ indexName: string; previousUpdatedAt: string; newUpdatedAt: string; wasUpdated: boolean }>;
    getIndexInfo(indexName: string): Promise<IndexInfo>;
    setDeviceId(deviceId: string): void;
    setIdentity?(
      deviceId?: string | null,
      userId?: string | null,
      mossDeviceId?: string | null,
    ): void;
    deviceIdentity?(): { deviceId?: string; mossDeviceId?: string } | null;
  };
  private readonly cachePathDeviceId?: string;
  private readonly configuredIdentity?: MossIdentity;
  /** Project id, retained for constructing sessions via the auth bridge. */
  private readonly projectId: string;
  /**
   * The JS-authenticator notify callback, built only on the custom-auth path.
   * Reused to construct sessions via `SessionIndex.withAuthenticator` so that
   * custom-auth clients (no static project key) can open sessions.
   */
  private readonly authNotifyFn?: AuthNotifyFn;

  constructor(
    projectId: string,
    auth: string | IAuthenticator,
    options?: MossClientOptions,
  ) {
    this.configuredIdentity = validateMossIdentity(options?.identity);
    this.cachePathDeviceId = resolveCachePathDeviceId(options?.cachePath);
    this.projectId = projectId;
    const inner =
      typeof auth === "string"
        ? new MossServerAuthenticator(projectId, auth)
        : auth;
    this.authenticator = new CachingAuthenticator(inner);

    const runtime = MossCore as unknown as {
      ManageClient?: new (projectId: string, projectKey: string) => InternalMossClient["manageClient"];
      IndexManager?: new (projectId: string, projectKey: string) => InternalMossClient["indexManager"];
      resolveAuthRequest?: (requestId: number, token: string) => void;
      rejectAuthRequest?: (requestId: number, error: string) => void;
      default?: {
        ManageClient?: new (projectId: string, projectKey: string) => InternalMossClient["manageClient"];
        IndexManager?: new (projectId: string, projectKey: string) => InternalMossClient["indexManager"];
        resolveAuthRequest?: (requestId: number, token: string) => void;
        rejectAuthRequest?: (requestId: number, error: string) => void;
      };
    };

    const ManageClientCtor = runtime.ManageClient ?? runtime.default?.ManageClient;
    const IndexManagerCtor = runtime.IndexManager ?? runtime.default?.IndexManager;
    if (!ManageClientCtor || !IndexManagerCtor) {
      throw new Error("moss-core runtime is missing ManageClient/IndexManager exports");
    }

    if (typeof auth === "string") {
      // Server-side path: CloudClient inside Rust reads MOSS_INDEX_URL from env; no URL passed here.
      this.manageClient = new ManageClientCtor(projectId, auth);
      this.indexManager = new IndexManagerCtor(projectId, auth);
    } else {
      // Custom authenticator path: wire auth bridge through the notify function
      const resolveAuthRequest =
        runtime.resolveAuthRequest ?? runtime.default?.resolveAuthRequest;
      const rejectAuthRequest =
        runtime.rejectAuthRequest ?? runtime.default?.rejectAuthRequest;

      if (!resolveAuthRequest || !rejectAuthRequest) {
        throw new Error(
          "moss-core runtime is missing resolveAuthRequest/rejectAuthRequest exports. " +
          "Ensure you are using a moss-core build that supports custom authenticators.",
        );
      }

      const authenticator = this.authenticator;
      // The native bridge parks on a receiver for every request id it hands
      // out, so once we accept an id we must settle it exactly once on every
      // branch - including when the native resolver itself throws.
      const settleReject = (requestId: number, reason: string) => {
        try {
          rejectAuthRequest(requestId, reason);
        } catch (error) {
          // Nothing further can reach the waiter; make the dead end visible
          // rather than swallowing it.
          console.warn(
            `[moss] Auth request ${requestId} could not be settled: ${describeCause(error)}`,
          );
        }
      };
      const settleResolve = (requestId: number, token: string) => {
        try {
          resolveAuthRequest(requestId, token);
        } catch (error) {
          settleReject(
            requestId,
            `moss-core rejected the auth token: ${describeCause(error)}`,
          );
        }
      };
      // NAPI-RS calls notifyFn with Node.js error-first convention:
      // (err, requestId, rejectedToken). rejectedToken is set on the retry
      // after a 401, and the cache drops it if it still holds it. err is null
      // on every current call (the Rust bridge always calls with Ok, passing
      // the request id and the rejected token or null), but the same rule as
      // `wrapProgress` applies: an error means there is no payload, so there
      // is no request id to answer. A request id
      // that is not a non-negative safe integer is equally unusable - it can
      // never name a real waiter, and `NaN`/fractional/oversized values would
      // be handed straight back to the native side. Bail out in that case; a
      // broken bridge is warned about once per client, not once per event.
      let reportedUnusableAuthRequest = false;
      const notifyFn: AuthNotifyFn = (err, requestId, rejectedToken) => {
        if (err || !Number.isSafeInteger(requestId) || requestId < 0) {
          if (!reportedUnusableAuthRequest) {
            reportedUnusableAuthRequest = true;
            console.warn(
              `[moss] Ignoring an auth request with no usable request id; custom ` +
                `authentication may be unavailable for this client. Cause: ${
                  err ? err.message : `received ${String(requestId)}`
                }`,
            );
          }
          return;
        }
        if (typeof rejectedToken === "string") authenticator.invalidate(rejectedToken);
        authenticator.getAuthHeader().then(
          (header) => {
            // header is "Bearer <token>" — strip the prefix for the Rust side
            const token = header.startsWith("Bearer ") ? header.slice(7) : header;
            settleResolve(requestId, token);
          },
          (error: unknown) => settleReject(requestId, describeCause(error)),
        );
      };
      // Retain the bridge so sessions can authenticate through the same flow.
      this.authNotifyFn = notifyFn;

      // Access withAuthenticator factory methods — these are added in the NAPI bindings
      // alongside the standard constructors
      const ManageClientWithAuth = ManageClientCtor as unknown as {
        withAuthenticator(projectId: string, notifyFn: AuthNotifyFn): InternalMossClient["manageClient"];
      };
      const IndexManagerWithAuth = IndexManagerCtor as unknown as {
        withAuthenticator(projectId: string, notifyFn: AuthNotifyFn): InternalMossClient["indexManager"];
      };

      if (!ManageClientWithAuth.withAuthenticator || !IndexManagerWithAuth.withAuthenticator) {
        throw new Error(
          "moss-core runtime ManageClient/IndexManager is missing withAuthenticator factory. " +
          "Ensure you are using a moss-core build that supports custom authenticators.",
        );
      }

      this.manageClient = ManageClientWithAuth.withAuthenticator(projectId, notifyFn);
      this.indexManager = IndexManagerWithAuth.withAuthenticator(projectId, notifyFn);
    }

    this.applyIdentity(this.indexManager as unknown as IdentityTarget);
  }

  /** Release native resources held by this client's IndexManager. */
  async close(): Promise<void> {
    const close = (this.indexManager as unknown as { close?: () => Promise<void> }).close;
    if (typeof close !== "function") {
      throw new Error(
        "@moss-js/moss-core >= 0.20.0 is required for MossClient.close()",
      );
    }
    await close.call(this.indexManager);
  }

  async getAuthToken(): Promise<AuthToken> {
    return this.authenticator.getAuthToken();
  }

  /**
   * Wrap an onProgress callback to adapt NAPI-RS ThreadsafeFunction's
   * Node.js (err, value) callback convention into a single-arg (value) callback.
   *
   * The public callback has no error channel — the awaited operation promise
   * is the authoritative success/failure signal, and progress is advisory. So
   * the policy on a native progress error is: never fabricate an event. When
   * the threadsafe function reports an error, hands us no payload (the
   * `(err, value)` convention leaves `value` undefined on the error path), or
   * hands us a value that is not a `JobProgress`, the caller's callback is not
   * invoked at all rather than being called with something it would have to
   * guard field-by-field. The first such event per operation is warned about
   * once, so a broken progress stream is visible without flooding the log for
   * every subsequent tick.
   */
  private wrapProgress(
    onProgress?: (progress: JobProgress) => void,
  ): NativeProgressCallback | undefined {
    if (!onProgress) return undefined;
    let reported = false;
    return (error, progress) => {
      const defect = error
        ? error.message
        : describeMalformedProgress(progress);
      if (defect !== null) {
        if (!reported) {
          reported = true;
          console.warn(
            `[moss] Dropping a malformed job progress event; progress reporting ` +
              `may be incomplete for this operation. Cause: ${defect}`,
          );
        }
        return;
      }
      onProgress(progress);
    };
  }

  /**
   * Normalize runtime status values from Rust/core to SDK canonical lowercase format.
   */
  private normalizeJobStatus(status: string): JobStatus {
    const normalized = status.trim().toLowerCase().replace(/\s+/g, "_");
    const compact = normalized.replace(/_/g, "");

    if (normalized === "pending_upload" || compact === "pendingupload") {
      return JobStatus.PendingUpload;
    }
    if (normalized === "uploading") {
      return JobStatus.Uploading;
    }
    if (normalized === "building") {
      return JobStatus.Building;
    }
    if (normalized === "completed") {
      return JobStatus.Completed;
    }
    if (normalized === "failed") {
      return JobStatus.Failed;
    }

    throw new Error(`Unsupported job status '${status}' returned by moss-core`);
  }

  async createIndex(
    indexName: string,
    docs: DocumentInfo[],
    modelId: string,
    options?: CreateIndexOptions,
  ): Promise<MutationResult> {
    if (!docs.length) {
      throw new Error("createIndex requires at least one document");
    }
    const result = await this.manageClient.createIndex(
      indexName,
      docs,
      modelId,
      this.wrapProgress(options?.onProgress),
    );
    return result as MutationResult;
  }

  /**
   * Convert browser-compatible data types (Blob, File, ArrayBuffer, Uint8Array)
   * to the byte representation the native binding accepts.
   */
  private async toByteArray(
    data: Uint8Array | ArrayBuffer | Blob | File,
  ): Promise<number[]> {
    // The native binding's ParseFileInput.data is Vec<u8>, which NAPI-RS
    // deserializes from a plain JS number array; a Buffer or Uint8Array
    // fails marshalling with "Failed to get Array length".
    if (data instanceof Uint8Array) {
      return Array.from(data);
    }
    if (data instanceof ArrayBuffer) {
      return Array.from(new Uint8Array(data));
    }
    // Blob / File (browser or Node.js 18+)
    if (typeof (data as Blob).arrayBuffer === "function") {
      const ab = await (data as Blob).arrayBuffer();
      return Array.from(new Uint8Array(ab));
    }
    throw new Error("Unsupported data type for file upload");
  }

  async createIndexFromFiles(
    indexName: string,
    files: ParseFileInput[],
    options?: CreateIndexFromFilesOptions,
  ): Promise<MutationResult> {
    if (files.length === 0) {
      throw new Error("createIndexFromFiles requires at least one file");
    }
    const modelId = options?.modelId ?? "moss-minilm";

    // Resolve data bytes for each file before passing to NAPI.
    // path and data must be undefined (not null) when absent — NAPI-RS treats
    // null as an invalid TypedArray and throws InvalidArg.
    const napiFiles = await Promise.all(
      files.map(async (f) => ({
        name: f.name,
        contentType: f.contentType,
        path: f.path ?? undefined,
        data: f.data != null ? await this.toByteArray(f.data) : undefined,
      })),
    );

    const result = await this.manageClient.createIndexFromFiles(
      indexName,
      napiFiles,
      modelId,
      this.wrapProgress(options?.onProgress),
      options?.parseOptions ?? null,
    );
    return result as MutationResult;
  }

  async addDocs(
    indexName: string,
    docs: DocumentInfo[],
    options?: MutationOptions,
  ): Promise<MutationResult> {
    if (Array.isArray(docs) && docs.length === 0) {
      throw new Error("addDocs requires at least one document");
    }
    const result = await this.manageClient.addDocs(
      indexName,
      docs,
      options ?? null,
      this.wrapProgress(options?.onProgress),
    );
    return result as MutationResult;
  }

  async deleteDocs(
    indexName: string,
    docIds: string[],
    options?: MutationOptions,
  ): Promise<MutationResult> {
    if (Array.isArray(docIds) && docIds.length === 0) {
      throw new Error("deleteDocs requires at least one document ID");
    }
    const result = await this.manageClient.deleteDocs(
      indexName,
      docIds,
      this.wrapProgress(options?.onProgress),
    );
    return result as MutationResult;
  }

  async getJobStatus(jobId: string): Promise<JobStatusResponse> {
    const response = (await this.manageClient.getJobStatus(jobId)) as JobStatusResponse;
    return {
      ...response,
      status: this.normalizeJobStatus(response.status),
      currentPhase: response.currentPhase ?? null,
      error: response.error ?? null,
    } as unknown as JobStatusResponse;
  }

  async getIndex(indexName: string): Promise<IndexInfo> {
    return this.manageClient.getIndex(indexName);
  }

  async listIndexes(): Promise<IndexInfo[]> {
    return this.manageClient.listIndexes();
  }

  async deleteIndex(indexName: string): Promise<boolean> {
    return this.manageClient.deleteIndex(indexName);
  }

  async getDocs(
    indexName: string,
    options?: GetDocumentsOptions,
  ): Promise<DocumentInfo[]> {
    return this.manageClient.getDocs(indexName, options ?? null);
  }

  async loadIndex(
    indexName: string,
    options?: LoadIndexOptions,
  ): Promise<string> {
    this.ensureCachePathDeviceId(options?.cachePath);
    // The transactional core warms the query model during loadIndex, so there
    // is no separate warm call here. A second loadQueryModel would re-raise the
    // stale-warm failure that a stale-but-successful load deliberately tolerates.
    const info = await this.indexManager.loadIndex(indexName, options ?? null);
    return info.name;
  }

  /**
   * Best-effort bulk load. Individual failures are reported in `failed`
   * and never roll back indexes that did load. The core warms each distinct
   * embedding model once for the whole batch.
   */
  async loadIndexes(
    indexNames: string[],
    options?: LoadIndexOptions,
  ): Promise<LoadIndexesResult> {
    const core = this.requireMultiIndexCore();
    this.ensureCachePathDeviceId(options?.cachePath);
    return core.loadIndexes(indexNames, options ?? null);
  }

  async unloadIndex(indexName: string): Promise<void> {
    return this.indexManager.unloadIndex(indexName);
  }

  /** Best-effort bulk unload; names that are not loaded are ignored. */
  async unloadIndexes(indexNames: string[]): Promise<void> {
    const core = this.requireMultiIndexCore();
    return core.unloadIndexes(indexNames);
  }

  /**
   * Narrow the native manager to one that implements the multi-index API,
   * failing closed with an upgrade hint on an older core.
   */
  private requireMultiIndexCore(): Required<
    Pick<
      InternalMossClient["indexManager"],
      "queryMultiIndex" | "queryMultiIndexText" | "loadIndexes" | "unloadIndexes"
    >
  > {
    const manager = this.indexManager;
    if (
      typeof manager.queryMultiIndex !== "function" ||
      typeof manager.queryMultiIndexText !== "function" ||
      typeof manager.loadIndexes !== "function" ||
      typeof manager.unloadIndexes !== "function"
    ) {
      throw new Error(
        "The installed @moss-js/moss-core does not support multi-index operations " +
          "(queryMultiIndex, loadIndexes, unloadIndexes). Upgrade @moss-js/moss-core.",
      );
    }
    return {
      queryMultiIndex: manager.queryMultiIndex.bind(manager),
      queryMultiIndexText: manager.queryMultiIndexText.bind(manager),
      loadIndexes: manager.loadIndexes.bind(manager),
      unloadIndexes: manager.unloadIndexes.bind(manager),
    };
  }

  private ensureCachePathDeviceId(cachePath?: string): void {
    if (cachePath && this.cachePathDeviceId === undefined) {
      resolveCachePathDeviceId(cachePath);
    }
  }

  readonly applyIdentity = (target: IdentityTarget): void => {
    if (
      !identitySupplied(this.configuredIdentity) &&
      this.cachePathDeviceId === undefined
    ) {
      return;
    }
    target.setIdentity(
      this.configuredIdentity?.deviceId ?? null,
      this.configuredIdentity?.userId ?? null,
      this.cachePathDeviceId ?? null,
    );
  };

  readonly applySessionIdentity = (target: IdentityTarget): void => {
    const identity = this.indexManager.deviceIdentity?.();
    if (!identity) {
      this.applyIdentity(target);
      return;
    }
    target.setIdentity(
      identity.deviceId ?? null,
      this.configuredIdentity?.userId ?? null,
      identity.mossDeviceId ?? null,
    );
  };

  /**
   * Whether this client was constructed with a custom `IAuthenticator`
   * (rather than a static project key). Sessions on this path authenticate
   * via the auth bridge.
   */
  hasCustomAuthenticator(): boolean {
    return this.authNotifyFn !== undefined;
  }

  /**
   * Build a core `SessionIndex` authenticated via the same JS-authenticator
   * bridge used for `IndexManager` — lets custom-auth clients (short-lived
   * JWTs, no project key) open sessions. The returned core handle is wrapped
   * by `SessionIndex._fromInner`.
   */
  async createAuthenticatedSessionInner(
    name: string,
    modelId: string,
    modelArtifact?: ModelArtifactIdentity,
  ): Promise<MossCore.SessionIndex> {
    if (!this.authNotifyFn) {
      throw new Error(
        "createAuthenticatedSessionInner requires a custom IAuthenticator client",
      );
    }
    // Resolve SessionIndex through the same CJS/ESM interop fallback the
    // constructor uses for ManageClient/IndexManager, so it isn't `undefined`
    // under some module-loading setups.
    type SessionWithAuth = {
      modelArtifactContractVersion?: () => number;
      withAuthenticator?: (
        name: string,
        modelId: string,
        projectId: string,
        notifyFn: AuthNotifyFn,
        baseUrl?: string | null,
        clientId?: string | null,
        artifactVersion?: string | null,
        manifestSha256?: string | null,
      ) => Promise<MossCore.SessionIndex>;
    };
    const runtime = MossCore as unknown as {
      SessionIndex?: SessionWithAuth;
      default?: { SessionIndex?: SessionWithAuth };
    };
    const SessionCtor = runtime.SessionIndex ?? runtime.default?.SessionIndex;
    if (!SessionCtor || typeof SessionCtor.withAuthenticator !== "function") {
      throw new Error(
        "moss-core runtime SessionIndex is missing the withAuthenticator factory. " +
          "Upgrade @moss-js/moss-core to a build that supports custom authenticators for sessions.",
      );
    }
    if (modelArtifact) {
      assertModelArtifactContractSupported(SessionCtor);
    }
    return SessionCtor.withAuthenticator(
      name,
      modelId,
      this.projectId,
      this.authNotifyFn,
      null,
      null,
      modelArtifact?.version ?? null,
      modelArtifact?.manifestSha256 ?? null,
    );
  }

  async query(
    indexName: string,
    query: string,
    options?: SdkQueryOptions,
  ): Promise<SearchResult> {
    if (!(await this.indexManager.hasIndex(indexName))) {
      throw mossError(
        "NOT_FOUND",
        `Index "${indexName}" is not loaded. Call loadIndex("${indexName}") or loadIndexes([...]) ` +
          "before querying; queries run locally and there is no cloud query fallback.",
      );
    }

    // An unloadIndex racing the check above makes the local query fail with
    // the core's typed "Index not loaded" error, which is surfaced as-is.
    const topK = options?.topK ?? 5;
    const alpha = options?.alpha ?? 0.8;

    if (options?.embedding) {
      return this.indexManager.query(indexName, query, options.embedding, topK, alpha, options?.filter, queryTuning(options));
    }

    return this.indexManager.queryText(indexName, query, topK, alpha, options?.filter, queryTuning(options));
  }

  /**
   * Search several loaded indexes in one call and return the global top-k,
   * each result tagged with its source `indexName`. Local-only: every name
   * must already be loaded, and all must share one embedding model.
   */
  async queryMultiIndex(
    indexNames: string[],
    query: string,
    options?: SdkQueryOptions,
  ): Promise<SearchResult> {
    if (indexNames.length === 0) {
      throw mossError("INVALID_ARGUMENT", "queryMultiIndex requires at least one index name");
    }
    const core = this.requireMultiIndexCore();
    const topK = options?.topK ?? 10;
    const alpha = options?.alpha ?? 0.8;

    if (options?.embedding) {
      return core.queryMultiIndex(indexNames, query, options.embedding, topK, alpha, options?.filter, queryTuning(options));
    }

    // An index that cannot embed text rejects with code INVALID_ARGUMENT and
    // a message that says to pass an embedding or use alpha 0.
    return core.queryMultiIndexText(indexNames, query, topK, alpha, options?.filter, queryTuning(options));
  }
}
