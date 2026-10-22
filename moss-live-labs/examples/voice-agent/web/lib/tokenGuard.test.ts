import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  assertLocalDevOnly,
  configFromEnv,
  isLoopbackIp,
  isLoopbackListenHost,
  isTrustedProxyPeer,
  isValidIpv4,
  peerIp,
  warnTokenGuardMisconfig,
  type TokenGuardConfig,
} from "./tokenGuard";

function req(headers: Record<string, string> = {}): Request {
  return new Request("http://127.0.0.1:3000/api/token", { headers });
}

function baseConfig(overrides: Partial<TokenGuardConfig> = {}): TokenGuardConfig {
  return {
    allowRemoteToken: false,
    trustProxy: false,
    trustedProxyHops: 1,
    trustProxyHeader: "x-forwarded-for",
    listenHost: "",
    trustedProxies: [],
    ...overrides,
  };
}

describe("isValidIpv4 / isLoopbackIp", () => {
  it("accepts IPv4 and IPv6 loopback forms", () => {
    assert.equal(isLoopbackIp("127.0.0.1"), true);
    assert.equal(isLoopbackIp("127.1.2.3"), true);
    assert.equal(isLoopbackIp("::1"), true);
    assert.equal(isLoopbackIp("[::1]"), true);
    assert.equal(isLoopbackIp("::ffff:127.0.0.1"), true);
  });

  it("rejects non-loopback and malformed IPv4 octets", () => {
    assert.equal(isLoopbackIp("10.0.0.1"), false);
    assert.equal(isLoopbackIp("192.168.1.1"), false);
    assert.equal(isLoopbackIp("8.8.8.8"), false);
    assert.equal(isValidIpv4("127.999.999.999"), false);
    assert.equal(isLoopbackIp("127.999.999.999"), false);
    assert.equal(isLoopbackIp("127.0.0.01"), false);
    assert.equal(isLoopbackIp("::ffff:127.999.0.1"), false);
  });
});

describe("isLoopbackListenHost", () => {
  it("accepts loopback hosts with optional ports / brackets", () => {
    assert.equal(isLoopbackListenHost("127.0.0.1"), true);
    assert.equal(isLoopbackListenHost("127.0.0.1:3000"), true);
    assert.equal(isLoopbackListenHost("localhost"), true);
    assert.equal(isLoopbackListenHost("[::1]"), true);
    assert.equal(isLoopbackListenHost("[::1]:3000"), true);
  });

  it("rejects non-loopback listen hosts", () => {
    assert.equal(isLoopbackListenHost("0.0.0.0"), false);
    assert.equal(isLoopbackListenHost("192.168.0.5"), false);
    assert.equal(isLoopbackListenHost("evil.example"), false);
  });
});

describe("peerIp strategies", () => {
  const trusted = baseConfig({
    trustProxy: true,
    trustProxyHeader: "x-forwarded-for",
    trustedProxies: ["loopback", "10.0.0.2"],
  });

  it("returns null when TRUST_PROXY is off", () => {
    assert.equal(
      peerIp(req({ "x-forwarded-for": "8.8.8.8", "x-real-ip": "127.0.0.1" }), baseConfig(), "127.0.0.1"),
      null,
    );
  });

  it("ignores forwarded headers when TRUSTED_PROXIES is empty", () => {
    const config = baseConfig({ trustProxy: true, trustedProxies: [] });
    assert.equal(peerIp(req({ "x-forwarded-for": "127.0.0.1" }), config, "127.0.0.1"), null);
  });

  it("ignores forwarded headers when the immediate peer is not a trusted proxy", () => {
    assert.equal(
      peerIp(req({ "x-forwarded-for": "127.0.0.1" }), trusted, "8.8.8.8"),
      null,
    );
    assert.equal(
      peerIp(req({ "x-forwarded-for": "127.0.0.1" }), trusted, null),
      null,
    );
  });

  it("x-forwarded-for uses the rightmost trusted hop after peer verification", () => {
    assert.equal(isTrustedProxyPeer("127.0.0.1", ["loopback"]), true);
    assert.equal(
      peerIp(req({ "x-forwarded-for": "8.8.8.8, 10.0.0.5" }), trusted, "127.0.0.1"),
      "10.0.0.5",
    );
    assert.equal(
      peerIp(req({ "x-forwarded-for": "127.0.0.1, 8.8.8.8" }), trusted, "10.0.0.2"),
      "8.8.8.8",
    );
  });

  it("x-forwarded-for respects TRUSTED_PROXY_HOPS", () => {
    const config = baseConfig({
      trustProxy: true,
      trustProxyHeader: "x-forwarded-for",
      trustedProxyHops: 2,
      trustedProxies: ["loopback"],
    });
    assert.equal(
      peerIp(req({ "x-forwarded-for": "client, proxy1, proxy2" }), config, "127.0.0.1"),
      "proxy1",
    );
    assert.equal(peerIp(req({ "x-forwarded-for": "only-one" }), config, "127.0.0.1"), null);
  });

  it("x-real-ip strategy ignores X-Forwarded-For entirely", () => {
    const config = baseConfig({
      trustProxy: true,
      trustProxyHeader: "x-real-ip",
      trustedProxies: ["loopback"],
    });
    assert.equal(
      peerIp(req({ "x-real-ip": "10.0.0.9", "x-forwarded-for": "127.0.0.1" }), config, "127.0.0.1"),
      "10.0.0.9",
    );
    assert.equal(peerIp(req({ "x-forwarded-for": "127.0.0.1" }), config, "127.0.0.1"), null);
  });

  it("returns null for missing headers or invalid strategy without per-request warnings", () => {
    const warnings: string[] = [];
    const original = console.warn;
    console.warn = (...args: unknown[]) => {
      warnings.push(String(args[0]));
    };
    try {
      assert.equal(peerIp(req({}), trusted, "127.0.0.1"), null);
      assert.equal(
        peerIp(
          req({ "x-forwarded-for": "1.2.3.4" }),
          baseConfig({
            trustProxy: true,
            trustProxyHeader: "x-forwardedfor",
            trustedProxies: ["loopback"],
          }),
          "127.0.0.1",
        ),
        null,
      );
      assert.equal(warnings.length, 0);
    } finally {
      console.warn = original;
    }
  });
});

