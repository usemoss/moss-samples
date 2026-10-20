import type {
  IndexStatus as CoreIndexStatus,
  JobPhase as CoreJobPhase,
  JobStatus as CoreJobStatus,
} from "@moss-js/moss-core";
import type { MossErrorCode } from "./errors";


/**
 * ISO 8601 date string format.
 * @example "2025-09-26T15:04:05Z"
 */
export type ISODate = string;

/**
 * Available embedding models for text-to-vector conversion.
 *
 * Each model offers different trade-offs between speed, accuracy, and resource usage:
 *
 * - **`"moss-minilm"`**: Lightweight model optimized for speed and efficiency.
 *   Best for applications requiring fast response times with moderate accuracy requirements.
 *
 * - **`"moss-mediumlm"`**: Balanced model offering higher accuracy with reasonable performance.
 *   Best for applications where search quality is important and moderate latency is acceptable.
 *
 * - **`"moss-litelm"`**: Smallest built-in model, available to entitled organizations.
 *
 * - **`"custom"`**: Use this when providing pre-computed embeddings from external sources.
 *   No embedding model is loaded. All documents must include embeddings, and all queries
 *   must provide embeddings via QueryOptions.embedding.
 */
export type MossModel = "moss-minilm" | "moss-mediumlm" | "moss-litelm" | "custom";

/** Exact immutable publisher identity required for local foundation models. */
export interface ModelArtifactIdentity {
  /** Version embedded in the publisher manifest and immutable artifact URL. */
  version: string;
  /** Lowercase SHA-256 digest of the exact publisher manifest bytes. */
  manifestSha256: string;
}

/**
 * Document that can be indexed and retrieved.
 */
export interface DocumentInfo {
  /**
   * Unique identifier within an index.
   */
  id: string;

  /**
   * REQUIRED canonical text to embed/search.
   */
  text: string;

  /**
   * Optional metadata associated with the document.
   */
  metadata?: Record<string, string>;

  /**
   * Optional caller-provided embedding vector.
   */
  embedding?: number[];
}


/**
 * Document result from a query, with its relevance score.
 */
export interface QueryResultDocumentInfo extends DocumentInfo {
  /**
   * Relevance to the query from 0 to 1. It comes from vector similarity
   * alone, so `alpha` and rank never change it. Results are ordered by hybrid
   * relevance, so a lower result can show a higher score. A keyword-only query
   * (`alpha` 0, or an index without vectors) scores every hit 0. Scores
   * depend on the embedding model: tune `minScore` on your own queries.
   */
  score: number;

  /**
   * Source index name. Set on results from `queryMultiIndex`; absent for
   * single-index queries.
   */
  indexName?: string;
}

/**
 * Search operation result.
 */
export interface SearchResult {
  /**
   * Matching documents in hybrid relevance order.
   */
  docs: QueryResultDocumentInfo[];

  /**
   * The original search query.
   */
  query: string;

  /**
   * Name of the index that was searched.
   */
  indexName?: string;

  /**
   * Time taken to execute the search in milliseconds.
   */
  timeTakenInMs?: number;
}

/**
 * Optional parameters for semantic queries.
 */
export interface QueryOptions {
  /**
   * Caller-provided embedding vector. When supplied, the service/client skips
   * embedding generation. This is required for a loaded foundation index that
   * has no exact model artifact identity. It is checked at every `alpha`:
   * each component must be finite, and its length must match the index.
   */
  embedding?: number[];

  /**
   * Number of top results to return. Overrides method-level defaults.
   * 0 returns no results.
   */
  topK?: number;

  /**
   * Weight for hybrid search fusion (0.0 to 1.0).
   * @default 0.8
   */
  alpha?: number;

  /**
   * Optional metadata filter to narrow query results.
   *
   * Supports field conditions and logical operators:
   * - Field: `{ field: "city", condition: { $eq: "NYC" } }`
   * - And: `{ $and: [filter, filter, ...] }`
   * - Or: `{ $or: [filter, filter, ...] }`
   *
   * Condition operators: `$eq`, `$ne`, `$gt`, `$gte`, `$lt`, `$lte`, `$in`, `$nin`, `$near`
   *
   * `$gt`, `$gte`, `$lt` and `$lte` compare two plain decimals (`"42"`, `"-3.5"`) as
   * numbers and two other values as text. They never match a plain decimal against any other
   * value, such as `"007"`, `"1e3"` or `"NaN"`.
   * `$near` takes `"lat,lng,maxDistanceMeters"` and matches a `"lat,lng"` field value;
   * any other `$near` value is an error. A condition never matches a document that lacks
   * the field, `$ne` and `$nin` included.
   */
  filter?: Record<string, unknown>;

