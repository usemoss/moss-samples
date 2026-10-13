/**
 * Shared types for the Moss React Native / Expo module.
 * Mirrors the public surface of `@moss-dev/moss` closely enough that
 * examples transfer across runtimes.
 */

export type MossModel = 'moss-minilm' | 'moss-mediumlm' | 'moss-litelm' | 'custom' | (string & {});

export interface DocumentInfo {
  id: string;
  text: string;
  metadata?: Record<string, string>;
  embedding?: number[];
  /** Opaque structured payload (e.g. JSON string). Not embedded or searched. */
  payload?: string;
}

export interface QueryResultDocumentInfo {
  id: string;
  text: string;
  score: number;
  metadata?: Record<string, string>;
  payload?: string;
}

export interface SearchResult {
  docs: QueryResultDocumentInfo[];
  query: string;
  /** Wall-clock query time in milliseconds. */
  timeMs: number;
}

export interface QueryOptions {
  topK?: number;
  /** Hybrid weight: 1.0 = dense only, 0.0 = sparse only. Default 0.8. */
  alpha?: number;
  /**
   * Metadata filter, same shape as `@moss-dev/moss`:
   * - Field: `{ field: 'city', condition: { $eq: 'NYC' } }`
   * - And: `{ $and: [filter, filter, ...] }`
   * - Or: `{ $or: [filter, filter, ...] }`
   *
   * Operators: `$eq`, `$ne`, `$gt`, `$gte`, `$lt`, `$lte`, `$in`, `$nin`, `$near`.
   */
  filter?: Record<string, unknown>;
  /**
   * Pre-serialized metadata filter, for callers that already hold the engine's
   * JSON form. Mutually exclusive with `filter`.
   */
  filterJson?: string;
  /**
   * Precomputed query vector. Required for indexes built from custom document
   * embeddings (`modelId: 'custom'`), which have no on-device model to embed
   * the query text with. Must match the index's dimensionality.
   */
  embedding?: number[];
}

export interface ModelRef {
  id: string;
  version?: string | null;
}

export interface IndexInfo {
  id: string;
  name: string;
  status: string;
  docCount: number;
  model: ModelRef;
  version?: string | null;
  createdAt?: string | null;
  updatedAt?: string | null;
}

export interface MutationResult {
  jobId: string;
  indexName: string;
  docCount: number;
}

export interface CreateIndexOptions {
  modelId?: MossModel;
}

export interface LoadIndexOptions {
  autoRefresh?: boolean;
  /** Poll interval in seconds when `autoRefresh` is true. Default 600. */
  pollingIntervalSeconds?: number;
  /** Sandbox path used to cache the index on disk across launches. */
  cachePath?: string;
}

export interface MutationOptions {
  upsert?: boolean;
}

/**
 * Supplies a short-lived bearer token.
 *
 * Return the raw token only — the native side builds the
 * `Authorization: Bearer <token>` header itself, so do not include the
 * `Bearer ` prefix. Called whenever the runtime needs a token, so cache until
 * expiry on your side if the round trip is expensive.
 */
export type AuthTokenProvider = () => Promise<string> | string;

/** Options for constructing a client that authenticates with short-lived tokens. */
export interface MossClientAuthOptions {
  projectId: string;
  getAuthToken: AuthTokenProvider;
  /** Override the cloud endpoint. Defaults to the standard Moss endpoint. */
  baseUrl?: string;
}

export class MossError extends Error {
  readonly code: number;

  constructor(code: number, message: string) {
    super(message);
    this.name = 'MossError';
    this.code = code;
  }
}
