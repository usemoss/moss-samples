import { describe, expect, it } from "vitest";
import { isNodeVersionSupported } from "../src/moss/client";

describe("isNodeVersionSupported", () => {
  it("requires the SDK's declared engine (>=20.4)", () => {
    expect(isNodeVersionSupported("20.4.0")).toBe(true);
    expect(isNodeVersionSupported("20.19.1")).toBe(true);
    expect(isNodeVersionSupported("22.11.0")).toBe(true);
    expect(isNodeVersionSupported("24.0.0")).toBe(true);
  });

  it("rejects Node older than 20.4, including 20.0-20.3", () => {
    expect(isNodeVersionSupported("20.3.1")).toBe(false);
    expect(isNodeVersionSupported("20.0.0")).toBe(false);
    expect(isNodeVersionSupported("18.20.4")).toBe(false);
    expect(isNodeVersionSupported("12.22.9")).toBe(false);
  });

  it("rejects unparseable output", () => {
    expect(isNodeVersionSupported("")).toBe(false);
    expect(isNodeVersionSupported("not a version")).toBe(false);
    expect(isNodeVersionSupported("20")).toBe(false);
  });

  it("tolerates surrounding whitespace from the probe", () => {
    expect(isNodeVersionSupported("  20.19.1\n")).toBe(true);
  });
});
