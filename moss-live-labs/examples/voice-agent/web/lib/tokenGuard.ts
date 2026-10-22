import { NextResponse } from "next/server";

export type TokenGuardConfig = {
  allowRemoteToken: boolean;
  trustProxy: boolean;
  trustedProxyHops: number;
  /** Exclusive strategy: "x-forwarded-for" | "x-real-ip" */
  trustProxyHeader: string;
  listenHost: string;
  /**
   * Immediate TCP peers allowed to supply forwarded client IPs when trustProxy is on.
   * Use concrete IPs and/or the shorthand "loopback". Empty = fail closed (ignore headers).
   */
  trustedProxies: string[];
};

export function configFromEnv(env: NodeJS.ProcessEnv | Record<string, string | undefined> = process.env): TokenGuardConfig {
  const config: TokenGuardConfig = {
    allowRemoteToken: env.ALLOW_REMOTE_TOKEN === "1",
    trustProxy: env.TRUST_PROXY === "1",
    trustedProxyHops: Math.max(1, Number(env.TRUSTED_PROXY_HOPS || "1") || 1),
    trustProxyHeader: (env.TRUST_PROXY_HEADER || "x-forwarded-for").trim().toLowerCase(),
    listenHost: (env.MOSS_LISTEN_HOST || "").trim().toLowerCase(),
    trustedProxies: (env.TRUSTED_PROXIES || "")
      .split(",")
      .map((part) => part.trim().toLowerCase())
      .filter(Boolean),
  };
  // One-time startup diagnostics — never log these invariants on every /api/token hit.
  warnTokenGuardMisconfig(config);
  return config;
}

/** Log TRUST_PROXY misconfiguration once when config is constructed. */
export function warnTokenGuardMisconfig(config: TokenGuardConfig): void {
  if (!config.trustProxy) return;

  if (config.trustedProxies.length === 0) {
    console.warn(
      "TRUST_PROXY=1 but TRUSTED_PROXIES is empty; ignoring forwarded client IP headers",
    );
  }

  if (
    config.trustProxyHeader !== "x-forwarded-for" &&
    config.trustProxyHeader !== "x-real-ip"
  ) {
    console.warn(
      `Invalid TRUST_PROXY_HEADER=${JSON.stringify(config.trustProxyHeader)}; use "x-forwarded-for" or "x-real-ip"`,
    );
  }
}

function normalizeIp(ip: string): string {
  const normalized = ip.trim().toLowerCase();
  const unwrapped =
    normalized.startsWith("[") && normalized.endsWith("]")
      ? normalized.slice(1, -1)
      : normalized;
  if (unwrapped.startsWith("::ffff:")) {
    const v4 = unwrapped.slice("::ffff:".length);
    if (isValidIpv4(v4)) return v4;
  }
  return unwrapped;
}

/** Valid dotted IPv4 with each octet in 0–255 (no leading junk). */
export function isValidIpv4(ip: string): boolean {
  const parts = ip.split(".");
  if (parts.length !== 4) return false;
  return parts.every((part) => {
    if (!/^\d{1,3}$/.test(part)) return false;
    const n = Number(part);
    return n >= 0 && n <= 255 && String(n) === part; // reject "127.0.0.01" / "127.0.0.999"
  });
}

export function isLoopbackIp(ip: string): boolean {
  const normalized = normalizeIp(ip);
  if (normalized === "::1" || normalized === "0:0:0:0:0:0:0:1") {
    return true;
  }
  if (normalized.startsWith("::ffff:")) {
    const v4 = normalized.slice("::ffff:".length);
    return isValidIpv4(v4) && v4.startsWith("127.");
  }
  return isValidIpv4(normalized) && normalized.startsWith("127.");
}

export function isLoopbackListenHost(host: string): boolean {
  const bracketed = host.match(/^\[([^\]]+)\](?::\d+)?$/);
  const hostname = bracketed?.[1] ?? host.replace(/^([^:]+):\d+$/, "$1");
  return (
    hostname === "127.0.0.1" ||
    hostname === "localhost" ||
    hostname === "::1" ||
    hostname === "0:0:0:0:0:0:0:1"
  );
}

export function isTrustedProxyPeer(immediatePeer: string, trustedProxies: string[]): boolean {
  const peer = normalizeIp(immediatePeer);
  return trustedProxies.some((entry) => {
    if (entry === "loopback") return isLoopbackIp(peer);
    return normalizeIp(entry) === peer;
  });
}

/**
 * Resolve the caller address from forwarded headers.
 * Headers are ignored unless TRUST_PROXY is on, TRUSTED_PROXIES is configured, and
 * the immediate TCP peer is in that allowlist (origin isolation / trusted proxy).
 */
export function peerIp(
  request: Request,
  config: TokenGuardConfig,
  immediatePeer: string | null,
): string | null {
  if (!config.trustProxy) return null;

  // Misconfig (empty TRUSTED_PROXIES / bad TRUST_PROXY_HEADER) is warned once in
  // configFromEnv / warnTokenGuardMisconfig — fail closed quietly per request.
  if (config.trustedProxies.length === 0) {
    return null;
  }

  if (!immediatePeer || !isTrustedProxyPeer(immediatePeer, config.trustedProxies)) {
    return null;
  }

  if (config.trustProxyHeader === "x-real-ip") {
    return request.headers.get("x-real-ip")?.trim() || null;
  }

  if (config.trustProxyHeader !== "x-forwarded-for") {
    return null;
  }

  const xff = request.headers.get("x-forwarded-for");
  if (!xff) return null;
  const parts = xff
    .split(",")
    .map((part) => part.trim())
    .filter(Boolean);
  if (parts.length < config.trustedProxyHops) return null;
  // Rightmost trusted hop — leftmost is attacker-controlled when clients forge XFF
  // and the proxy only appends.
  return parts[parts.length - config.trustedProxyHops] || null;
}

/** Socket / platform peer when available (NextRequest.ip). Never trust Host for this. */
export function immediatePeerFromRequest(request: Request): string | null {
  const ip = (request as Request & { ip?: string | null }).ip;
  return typeof ip === "string" && ip.trim() ? ip.trim() : null;
}

/** Returns a 403 response when the caller is not allowed; otherwise null. */
export function assertLocalDevOnly(
  request: Request,
  config: TokenGuardConfig,
  immediatePeer: string | null = null,
): NextResponse | null {
  if (config.allowRemoteToken) return null;

  const ip = peerIp(request, config, immediatePeer);
  if (ip !== null) {
    return isLoopbackIp(ip)
      ? null
      : new NextResponse("Token endpoint is local-dev only", { status: 403 });
  }

  // No verified peer IP. Allow only when the npm script marked this process as
  // loopback-bound AND the browser Host is also loopback (DNS-rebinding boundary).
  if (!config.trustProxy && config.listenHost && isLoopbackListenHost(config.listenHost)) {
    const host = request.headers.get("host") ?? "";
    if (!isLoopbackListenHost(host)) {
      return new NextResponse("Token endpoint is local-dev only", { status: 403 });
    }
    return null;
  }

  return new NextResponse("Token endpoint is local-dev only", { status: 403 });
}
