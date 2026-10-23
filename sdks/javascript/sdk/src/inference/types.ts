// An `any` index signature, unlike `unknown`, also accepts values whose types are interfaces.
/* eslint-disable @typescript-eslint/no-explicit-any */

/** One part of a message's content, such as text or an image. */
export interface ChatCompletionContentPart {
  type: string;
  text?: string;
  [key: string]: any;
}

/**
 * A tool call the model made, as the API returns it.
 * Fields the model adds, such as Gemini's `extra_content`, stay on the object.
 */
export interface ChatCompletionMessageToolCall {
  id: string;
  type: "function";
  function: { name: string; arguments: string };
  [key: string]: any;
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

/** A function the model may call. Your code runs it and sends back the result. */
export interface ChatCompletionTool {
  type: "function";
  function: {
    name: string;
    description?: string;
    parameters?: Record<string, unknown>;
    strict?: boolean | null;
  };
}

/** An MCP server the gateway calls for the model during the turn. */
export interface McpServer {
  /** Marks this `tools` entry as an MCP server. */
  type: "mcp";
  /** The server's label, unique in the request. */
  server_label: string;
  /** The server's https URL. */
  server_url: string;
  /** Headers for this server only, such as its `Authorization`. */
  headers?: Record<string, string>;
  /** The only tools of the server the model may call. */
  allowed_tools?: string[];
  /** `streamable_http` by default, or `sse` for an older server. */
  transport?: "streamable_http" | "sse";
}

/**
 * One MCP tool call the gateway runs, streamed once before the call (`call`)
 * and once after it (`result`). Fields this type does not name stay on the object.
 */
export interface ToolStep {
  /** `call` before the tool runs, `result` after. */
  type: "call" | "result";
  /** The same on the `call` and the `result` of one tool call. */
  id: string;
  /** The label of the MCP server, as sent in `tools`. */
  server_label: string;
  /** The tool's name on its server. */
  name: string;
  /** The arguments as JSON text, on `call` only. */
  arguments?: string;
  /** True when the tool failed, on `result` only. */
  is_error?: boolean;
  /** How long the call took in milliseconds, on `result` only. */
  duration_ms?: number;
  /** The tool's result, cut when long, on `result` only. */
  output?: string;
  [key: string]: any;
}

/**
 * OpenAI's chat completion parameters plus the Moss options.
 * `indexes`, `retrieve` and `cache` travel as headers, the rest in the body
 * unchanged, including parameters this type does not name. The body always says `stream: true`.
 */
export interface ChatCompletionCreateParamsBase {
  /** `moss` by default, Moss's own model. A vendor model such as `gpt-4o-mini` needs `apiKey`. */
  model?: string;
  messages: ChatCompletionMessageParam[];
  stream?: boolean | null;
  /**
   * Moss indexes to search, every index when left out and none when empty.
   * Names travel in a single header, so each must be Latin-1 text with no comma.
   */
  indexes?: string[];
  /** False skips retrieval for this call. */
  retrieve?: boolean;
  /** False always asks the model instead of the gateway's reply cache. */
  cache?: boolean;
  temperature?: number | null;
  top_p?: number | null;
  max_tokens?: number | null;
  max_completion_tokens?: number | null;
  stop?: string | string[] | null;
  seed?: number | null;
  /** Functions your code runs, MCP servers the gateway calls, or any other tool object. */
  tools?: (ChatCompletionTool | McpServer | { type: string; [key: string]: any })[];
  /** Whether and which tool the model calls, such as `{ type: "function", function: { name } }`. */
  tool_choice?: "none" | "auto" | "required" | { type: string; [key: string]: any };
  /** False asks the model for at most one tool call per reply. */
  parallel_tool_calls?: boolean | null;
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
  /**
   * Retries before the stream starts, 2 by default and 0 for none.
   * A failed connection or a 408, 409, 429 or 5xx response is retried.
   */
  maxRetries?: number;
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
  /** Replaces the client's `maxRetries` for this call. */
  maxRetries?: number;
  /**
   * Headers for this call, over the client's.
   * The SDK's own headers win over both, and Host,
   * Content-Length and Transfer-Encoding are an error.
   */
  headers?: Record<string, string>;
}

/** Token counts for one call, with every field the gateway sent. */
export interface CompletionUsage {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  /** Such as `reasoning_tokens`. */
  completion_tokens_details?: Record<string, any>;
  /** Such as `cached_tokens`. */
  prompt_tokens_details?: Record<string, any>;
  [key: string]: any;
}

/** The log probability of one token, with the likeliest tokens in its place when asked for. */
export interface ChatCompletionTokenLogprob {
  token: string;
  logprob: number;
  bytes: number[] | null;
  top_logprobs: { token: string; logprob: number; bytes: number[] | null }[];
  [key: string]: any;
}

/** The log probabilities of a choice's tokens, for its text and for a refusal. */
export interface ChatCompletionLogprobs {
  content: ChatCompletionTokenLogprob[] | null;
  refusal: ChatCompletionTokenLogprob[] | null;
}

/** A piece of a tool call inside a streamed delta, with any fields beyond OpenAI's. */
export interface ChatCompletionChunkToolCall {
  index: number;
  id?: string;
  type?: "function";
  function?: { name?: string; arguments?: string };
  [key: string]: any;
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
  logprobs?: ChatCompletionLogprobs | null;
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
  /** An MCP tool call the gateway runs, on a chunk whose one choice has an empty delta. */
  moss_tool_step?: ToolStep;
}

/**
 * The reply the model built for one choice.
 * Push it onto `messages` unchanged, then one `tool` message per tool call.
 */
export interface ChatCompletionMessage {
  role: "assistant";
  /** All text joined. Without text, null when the model called tools and empty otherwise. */
  content: string | null;
  /** Present only when the model called tools. */
  tool_calls?: ChatCompletionMessageToolCall[];
}

/** One choice of an aggregated completion. */
export interface ChatCompletionChoice {
  index: number;
  message: ChatCompletionMessage;
  /** The tokens of every chunk joined in order, or null when no chunk had any. */
  logprobs: ChatCompletionLogprobs | null;
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
  /** Every MCP tool step of the stream in order, present only when there is one. */
  moss_tool_steps?: ToolStep[];
  /** The `X-Moss-Request-Id` of the response. `JSON.stringify` leaves it out. */
  readonly requestId?: string;
}
