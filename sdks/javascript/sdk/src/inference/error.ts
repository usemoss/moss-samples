import type { MossError, MossErrorCode } from "../errors";

/** The kind of failure an {@link InferenceError} reports. */
export type InferenceErrorType =
  | "authentication_error"
  | "permission_error"
  | "not_found_error"
  | "invalid_request_error"
  | "rate_limit_error"
  | "capacity"
  | "mcp_error"
  | "model_error"
  | "server_error"
  | "connection_error"
  | "timeout"
  | "incomplete_stream"
  | (string & {});

const CODE_BY_TYPE = new Map<string, MossErrorCode>([
  ["invalid_request_error", "INVALID_ARGUMENT"],
  ["authentication_error", "UNAUTHORIZED"],
  ["permission_error", "UNAUTHORIZED"],
  ["not_found_error", "NOT_FOUND"],
  ["connection_error", "NETWORK"],
  ["timeout", "NETWORK"],
  ["incomplete_stream", "NETWORK"],
]);

/**
 * The error every inference call throws, before or during the stream.
 * Arguments the SDK rejects before sending carry `invalid_request_error`,
 * code `INVALID_ARGUMENT` and no status. `isMossError` accepts every InferenceError.
 * A caller's abort rejects with the signal's reason, or ends a stream quietly on an `AbortError`.
 */
export class InferenceError extends Error implements MossError {
  /** The HTTP status of a rejected request. Undefined for transport and stream failures. */
  readonly status: number | undefined;
  /** The gateway's `error.type`, or one derived from the status or the failure. */
  readonly type: InferenceErrorType;
  /** The Moss code for `type`. Model, server and rate limit failures are `INTERNAL`. */
  readonly code: MossErrorCode;
  /**
   * The gateway's `error.code`, a string or a safe integer in decimal. Undefined otherwise.
   *
   * `failed_after_tool_call` once the stream carried an MCP tool step.
   * The tool may have changed data, so do not replay the call blindly.
   * The same holds for a call you abort after a step, which has no such code,
   * as with `stream.controller.abort()` or a signal such as `AbortSignal.timeout()`.
   */
  readonly errorCode?: string;
  /** The `X-Moss-Request-Id` of the response. Undefined when the call failed before one arrived. */
  readonly requestId?: string;
  /** The `Retry-After` of an error response in milliseconds, when the header gives whole seconds. */
  readonly retryAfter?: number;

  constructor(
    message: string,
    init: {
      type: InferenceErrorType;
      status?: number;
      errorCode?: string;
      requestId?: string;
      retryAfter?: number;
      cause?: unknown;
    },
  ) {
    super(message, init.cause === undefined ? undefined : { cause: init.cause });
    this.name = "InferenceError";
    this.type = init.type;
    this.code = CODE_BY_TYPE.get(init.type) ?? "INTERNAL";
    this.status = init.status;
    this.errorCode = init.errorCode;
    this.requestId = init.requestId;
    this.retryAfter = init.retryAfter;
  }
}

/** What every {@link InferenceError} of a call takes from its response. */
export interface ResponseFields {
  requestId?: string;
  retryAfter?: number;
  /** Set once the stream carries an MCP tool step. */
  errorCode?: "failed_after_tool_call";
}

/**
 * The request id of any response, and for an error response
 * the `Retry-After` in milliseconds when the header holds delta-seconds.
 */
export function responseFields(response: Response): ResponseFields {
  const retry = response.ok ? null : response.headers.get("Retry-After");
  return {
    requestId: response.headers.get("X-Moss-Request-Id") || undefined,
    retryAfter: retry !== null && /^\d+$/.test(retry) ? Number(retry) * 1000 : undefined,
  };
}

/**
 * The gateway's `error.code` as text: a string as sent, a safe integer in decimal.
 * A larger integer gives none, since `JSON.parse` can change its digits.
 */
export function codeText(code: unknown): string | undefined {
  if (typeof code === "string") return code;
  return Number.isSafeInteger(code) ? String(code) : undefined;
}

const TYPE_BY_STATUS: Record<number, InferenceErrorType> = {
  401: "authentication_error",
  403: "permission_error",
  404: "not_found_error",
  429: "rate_limit_error",
};

/** The longest message a body that is not JSON gives, in characters. */
const MAX_BODY_MESSAGE = 300;

/** The body with its whitespace collapsed, cut to {@link MAX_BODY_MESSAGE} characters. */
function bodyMessage(text: string): string | undefined {
  const chars = Array.from(text.replace(/\s+/g, " ").trim());
  if (chars.length <= MAX_BODY_MESSAGE) return chars.join("") || undefined;
  return `${chars.slice(0, MAX_BODY_MESSAGE - 3).join("")}...`;
}

/** undici's codes for the time limits of Node's fetch, including its 300 s limits on silence. */
const TIMEOUT_CODES = new Set<unknown>([
  "UND_ERR_CONNECT_TIMEOUT",
  "UND_ERR_HEADERS_TIMEOUT",
  "UND_ERR_BODY_TIMEOUT",
]);

/** The error for a fetch or body read that failed in transport, a `timeout` or a `connection_error`. */
export function transportError(
  error: unknown,
  message: string,
  fields: ResponseFields = {},
): InferenceError {
  const cause = (error as { cause?: { code?: unknown; message?: unknown } } | null)?.cause;
  const detail = typeof cause?.message === "string" ? cause.message : String(error);
  const type = TIMEOUT_CODES.has(cause?.code) ? "timeout" : "connection_error";
  return new InferenceError(`${message}: ${detail}`, { type, cause: error, ...fields });
}

/**
 * Builds the error for a non-2xx response from its status and body text.
 * A body that is not JSON gives the message, and an empty one the status line.
 */
export function errorFromResponse(response: Response, text: string): InferenceError {
  let body: unknown;
  let message = `HTTP ${response.status}${response.statusText ? ` ${response.statusText}` : ""}`;
  try {
    body = JSON.parse(text);
  } catch {
    message = bodyMessage(text) ?? message;
  }
  const { error, detail } = (body ?? {}) as {
    error?: { message?: unknown; type?: unknown; code?: unknown };
    detail?: unknown;
  };
  if (typeof error?.message === "string") message = error.message;
  else if (typeof detail === "string") message = detail;
  else if (detail !== undefined) message = JSON.stringify(detail);
  return new InferenceError(message, {
    type:
      typeof error?.type === "string"
        ? error.type
        : (TYPE_BY_STATUS[response.status] ??
          (response.status >= 400 && response.status < 500
            ? "invalid_request_error"
            : "server_error")),
    status: response.status,
    errorCode: codeText(error?.code),
    ...responseFields(response),
  });
}