  /**
   * Minimum `score` a hit must reach, from 0 to 1. Drops hits below the
   * floor; a query returns up to `topK` hits that clear it, in hybrid order.
   * Rejected on a keyword-only query (`alpha` 0).
   */
  minScore?: number;

  /**
   * How many hits a hybrid query (`alpha` between 0 and 1) ranks on each
   * signal before fusion. A hit outside both lists is never returned, so a
   * deeper list raises recall and query time. Defaults to `2 * topK`. A set
   * value must be at least 1 and is raised to `topK` when below it.
   * Keyword-only and vector-only queries (`alpha` 0 or 1) ignore it.
   * Used by `MossClient.query` and `queryMultiIndex`. Session queries ignore it.
   */
  candidateDepth?: number;
}


/**
 * Options for retrieving documents from an index.
 */
export interface GetDocumentsOptions {
  /**
   * Optional array of document IDs to retrieve.
   * If omitted, returns all documents.
   */
  docIds?: string[];
}

/**
 * Options for adding documents to a local in-memory index.
 */
export interface AddDocumentsOptions {
  /**
   * Whether to update existing documents with the same ID.
   * @default true
   */
  upsert?: boolean;
}


/** Lifecycle status of an index build. */
export const IndexStatus = {
  NotStarted: "NotStarted",
  Building: "Building",
  Ready: "Ready",
  Failed: "Failed",
} as const satisfies Record<string, CoreIndexStatus>;

/** Lifecycle status of an index build. */
export type IndexStatus = (typeof IndexStatus)[keyof typeof IndexStatus];

/** The type of each `IndexStatus` member, so `IndexStatus.NotStarted` also works as a type, as an enum member does. */
export declare namespace IndexStatus {
  export type NotStarted = typeof IndexStatus.NotStarted;
  export type Building = typeof IndexStatus.Building;
  export type Ready = typeof IndexStatus.Ready;
  export type Failed = typeof IndexStatus.Failed;
}

/** Status of an async cloud job. */
export const JobStatus = {
  PendingUpload: "pending_upload",
  Uploading: "uploading",
  Building: "building",
  Completed: "completed",
  Failed: "failed",
} as const satisfies Record<string, CoreJobStatus>;

/** Status of an async cloud job. */
export type JobStatus = (typeof JobStatus)[keyof typeof JobStatus];

/** The type of each `JobStatus` member, so `JobStatus.PendingUpload` also works as a type, as an enum member does. */
export declare namespace JobStatus {
  export type PendingUpload = typeof JobStatus.PendingUpload;
  export type Uploading = typeof JobStatus.Uploading;
  export type Building = typeof JobStatus.Building;
  export type Completed = typeof JobStatus.Completed;
  export type Failed = typeof JobStatus.Failed;
}

/** Phase of an async cloud job. */
export const JobPhase = {
  Downloading: "downloading",
  Deserializing: "deserializing",
  GeneratingEmbeddings: "generating_embeddings",
  BuildingIndex: "building_index",
  Uploading: "uploading",
  Cleanup: "cleanup",
  WaitingForParser: "waiting_for_parser",
  Parsing: "parsing",
  ParsingComplete: "parsing_complete",
  Queued: "queued",
  Crawling: "crawling",
  ParsingDocuments: "parsing_documents",
} as const satisfies Record<string, CoreJobPhase>;

/** Phase of an async cloud job. */
export type JobPhase = (typeof JobPhase)[keyof typeof JobPhase];

/** The type of each `JobPhase` member, so `JobPhase.Downloading` also works as a type, as an enum member does. */
export declare namespace JobPhase {
  export type Downloading = typeof JobPhase.Downloading;
  export type Deserializing = typeof JobPhase.Deserializing;
  export type GeneratingEmbeddings = typeof JobPhase.GeneratingEmbeddings;
  export type BuildingIndex = typeof JobPhase.BuildingIndex;
  export type Uploading = typeof JobPhase.Uploading;
  export type Cleanup = typeof JobPhase.Cleanup;
  export type WaitingForParser = typeof JobPhase.WaitingForParser;
  export type Parsing = typeof JobPhase.Parsing;
  export type ParsingComplete = typeof JobPhase.ParsingComplete;
  export type Queued = typeof JobPhase.Queued;
  export type Crawling = typeof JobPhase.Crawling;
  export type ParsingDocuments = typeof JobPhase.ParsingDocuments;
}

