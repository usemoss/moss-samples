const DEFAULT_BASE_URL = "https://service.usemoss.dev";
const MANAGE_PATH = "/v1/manage";

export class ManageApiError extends Error {
  readonly status: number;
  readonly body: string;

  constructor(status: number, body: string) {
    const suffix = body ? `: ${body}` : "";
    super(`HTTP error! status: ${status}${suffix}`);
    this.name = "ManageApiError";
    this.status = status;
    this.body = body;
  }
}

export function resolveManageUrl(): string {
  const base =
    (typeof process !== "undefined" && process.env.MOSS_CLOUD_API_BASE_URL) ||
    DEFAULT_BASE_URL;
  return `${base.replace(/\/+$/, "")}${MANAGE_PATH}`;
}

function omitUndefined(
  data?: Record<string, unknown>,
): Record<string, unknown> {
  if (!data) {
    return {};
  }
  return Object.fromEntries(
    Object.entries(data).filter(([, value]) => value !== undefined),
  );
}

/**
 * POST /v1/manage with X-Project-Key. Reserved fields (`action`, `projectId`)
 * are assigned after the payload spread so callers cannot overwrite them.
 */
export async function requestManage<T>(
  projectId: string,
  projectKey: string,
  action: string,
  data?: Record<string, unknown>,
): Promise<T> {
  const body = { ...omitUndefined(data), action, projectId };
  const response = await fetch(resolveManageUrl(), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Project-Key": projectKey,
    },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(600_000),
  });
  const text = await response.text();
  if (!response.ok) {
    throw new ManageApiError(response.status, text);
  }
  if (!text) {
    return {} as T;
  }
  return JSON.parse(text) as T;
}
