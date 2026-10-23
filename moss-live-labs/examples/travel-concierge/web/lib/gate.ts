import { createHash, createHmac, timingSafeEqual } from "crypto";

export const COOKIE_NAME = "travel_demo_gate";
export const GATE_TTL_MS = 12 * 60 * 60 * 1000; // 12 hours

/** Constant-time compare of arbitrary strings via fixed-length digests. */
export function secretsEqual(a: string, b: string): boolean {
  const ha = createHash("sha256").update(a, "utf8").digest();
  const hb = createHash("sha256").update(b, "utf8").digest();
  return timingSafeEqual(ha, hb);
}

/** HMAC cookie: `{issuedAtMs}.{sig}` — sig covers the issued timestamp so TTL is enforced server-side. */
export function mintGateCookie(secret: string, now = Date.now()): string {
  const issuedAt = String(now);
  const sig = createHmac("sha256", secret).update(`travel-concierge-gate:${issuedAt}`).digest("hex");
  return `${issuedAt}.${sig}`;
}

export function hasValidGateCookie(cookieHeader: string | null, secret: string, now = Date.now()): boolean {
  if (!cookieHeader) return false;
  const match = cookieHeader.match(new RegExp(`(?:^|;\\s*)${COOKIE_NAME}=([^;]+)`));
  const value = match?.[1];
  if (!value) return false;

  const dot = value.indexOf(".");
  if (dot <= 0 || dot === value.length - 1) return false;
  const issuedAt = value.slice(0, dot);
  const sig = value.slice(dot + 1);
  if (!/^\d+$/.test(issuedAt) || !/^[0-9a-f]+$/i.test(sig)) return false;

  const issued = Number(issuedAt);
  if (!Number.isFinite(issued)) return false;
  // Reject future skew > 1 minute and cookies older than the advertised TTL.
  if (issued > now + 60_000 || now - issued > GATE_TTL_MS) return false;

  const expected = createHmac("sha256", secret).update(`travel-concierge-gate:${issuedAt}`).digest("hex");
  try {
    const a = Buffer.from(sig, "utf8");
    const b = Buffer.from(expected, "utf8");
    return a.length === b.length && timingSafeEqual(a, b);
  } catch {
    return false;
  }
}