/**
 * Progress update passed to the `onProgress` callback during async operations.
 */
export interface JobProgress {
  jobId: string;
  status: "pending_upload" | "uploading" | "building" | "completed" | "failed";
  progress: number;
  currentPhase: "queued" | "crawling" | "parsing_documents" | "parsing" | "waiting_for_parser" | "parsing_complete" | "downloading" | "deserializing" | "generating_embeddings" | "building_index" | "uploading" | "cleanup" | null;
}


/**
 * Input descriptor for a single file in the parse pipeline.
 *
 * Either `path` (server/Node.js) or `data` (browser) must be provided.
 * Supported `contentType` values are `"application/pdf"` and
 * `"application/vnd.openxmlformats-officedocument.wordprocessingml.document"` (DOCX).
 */
export interface ParseFileInput {
  /**
   * File identifier sent to the server. Required.
   */
  name: string;
  /**
   * MIME content type. Required. Supported values are `"application/pdf"` and
   * `"application/vnd.openxmlformats-officedocument.wordprocessingml.document"` (DOCX).
   */
  contentType: string;
  /**
   * Filesystem path to the file (Node.js / server-side).
   * Required when `data` is not provided.
   */
  path?: string;
  /**
   * Raw file bytes (browser / in-memory).
   * Takes precedence over `path` when provided.
   * Accepts `Uint8Array`, `ArrayBuffer`, `Blob`, or a browser `File` object.
   */
  data?: Uint8Array | ArrayBuffer | Blob | File;
}

/**
 * Controls how the server extracts text from uploaded documents.
 *
 * Every field is optional; omitted fields use the server defaults.
 */
export interface ParseOptions {
  /**
   * Slower, higher fidelity extraction. Useful for dense tables.
   */
  useHighResolution?: boolean;
  /**
   * How the document is segmented before extraction.
   */
  segmentationMethod?: "smart_layout_detection" | "page_by_page";
  /**
   * `"full_ocr"` forces OCR on every page, which is what scanned documents
   * with no text layer need. `"auto_ocr"` runs it only where it looks
   * necessary.
   */
  ocrMode?: "auto_ocr" | "full_ocr";
  /**
   * Merge a table split across a page break into a single segment.
   */
  mergeTables?: boolean;
  /**
   * Target length of each chunk in characters, 200 to 2000. Defaults to 1200.
   */
  chunkSize?: number;
  /**
   * Characters shared by consecutive chunks, 0 to half of `chunkSize`.
   * Defaults to 200, capped at half of `chunkSize`.
   */
  chunkOverlap?: number;
}

/**
 * Options for creating an index from files via the parse pipeline.
 */
export interface CreateIndexFromFilesOptions {
  /**
   * Embedding model to use. Defaults to "moss-minilm".
   * "custom" is not supported — the parse pipeline generates embeddings server-side.
   */
  modelId?: "moss-minilm" | "moss-mediumlm";

  /**
   * Extraction controls, including OCR mode. Omit for server defaults.
   */
  parseOptions?: ParseOptions;

  /**
   * Callback invoked with progress updates (~every 2s) while the server is processing.
   */
  onProgress?: (progress: JobProgress) => void;
}

/**
 * Options for creating an index.
 */
export interface CreateIndexOptions {
  /**
   * Embedding model to use. Defaults to "moss-minilm", or "custom" if
   * documents have pre-computed embeddings.
   */
  modelId?: string;

  /**
   * Callback invoked with progress updates (~every 2s) while the server is processing.
   */
  onProgress?: (progress: JobProgress) => void;
}

/**
 * Options for async mutation operations (addDocs, deleteDocs).
 * Extends moss-core MutationOptions with SDK-specific onProgress callback.
 */
export interface MutationOptions {
  /**
   * Whether a document replaces a stored one with the same ID.
   * `SessionIndex.addDocs` applies it locally and treats an omitted value as `true`.
   * `MossClient.addDocs` sends it only when set, and the cloud service decides how to apply it.
   */
  upsert?: boolean;

  /**
   * Callback invoked with progress updates (~every 2s) while the server is processing.
   */
  onProgress?: (progress: JobProgress) => void;
}

// MutationResult is exported directly from index.ts

// JobStatusResponse is exported directly from index.ts

// Cloud API request types (internal)

/**
 * Options for loading an index with auto-refresh configuration.
 * Note: SDK makes fields optional with defaults, moss-core requires them.
 */
