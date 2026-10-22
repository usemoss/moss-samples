import {
  InferenceError,
  errorFromResponse,
  responseFields,
  transportError,
  type ResponseFields,
} from "./error";
import { ChatCompletionStream, aggregate, errorText, idleTimer } from "./stream";
import type {
  ChatCompletion,
  ChatCompletionCreateParams,
  ChatCompletionCreateParamsNonStreaming,
  ChatCompletionCreateParamsStreaming,
  InferenceRequestOptions,
  MossInferenceOptions,
} from "./types";

/** The production gateway, up to and including `/v1`. */
const DEFAULT_URL = "https://inference.moss.dev/v1";
const DEFAULT_MODEL = "moss";
const DEFAULT_IDLE_TIMEOUT = 120_000;
/** The longest delay `setTimeout` holds. */
const MAX_DELAY = 2 ** 31 - 1;

function env(name: string): string | undefined {
  return (typeof process !== "undefined" && process.env[name]) || undefined;
}

function invalid(message: string): InferenceError {
  return new InferenceError(message, { type: "invalid_request_error" });
}

/** Printable Latin-1 with no space or tab at either end, which fetch would trim. */
const HEADER_SAFE = /^(?![\t ])[\t\x20-\x7e\x80-\xff]*(?<![\t ])$/;

/** Returns `value` when a header carries it unchanged. The error names `what`, never the value. */
function headerSafe(what: string, value: unknown): string {
  if (typeof value === "string" && HEADER_SAFE.test(value)) return value;
  throw invalid(`${what} must be printable Latin-1 text without surrounding spaces.`);
}

function credential(what: string, value: unknown): string {
  if (value == null || value === "") throw invalid(`${what} is missing or empty.`);
  return headerSafe(what, value);
}

/** The authority after `http://` or `https://`, up to the path. */
const AUTHORITY = /^https?:\/\/([^/]*)/i;

/**
 * The chat completions URL under `MOSS_INFERENCE_URL`, or under production when it is unset or empty.
 *
 * `new URL` repairs malformed text, so the text must be printable ASCII
 * that starts with `http://` or `https://`, then a host with no user info or port 0,
 * with no backslash, query or fragment. Anything else throws, naming the variable but not the value.
 */
