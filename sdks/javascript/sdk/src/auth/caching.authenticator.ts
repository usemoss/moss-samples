import type { IAuthenticator, AuthToken } from "./authenticator.interface";

interface TokenCache {
  token: string;
  expiresIn: number;
  expiresAt: number; // ms since epoch
}

export class CachingAuthenticator implements IAuthenticator {
  private cache: TokenCache | null = null;
  private inflight: Promise<AuthToken> | null = null;

  constructor(private readonly inner: IAuthenticator) {}

  async getAuthToken(): Promise<AuthToken> {
    if (this.cache && this.cache.expiresAt > Date.now()) {
      return { token: this.cache.token, expiresIn: this.cache.expiresIn };
    }

    if (this.inflight) {
      return this.inflight;
    }

    this.inflight = this.fetchAndCache();
    try {
      return await this.inflight;
    } finally {
      this.inflight = null;
    }
  }

  async getAuthHeader(): Promise<string> {
    const { token } = await this.getAuthToken();
    return `Bearer ${token}`;
  }

  /**
   * Drops `rejectedToken` if the cache still holds it, so the next call asks
   * the inner authenticator again. A token that already replaced it stays.
   */
  invalidate(rejectedToken: string): void {
    if (this.cache?.token === rejectedToken) this.cache = null;
  }

  private async fetchAndCache(): Promise<AuthToken> {
    const { token, expiresIn } = await this.inner.getAuthToken();
    const lifetime = cacheLifetimeSeconds(expiresIn);
    this.cache = lifetime > 0
      ? { token, expiresIn, expiresAt: Date.now() + lifetime * 1000 }
      : null;
    return { token, expiresIn };
  }
}

/**
 * Seconds to serve a token from the cache: until 60 seconds
 * before it expires, or for 90% of its life when that is later.
 * A numeric string such as "3600" counts as its number. Returns 0, meaning
 * uncached, unless that gives a positive finite number of seconds.
 */
function cacheLifetimeSeconds(expiresIn: unknown): number {
  const seconds =
    typeof expiresIn === "number" || typeof expiresIn === "string"
      ? Number(expiresIn)
      : Number.NaN;
  if (!Number.isFinite(seconds) || seconds <= 0) {
    return 0;
  }
  return Math.max(seconds * 0.9, seconds - 60);
}
