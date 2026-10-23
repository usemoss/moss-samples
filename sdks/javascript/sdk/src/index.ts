/// <reference lib="esnext.disposable" preserve="true" />
/**
 * Moss Semantic Search SDK
 *
 * Powerful TypeScript SDK for local semantic search using state-of-the-art embedding models.
 *
 * @example
 * ```typescript
 * import { MossClient } from '@moss-js/moss';
 *
 * const client = new MossClient('your-project-id', 'your-project-key');
 *
 * // Create an index with documents
 * await client.createIndex('knowledge-base', [
 *   { id: '1', text: 'Machine learning algorithms for data analysis' },
 *   { id: '2', text: 'Natural language processing techniques' }
 * ]);
 *
 * // Query the index
 * await client.loadIndex('knowledge-base');
 * const results = await client.query('knowledge-base', 'AI and data science');
 * ```
 */

export { MossClient } from "./client/mossClient";
export { SessionIndex } from "./client/sessionIndex";
export { ManageApiError } from "./utils/manageHttp";
export { isMossError } from "./errors";
export type { MossError, MossErrorCode } from "./errors";
export type { IAuthenticator, AuthToken } from "./auth/authenticator.interface";

// Chat completions through the Moss inference gateway, in OpenAI's shape
export { MossInference, inference } from "./inference";
export type { ChatCompletions } from "./inference";
export { ChatCompletionStream } from "./inference/stream";
export { InferenceError } from "./inference/error";
export type { InferenceErrorType } from "./inference/error";
export type {
  ChatCompletion,
  ChatCompletionChoice,
  ChatCompletionChunk,
  ChatCompletionChunkChoice,
  ChatCompletionChunkDelta,
  ChatCompletionChunkToolCall,
  ChatCompletionContentPart,
  ChatCompletionCreateParams,
  ChatCompletionCreateParamsBase,
  ChatCompletionCreateParamsNonStreaming,
  ChatCompletionCreateParamsStreaming,
  ChatCompletionLogprobs,
  ChatCompletionMessage,
  ChatCompletionMessageParam,
  ChatCompletionMessageToolCall,
  ChatCompletionTokenLogprob,
  ChatCompletionTool,
  CompletionUsage,
  InferenceRequestOptions,
  McpServer,
  MossInferenceOptions,
  ToolStep,
} from "./inference/types";

// SDK-specific types
export type {
  ISODate,
  ModelArtifactIdentity,
  MossIdentity,
  MossModel,
  CreateIndexOptions,
  ParseFileInput,
  ParseOptions,
  CreateIndexFromFilesOptions,
  WebSource,
  WebSourceStatus,
  WebSourceRefreshCadence,
  CreateWebSourceResult,
  CreateWebSourceOptions,
  UpdateWebSourceResult,
  UpdateWebSourceOptions,
  ResyncWebSourceResult,
  DeleteWebSourceResult,
} from "./models";

// Status values ship as plain objects, so a file transpiled on its own can read their members
export { IndexStatus, JobStatus, JobPhase } from "./models";

// Re-export moss-core types directly
export type {
  IndexInfo,
  ModelRef,
  DocumentInfo,
  QueryResultDocumentInfo,
  SearchResult,
  QueryOptions,
  GetDocumentsOptions,
  MutationResult,
  RefreshResult,
  JobStatusResponse,
  PushIndexResult,
  LoadSessionOptions,
  LoadFromDiskOptions,
  SnapshotInfo,
} from "@moss-js/moss-core";

// SDK-specific types (extended or unique to SDK)
export type {
  LoadIndexOptions,
  LoadIndexesResult,
  MossClientOptions,
  MutationOptions,
  JobProgress,
} from "./models";