export interface LoadIndexOptions {
  /**
   * Whether to enable auto-refresh polling for this index.
   * When enabled, the index will periodically check for updates from the cloud.
   * @default false
   */
  autoRefresh?: boolean;

  /**
   * Polling interval in seconds. Only used when autoRefresh is true.
   * 0 uses the default, and the minimum is 1 second.
   * @default 600 (10 minutes)
   */
  pollingIntervalInSeconds?: number;

  /**
   * Filesystem path for caching index data to disk.
   * When set, downloaded indexes are persisted and reused on subsequent loads
   * if the cloud data hasn't changed. Auto-refresh also persists to cache.
   */
  cachePath?: string;
}

/**
 * Outcome of a best-effort bulk `loadIndexes` call.
 */
export interface LoadIndexesResult {
  /**
   * Names of indexes that were successfully loaded into memory.
   */
  loaded: string[];

  /**
   * Names that failed to load, mapping name to a fixed public message.
   */
  failed: Record<string, string>;

  /**
   * Names that failed to load, mapping name to the error code. Set by the
   * matching `@moss-js/moss-core`.
   */
  failedCodes?: Record<string, MossErrorCode>;
}

export interface MossClientOptions {
  /**
   * Directory whose `.moss-device-id` file is adopted as Moss's stable device
   * UUID for this client and its sessions. It is emitted as `mossDeviceId`,
   * and also as the billable `deviceId` when no host device id is configured.
   * The file is created on first use. When omitted, the native core uses
   * `~/.moss/.moss-device-id`. Sessions from this client save to
   * `<cachePath>/sessions/<project id>/` when `saveToDisk` gets no directory.
   */
  cachePath?: string;

  /**
   * Stable host identity attached to telemetry from this client and its
   * sessions. `deviceId` is the billable MAD key. `userId` is optional and
   * non-billable. Moss's own stable UUID is still sent as `mossDeviceId`.
   */
  identity?: MossIdentity;
}

/**
 * Caller-managed stable identity for a MossClient lifetime. Supplied values
 * must be 1-256 UTF-8 bytes with no leading or trailing whitespace, Unicode
 * control or format characters, lone surrogates, or replacement characters.
 */
export interface MossIdentity {
  /** Stable device or app-installation id used for MAD billing. */
  deviceId?: string;

  /** Optional non-billable user grouping id. */
  userId?: string;
}

export type WebSourceStatus = "idle" | "crawling" | "failed" | "removing";

export type WebSourceRefreshCadence = "daily" | "weekly" | "manual";

/**
 * A web source as the manage API returns it.
 */
export interface WebSource {
  id: string;
  indexName: string;
  rootUrl: string;
  maxPages: number;
  maxDocuments: number;
  maxDepth: number;
  includePaths?: string[];
  excludePaths?: string[];
  respectRobots: boolean;
  parseDocuments: boolean;
  refreshCadence: WebSourceRefreshCadence;
  nextRefreshAt: string | null;
  lastCrawledAt: string | null;
  lastPageCount: number | null;
  lastDocCount: number | null;
  status: WebSourceStatus;
  lastErrorCode: string | null;
  createdAt?: string;
}

export interface CreateWebSourceResult extends WebSource {
  /** Crawl job to poll with `getJobStatus`. */
  jobId: string;
}

export interface UpdateWebSourceResult extends WebSource {
  /**
   * Present when `resync` is true and the server enqueued a crawl.
   * Poll with `getJobStatus`.
   */
  jobId?: string;
}

export interface ResyncWebSourceResult {
  id: string;
  jobId: string;
  status?: string;
  indexName?: string;
}

export interface DeleteWebSourceResult {
  deleted: boolean;
  id: string;
  /**
   * Present when a purge was enqueued. Poll with `getJobStatus`.
   */
  purgeJobId?: string;
}

export interface CreateWebSourceOptions {
  maxPages?: number;
  maxDocuments?: number;
  maxDepth?: number;
  includePaths?: string[];
  excludePaths?: string[];
  respectRobots?: boolean;
  parseDocuments?: boolean;
  refreshCadence?: "daily" | "weekly";
  modelId?: "moss-minilm" | "moss-mediumlm";
}

export interface UpdateWebSourceOptions {
  refreshCadence?: WebSourceRefreshCadence;
  rootUrl?: string;
  includePaths?: string[];
  excludePaths?: string[];
  maxDepth?: number;
  maxPages?: number;
  resync?: boolean;
}

// RefreshResult is exported directly from index.ts
