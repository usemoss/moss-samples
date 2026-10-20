/** Stable code on every error the native core or the SDK reports. */
export type MossErrorCode =
  | "INVALID_ARGUMENT"
  | "NOT_FOUND"
  | "UNAUTHORIZED"
  | "NETWORK"
  | "DESERIALIZATION"
  | "MODEL_UNAVAILABLE"
  | "INTERNAL";

/**
 * An `Error` with a stable `code`, from the native core or the SDK.
 * A core failure carries fixed text for each kind of failure, and `detail`
 * holds the core error text. An SDK error describes its cause and has no `detail`.
 */
export interface MossError extends Error {
  /** The kind of failure, stable across releases. */
  code: MossErrorCode;
  /** The core error text, for logs and support. Diagnostic text, not a stable contract. */
  detail?: string;
}

// tsc rejects a code missing from this record or one that is not in `MossErrorCode`.
const CODES = {
  INVALID_ARGUMENT: true,
  NOT_FOUND: true,
  UNAUTHORIZED: true,
  NETWORK: true,
  DESERIALIZATION: true,
  MODEL_UNAVAILABLE: true,
  INTERNAL: true,
} satisfies Record<MossErrorCode, true>;

const MOSS_ERROR_CODES: ReadonlySet<string> = new Set(Object.keys(CODES));

/** True when `error` carries a stable Moss `code`, set by the native core or the SDK. */
export function isMossError(error: unknown): error is MossError {
  if (!(error instanceof Error)) return false;
  const code = (error as { code?: unknown }).code;
  return typeof code === "string" && MOSS_ERROR_CODES.has(code);
}

/** An `Error` with a stable `code`, for a failure the SDK detects itself. */
export function mossError(code: MossErrorCode, message: string): MossError {
  return Object.assign(new Error(message), { code });
}
