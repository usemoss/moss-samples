type Bucket = { count: number; resetAt: number };

const buckets = new Map<string, Bucket>();
const MAX_BUCKETS = 256;

/** Allowed explicit client-IP headers — set exactly one via TRUSTED_CLIENT_IP_HEADER. */
const TRUSTED_IP_HEADERS = new Set([
  "cf-connecting-ip",
  "x-vercel-forwarded-for",
  "x-real-ip",
]);

function evictExpired(now: number) {
  for (const [key, entry] of buckets) {
    if (now >= entry.resetAt) buckets.delete(key);
  }
}

function soonestRetryAfterSec(now: number): number {
  let soonest = Infinity;
  for (const entry of buckets.values()) {
    soonest = Math.min(soonest, entry.resetAt);
  }
  if (!Number.isFinite(soonest)) return 1;
  return Math.max(1, Math.ceil((soonest - now) / 1000));
}

/**
 * In-process rate limiter with TTL eviction.
 * Resets on process restart / across workers — pair with edge limits for public deploys.
 *
 * At capacity, unknown keys fail closed instead of evicting live counters (which would
 * let an evicted client restart its allowance before the window ended).
 */
export function rateLimit(
  key: string,
  { limit, windowMs }: { limit: number; windowMs: number },
): { ok: true } | { ok: false; retryAfterSec: number } {
  const now = Date.now();
  evictExpired(now);

  let entry = buckets.get(key);
  if (!entry || now >= entry.resetAt) {
    if (entry) buckets.delete(key);
    // New key (or expired key we just removed): never drop another client's active bucket.
    if (!buckets.has(key) && buckets.size >= MAX_BUCKETS) {
      return { ok: false, retryAfterSec: soonestRetryAfterSec(now) };
    }
    entry = { count: 0, resetAt: now + windowMs };
    buckets.set(key, entry);
  }
  entry.count += 1;
  if (entry.count > limit) {
    return { ok: false, retryAfterSec: Math.max(1, Math.ceil((entry.resetAt - now) / 1000)) };
  }
  return { ok: true };
}

/**
 * Read-only lockout check: has `key` already spent `limit` in the current window?
 *
 * Consumes nothing, so a caller can reject *every* submission while a window is locked
 * while charging the bucket only for the submissions that deserve it (e.g. wrong
 * guesses). Pairing rateLimit() alone with a conditional branch cannot do this: the
 * branch that never calls it is never blocked by it.
 */
export function isLocked(key: string, limit: number): false | { retryAfterSec: number } {
  const now = Date.now();
  const entry = buckets.get(key);
  if (!entry || now >= entry.resetAt || entry.count < limit) return false;
  return { retryAfterSec: Math.max(1, Math.ceil((entry.resetAt - now) / 1000)) };
}

/**
 * Rate-limit identity from exactly one configured trusted header.
 *
 * Set TRUSTED_CLIENT_IP_HEADER to one of: cf-connecting-ip | x-vercel-forwarded-for | x-real-ip.
 * Reading multiple headers under a boolean flag is unsafe when a proxy only sanitizes its own
 * header and a higher-priority spoofed header is still accepted.
 * Unset / unknown → shared "global" bucket. Never trusts X-Forwarded-For.
 */
export function clientKey(request: Request): string {
  const configured = process.env.TRUSTED_CLIENT_IP_HEADER?.trim().toLowerCase();
  if (!configured || !TRUSTED_IP_HEADERS.has(configured)) {
    return "global";
  }

  const raw = request.headers.get(configured)?.trim();
  if (!raw) return "global";

  // x-vercel-forwarded-for may be a short list; take the first platform-provided hop.
  const ip = configured === "x-vercel-forwarded-for" ? raw.split(",")[0]?.trim() : raw;
  return ip ? `ip:${ip}` : "global";
}