function endpoint(): string {
  const text = env("MOSS_INFERENCE_URL") ?? DEFAULT_URL;
  const authority = AUTHORITY.exec(text)?.[1];
  let url: URL | undefined;
  try {
    url = new URL(text);
  } catch {
    url = undefined;
  }
  if (
    !/^[!-~]+$/.test(text) ||
    !authority ||
    authority.includes("@") ||
    !url ||
    url.port === "0" ||
    /[\\?#]/.test(text)
  ) {
    throw invalid(
      "MOSS_INFERENCE_URL must be an absolute http or https URL with a host and no user info, query or fragment.",
    );
  }
  return `${url.href.replace(/\/$/, "")}/chat/completions`;
}

/** Throws when `options` names a gateway URL, which only `MOSS_INFERENCE_URL` sets. */
function refuseURL(options: object): void {
  const { baseURL, baseUrl } = options as { baseURL?: unknown; baseUrl?: unknown };
  if (baseURL !== undefined || baseUrl !== undefined)
    throw invalid("Set the gateway URL in MOSS_INFERENCE_URL. There is no baseURL option.");
}

/** Headers fetch derives from the URL and the body. */
const FETCH_HEADERS = ["host", "content-length", "transfer-encoding"];

function headersOf(init: Record<string, string> | undefined): Headers {
  let headers: Headers;
  try {
    headers = new Headers(init);
  } catch {
    throw invalid("The headers option holds a name or value a header cannot carry.");
  }
  if (FETCH_HEADERS.some((name) => headers.has(name)))
    throw invalid("Host, Content-Length and Transfer-Encoding cannot be set.");
  for (const [name, value] of headers) headerSafe(`The ${name} header`, value);
  return headers;
}

/** Milliseconds for a timer, or null for no limit. */
function delay(what: string, value: unknown): number | null {
  if (value === null || value === Infinity) return null;
  if (typeof value === "number" && value > 0 && value < Infinity) return Math.min(value, MAX_DELAY);
  throw invalid(`${what} must be a positive number of milliseconds, or null for no limit.`);
}

/** The `chat.completions` namespace of a {@link MossInference} client, shaped like OpenAI's. */
export interface ChatCompletions {
  /**
   * Sends a chat completion through the Moss inference gateway.
   *
   * The gateway searches `indexes` and adds what it finds to the prompt.
   * Failures reject with {@link InferenceError}. With `stream: true` this
   * resolves to a {@link ChatCompletionStream} once the gateway accepts the request,
   * and otherwise to one {@link ChatCompletion} built from the whole stream.
   */
  create(
    params: ChatCompletionCreateParamsStreaming,
    options?: InferenceRequestOptions,
  ): Promise<ChatCompletionStream>;
  create(
    params: ChatCompletionCreateParamsNonStreaming,
    options?: InferenceRequestOptions,
  ): Promise<ChatCompletion>;
  create(
    params: ChatCompletionCreateParams,
    options?: InferenceRequestOptions,
  ): Promise<ChatCompletionStream | ChatCompletion>;
}

/**
 * A drop-in for OpenAI's client that answers from your Moss indexes.
 *
 * Calls go to the production gateway, or to the base URL
 * in `MOSS_INFERENCE_URL` when the client is built.
 * A wrong URL, credential, provider key, header or timeout, or a `baseURL` option,
 * makes the constructor throw {@link InferenceError} with `invalid_request_error`.
 */
export class MossInference {
  /** OpenAI's `chat.completions`, answered by the Moss inference gateway. */
  readonly chat: { readonly completions: ChatCompletions };
  /** Where every call goes. */
  readonly #url: string;
  /** The caller's headers for every call. */
  readonly #headers: Headers;
  /** The SDK's own headers, which win over the caller's. */
  readonly #own: Headers;
  readonly #timeout: number | null;
  readonly #idleTimeout: number | null;
  /** The provider key for calls that do not pass their own. */
  readonly #apiKey: string | undefined;

  constructor(projectId: string, projectKey: string, options: MossInferenceOptions = {}) {
    const id = credential("projectId", projectId);
    const key = credential("projectKey", projectKey);
    if (id.includes(":")) throw invalid("projectId must not contain a colon.");
    refuseURL(options);
    this.#url = endpoint();
    this.#timeout = delay("timeout", options.timeout ?? null);
    const { idleTimeout = DEFAULT_IDLE_TIMEOUT } = options;
    this.#idleTimeout = delay("idleTimeout", idleTimeout);
    this.#headers = headersOf(options.headers);
    this.#own = new Headers({
      Authorization: `Bearer ${id}:${key}`,
      "Content-Type": "application/json",
      Accept: "text/event-stream",
    });
    this.#apiKey = options.apiKey == null ? undefined : credential("apiKey", options.apiKey);
    const create = (params: ChatCompletionCreateParams, call?: InferenceRequestOptions) =>
      this.#create(params, call);
    this.chat = Object.freeze({
      completions: Object.freeze({ create: create as ChatCompletions["create"] }),
    });
  }

  async #create(
    params: ChatCompletionCreateParams,
    options: InferenceRequestOptions = {},
  ): Promise<ChatCompletionStream | ChatCompletion> {
    refuseURL(options);
    const { indexes, retrieve, model = DEFAULT_MODEL, ...body } = params;
    if (body.apiKey !== undefined || body.api_key !== undefined)
      throw invalid("Pass the provider key as apiKey in the options of create, not in params.");
    if (indexes !== undefined && !Array.isArray(indexes))
      throw invalid("indexes must be an array of index names.");
    for (const name of indexes ?? []) {
      if (typeof name !== "string" || name === "" || name.includes(",")) {
        throw invalid(
          `Invalid index name ${JSON.stringify(name)}. Names must be non-empty and contain no comma.`,
        );
      }
      headerSafe(`Index name ${JSON.stringify(name)}`, name);
    }
    const apiKey = options.apiKey == null ? this.#apiKey : credential("apiKey", options.apiKey);
    const timeout =
      options.timeout === undefined ? this.#timeout : delay("timeout", options.timeout);
    const idleTimeout =
      options.idleTimeout === undefined
        ? this.#idleTimeout
        : delay("idleTimeout", options.idleTimeout);
    const headers = new Headers(this.#headers);
    for (const [name, value] of headersOf(options.headers)) headers.set(name, value);
    for (const [name, value] of this.#own) headers.set(name, value);
    if (indexes?.length) headers.set("X-Moss-Indexes", indexes.join(","));
    if (retrieve === false) headers.set("X-Moss-Retrieve", "off");
    if (apiKey !== undefined) headers.set("X-Moss-Provider-Key", apiKey);
    let payload: string;
    try {
      payload = JSON.stringify({ model, ...body, stream: true });
    } catch (cause) {
      throw new InferenceError(`The parameters cannot be sent as JSON: ${String(cause)}`, {
        type: "invalid_request_error",
        cause,
      });
    }

    const { signal } = options;
    const controller = new AbortController();
    let fields: ResponseFields = {};
    const expire = (message: string) => () =>
      controller.abort(new InferenceError(message, { type: "timeout", ...fields }));
    const timer =
      timeout === null
        ? undefined
        : setTimeout(expire(`The request timed out after ${timeout} ms.`), timeout);
    const idle = idleTimer(idleTimeout, expire(`The gateway sent nothing for ${idleTimeout} ms.`));
    const onAbort = () => controller.abort(signal?.reason);
    signal?.addEventListener("abort", onAbort, { once: true });
    if (signal?.aborted) onAbort();
    const settle = () => {
      clearTimeout(timer);
      idle.clear();
      signal?.removeEventListener("abort", onAbort);
    };

    let response: Response;
    try {
      idle.arm();
      response = await fetch(this.#url, {
        method: "POST",
        headers,
        body: payload,
        signal: controller.signal,
        redirect: "manual",
      });
    } catch (error) {
      settle();
      if (controller.signal.aborted) throw controller.signal.reason;
      throw transportError(error, "The inference gateway did not answer");
    }
    idle.clear();
    fields = responseFields(response);
    if (!response.ok) {
      const text = await errorText(response, idle).catch(() => "");
      settle();
      if (controller.signal.aborted) throw controller.signal.reason;
      throw errorFromResponse(response, text);
    }
    const stream = new ChatCompletionStream(response, controller, idle, settle);
    return params.stream ? stream : aggregate(stream, model);
  }
}

