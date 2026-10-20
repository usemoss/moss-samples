import { randomUUID } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import type { MossIdentity } from "../models";

const DEVICE_ID_FILE = ".moss-device-id";
export const MAX_IDENTITY_UTF8_BYTES = 256;

const DISALLOWED_IDENTITY_CODE_POINT = /[\p{Cc}\p{Cf}\p{Cs}\uFFFD]/u;

function isValidIdentityId(value: string): boolean {
  return (
    value.length > 0 &&
    value.trim() === value &&
    !DISALLOWED_IDENTITY_CODE_POINT.test(value) &&
    new TextEncoder().encode(value).byteLength <= MAX_IDENTITY_UTF8_BYTES
  );
}

/** @internal */
export interface IdentityTarget {
  setIdentity(
    deviceId?: string | null,
    userId?: string | null,
    mossDeviceId?: string | null,
  ): void;
}

function validateOptionalIdentityId(
  value: unknown,
  field: "deviceId" | "userId",
): string | undefined {
  if (value === undefined) return undefined;
  if (typeof value !== "string" || value.length === 0) {
    throw new TypeError(
      `MossClient options.identity.${field} must be a non-empty string`,
    );
  }
  if (value.trim() !== value) {
    throw new TypeError(
      `MossClient options.identity.${field} must not have leading or trailing whitespace`,
    );
  }
  if (DISALLOWED_IDENTITY_CODE_POINT.test(value)) {
    throw new TypeError(
      `MossClient options.identity.${field} contains an unsupported character`,
    );
  }
  if (new TextEncoder().encode(value).byteLength > MAX_IDENTITY_UTF8_BYTES) {
    throw new TypeError(
      `MossClient options.identity.${field} must be at most ${MAX_IDENTITY_UTF8_BYTES} UTF-8 bytes`,
    );
  }
  return value;
}

/** Validate and snapshot caller identity before any native client is created. */
export function validateMossIdentity(
  identity: MossIdentity | undefined,
): MossIdentity | undefined {
  if (identity === undefined) return undefined;
  if (
    identity === null ||
    typeof identity !== "object" ||
    Array.isArray(identity)
  ) {
    throw new TypeError("MossClient options.identity must be an object");
  }
  return Object.freeze({
    deviceId: validateOptionalIdentityId(identity.deviceId, "deviceId"),
    userId: validateOptionalIdentityId(identity.userId, "userId"),
  });
}

export function identitySupplied(identity: MossIdentity | undefined): boolean {
  return identity?.deviceId !== undefined || identity?.userId !== undefined;
}

export function resolveCachePathDeviceId(dir: string | undefined): string | undefined {
  if (!dir?.trim()) return undefined;
  const file = join(dir, DEVICE_ID_FILE);
  try {
    if (existsSync(file)) {
      const value = readFileSync(file, "utf8").trim();
      return isValidIdentityId(value) ? value : undefined;
    }
    mkdirSync(dir, { recursive: true });
    const id = randomUUID();
    writeFileSync(file, id, "utf8");
    return id;
  } catch {
    return undefined;
  }
}
