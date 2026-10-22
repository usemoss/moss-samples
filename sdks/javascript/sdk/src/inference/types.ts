// An `any` index signature, unlike `unknown`, also accepts values whose types are interfaces.
/* eslint-disable @typescript-eslint/no-explicit-any */

/** One part of a message's content, such as text or an image. */
export interface ChatCompletionContentPart {
  type: string;
  text?: string;
  [key: string]: any;
}

/** A tool call the model made, as the API returns it. */
export interface ChatCompletionMessageToolCall {
  id: string;
  type: "function";
  function: { name: string; arguments: string };
}

/** One message of the conversation, in OpenAI's shape. */
export interface ChatCompletionMessageParam {
  role: "system" | "developer" | "user" | "assistant" | "tool" | "function";
  content?: string | ChatCompletionContentPart[] | null;
  name?: string;
  tool_calls?: (ChatCompletionMessageToolCall | { type: string; [key: string]: any })[];
  tool_call_id?: string;
  [key: string]: any;
}

/** A function the model may call. */
export interface ChatCompletionTool {
  type: "function";
  function: {
    name: string;
    description?: string;
    parameters?: Record<string, unknown>;
    strict?: boolean | null;
  };
}

/**
 * OpenAI's chat completion parameters plus the Moss retrieval options.
 * `indexes` and `retrieve` travel as headers, the rest in the body unchanged,
 * including parameters this type does not name. The body always says `stream: true`.
 */
export interface ChatCompletionCreateParamsBase {
  /** `moss` by default, Moss's own model. A vendor model such as `gpt-4o-mini` needs `apiKey`. */
  model?: string;
  messages: ChatCompletionMessageParam[];
  stream?: boolean | null;
  /** Moss indexes the gateway searches. Names travel in a header, so they must be Latin-1. */
  indexes?: string[];
  /** False skips retrieval for this call. */
  retrieve?: boolean;
  temperature?: number | null;
  top_p?: number | null;
  max_tokens?: number | null;
  max_completion_tokens?: number | null;
  stop?: string | string[] | null;
  seed?: number | null;
  tools?: (ChatCompletionTool | { type: string; [key: string]: any })[];
  tool_choice?: "none" | "auto" | "required" | { type: string; [key: string]: any };
  response_format?: { type: string; [key: string]: any };
  stream_options?: { include_usage?: boolean } | null;
  user?: string;
  /** Any other OpenAI parameter. */
  [param: string]: any;
}

/** Parameters that return a {@link ChatCompletionStream}. */
export interface ChatCompletionCreateParamsStreaming extends ChatCompletionCreateParamsBase {
  stream: true;
}

/** Parameters that return one aggregated {@link ChatCompletion}. */
export interface ChatCompletionCreateParamsNonStreaming extends ChatCompletionCreateParamsBase {
  stream?: false | null;
}

/** Parameters of `chat.completions.create`. */
export type ChatCompletionCreateParams =
  ChatCompletionCreateParamsStreaming | ChatCompletionCreateParamsNonStreaming;

/**
 * Settings of a `MossInference` client.
 * Timeouts are in milliseconds, and `null` or `Infinity` removes the limit.
 */
export interface MossInferenceOptions {
  /**
   * Your own OpenAI, Anthropic or Google key, for a vendor model such as `gpt-4o-mini`.
   * `moss` ignores it, and a vendor model without one is refused. A call's `apiKey` wins.
   */
  apiKey?: string;
  /** The limit for each whole call, streaming included. None by default. */
  timeout?: number | null;
  /**
   * The longest wait for response headers or for more of the body. 120 000 by default.
   * Node's fetch also ends a silence of 300 000, unless its global dispatcher allows more.
   */
  idleTimeout?: number | null;
  /** Headers sent on every call. Host, Content-Length and Transfer-Encoding are an error. */
  headers?: Record<string, string>;
}

/** Per-call settings that never reach the request body. */
export interface InferenceRequestOptions {
  /** Replaces the client's `apiKey` for this call. An empty string is an error. */
  apiKey?: string;
  /** Aborts the call. */
  signal?: AbortSignal;
  /** Replaces the client's `timeout` for this call. */
  timeout?: number | null;
  /** Replaces the client's `idleTimeout` for this call. */
  idleTimeout?: number | null;
  /**
   * Headers for this call, over the client's.
   * The SDK's own headers win over both, and Host,
   * Content-Length and Transfer-Encoding are an error.
   */
  headers?: Record<string, string>;
}

/** Token counts for one call. */
export interface CompletionUsage {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
}

/** A piece of a tool call inside a streamed delta. */
export interface ChatCompletionChunkToolCall {
  index: number;
  id?: string;
  type?: "function";
  function?: { name?: string; arguments?: string };
}

/** What one chunk adds to a choice. */
export interface ChatCompletionChunkDelta {
  role?: string;
  content?: string | null;
  tool_calls?: ChatCompletionChunkToolCall[];
}

/** One choice inside a streamed chunk. */
export interface ChatCompletionChunkChoice {
  index: number;
  delta: ChatCompletionChunkDelta;
  finish_reason: string | null;
}

/**
 * One streamed event, in OpenAI's shape.
 * Each chunk is the decoded JSON event,
 * so fields this type does not name are still on the object.
 * The last chunk may carry `usage` with an empty `choices` list.
 */
export interface ChatCompletionChunk {
  id: string;
  object: "chat.completion.chunk";
  created: number;
  model: string;
  choices: ChatCompletionChunkChoice[];
  usage?: CompletionUsage | null;
}

/** The reply the model built for one choice. */
export interface ChatCompletionMessage {
  role: "assistant";
  /** All text joined, or null when the model sent none. */
  content: string | null;
  /** Present only when the model called tools. */
  tool_calls?: ChatCompletionMessageToolCall[];
}

/** One choice of an aggregated completion. */
export interface ChatCompletionChoice {
  index: number;
  message: ChatCompletionMessage;
  finish_reason: string | null;
}

/** A whole reply, built from every chunk of the stream. */
export interface ChatCompletion {
  id: string;
  object: "chat.completion";
  created: number;
  model: string;
  choices: ChatCompletionChoice[];
  usage: CompletionUsage | null;
}