let fallback: { env: string; client: MossInference } | undefined;

/** The client of `inference`, for the current environment. */
function defaultClient(): MossInference {
  const [id, key] = ["MOSS_PROJECT_ID", "MOSS_PROJECT_KEY"].map(env);
  if (!id || !key) {
    throw invalid(
      "Missing project credentials. Set MOSS_PROJECT_ID and MOSS_PROJECT_KEY, or create a MossInference.",
    );
  }
  const snapshot = JSON.stringify([id, key, env("MOSS_INFERENCE_URL")]);
  if (fallback?.env !== snapshot) fallback = { env: snapshot, client: new MossInference(id, key) };
  return fallback.client;
}

/**
 * Chat completions through a {@link MossInference} client.
 * Each call reads `MOSS_PROJECT_ID`, `MOSS_PROJECT_KEY` and `MOSS_INFERENCE_URL`.
 * The client is built on first use, and again when one of them changes.
 */
export const inference: {
  readonly chat: { readonly completions: ChatCompletions };
} = Object.freeze({
  chat: Object.freeze({
    completions: Object.freeze({
      create: (async (params: ChatCompletionCreateParams, options?: InferenceRequestOptions) =>
        defaultClient().chat.completions.create(params, options)) as ChatCompletions["create"],
    }),
  }),
});