describe("warnTokenGuardMisconfig", () => {
  it("logs empty TRUSTED_PROXIES and invalid TRUST_PROXY_HEADER once at config time", () => {
    const warnings: string[] = [];
    const original = console.warn;
    console.warn = (...args: unknown[]) => {
      warnings.push(String(args[0]));
    };
    try {
      warnTokenGuardMisconfig(
        baseConfig({
          trustProxy: true,
          trustedProxies: [],
          trustProxyHeader: "x-forwardedfor",
        }),
      );
      assert.ok(warnings.some((w) => w.includes("TRUSTED_PROXIES")));
      assert.ok(warnings.some((w) => w.includes("TRUST_PROXY_HEADER")));

      warnings.length = 0;
      configFromEnv({
        TRUST_PROXY: "1",
        TRUST_PROXY_HEADER: "x-forwardedfor",
        TRUSTED_PROXIES: "",
      });
      assert.ok(warnings.some((w) => w.includes("TRUSTED_PROXIES")));
      assert.ok(warnings.some((w) => w.includes("TRUST_PROXY_HEADER")));
    } finally {
      console.warn = original;
    }
  });
});

describe("assertLocalDevOnly", () => {
  it("allows everything when ALLOW_REMOTE_TOKEN is set", () => {
    assert.equal(assertLocalDevOnly(req(), baseConfig({ allowRemoteToken: true })), null);
  });

  it("allows loopback-bound listen host with loopback Host header", () => {
    assert.equal(
      assertLocalDevOnly(req({ host: "127.0.0.1:3000" }), baseConfig({ listenHost: "127.0.0.1" })),
      null,
    );
    assert.equal(
      assertLocalDevOnly(req({ host: "localhost:3000" }), baseConfig({ listenHost: "localhost" })),
      null,
    );
  });

  it("denies DNS-rebinding Host values even when listen host is loopback", () => {
    const denied = assertLocalDevOnly(
      req({ host: "evil.example" }),
      baseConfig({ listenHost: "127.0.0.1" }),
    );
    assert.ok(denied);
    assert.equal(denied.status, 403);
  });

  it("denies when listen host is missing or non-loopback and peer IP is unknown", () => {
    const denied = assertLocalDevOnly(req({ host: "127.0.0.1" }), baseConfig({ listenHost: "" }));
    assert.ok(denied);
    assert.equal(denied.status, 403);

    const deniedLan = assertLocalDevOnly(
      req({ host: "127.0.0.1" }),
      baseConfig({ listenHost: "0.0.0.0" }),
    );
    assert.ok(deniedLan);
    assert.equal(deniedLan.status, 403);
  });

  it("with TRUST_PROXY, only trusts forwarded IPs from a configured immediate proxy peer", () => {
    const config = baseConfig({
      trustProxy: true,
      trustProxyHeader: "x-forwarded-for",
      trustedProxies: ["loopback"],
      listenHost: "127.0.0.1",
    });
    assert.equal(
      assertLocalDevOnly(req({ "x-forwarded-for": "evil, 127.0.0.1" }), config, "127.0.0.1"),
      null,
    );
    // Untrusted immediate peer — headers ignored, listenHost path blocked by trustProxy.
    const denied = assertLocalDevOnly(
      req({ host: "127.0.0.1", "x-forwarded-for": "127.0.0.1" }),
      config,
      "8.8.8.8",
    );
    assert.ok(denied);
    assert.equal(denied.status, 403);
  });

  it("with TRUST_PROXY + x-real-ip, requires trusted immediate peer", () => {
    const config = baseConfig({
      trustProxy: true,
      trustProxyHeader: "x-real-ip",
      trustedProxies: ["10.0.0.2"],
    });
    assert.equal(
      assertLocalDevOnly(req({ "x-real-ip": "127.0.0.1" }), config, "10.0.0.2"),
      null,
    );
    const denied = assertLocalDevOnly(req({ "x-real-ip": "127.0.0.1" }), config, "10.0.0.9");
    assert.ok(denied);
    assert.equal(denied.status, 403);
  });

  it("does not treat Host spoofing as authorization without listen host", () => {
    const denied = assertLocalDevOnly(
      req({ host: "localhost", "x-forwarded-host": "127.0.0.1" }),
      baseConfig({ listenHost: "" }),
    );
    assert.ok(denied);
    assert.equal(denied.status, 403);
  });

  it("denies null peer when TRUST_PROXY is on even if listen host is loopback", () => {
    const denied = assertLocalDevOnly(
      req({ host: "127.0.0.1" }),
      baseConfig({
        trustProxy: true,
        trustProxyHeader: "x-forwarded-for",
        trustedProxies: ["loopback"],
        listenHost: "127.0.0.1",
      }),
      null,
    );
    assert.ok(denied);
    assert.equal(denied.status, 403);
  });
});
