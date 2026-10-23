import { describe, expect, it } from "vitest";
import { dedupeByNote, mapHit, previewText } from "../src/search/search";

describe("mapHit", () => {
  it("maps metadata and strips the breadcrumb prefix from text", () => {
    const hit = mapHit({
      id: "a/b.md#chunk-3",
      text: "b > Sec\nbody line",
      score: 0.82,
      metadata: {
        filePath: "a/b.md",
        title: "b",
        headingPath: "b > Sec",
        heading: "Sec",
        startLine: "12",
        endLine: "20",
      },
    });
    expect(hit).toEqual({
      id: "a/b.md#chunk-3",
      score: 0.82,
      text: "body line",
      filePath: "a/b.md",
      title: "b",
      headingPath: "b > Sec",
      heading: "Sec",
      startLine: 12,
      endLine: 20,
    });
  });

  it("falls back to id-derived path and safe defaults when metadata is missing", () => {
    const hit = mapHit({ id: "x/y.md#chunk-0", text: "t", score: 0.5 });
    expect(hit.filePath).toBe("x/y.md");
    expect(hit.title).toBe("x/y");
    expect(hit.startLine).toBe(1);
    expect(hit.text).toBe("t");
  });
});

describe("dedupeByNote", () => {
  const hits = [
    { filePath: "a.md", score: 0.9 },
    { filePath: "b.md", score: 0.8 },
    { filePath: "a.md", score: 0.7 },
  ].map((h, i) => ({
    id: `${h.filePath}#chunk-${i}`,
    text: "",
    title: "",
    headingPath: "",
    heading: "",
    startLine: 1,
    endLine: 1,
    ...h,
  }));

  it("keeps the first (best) hit per note when enabled", () => {
    expect(dedupeByNote(hits, true).map((h) => h.id)).toEqual(["a.md#chunk-0", "b.md#chunk-1"]);
  });

  it("is a no-op when disabled", () => {
    expect(dedupeByNote(hits, false)).toBe(hits);
  });
});

describe("previewText", () => {
  it("collapses whitespace and truncates with an ellipsis", () => {
    expect(previewText("a\n\n  b\tc")).toBe("a b c");
    const long = "word ".repeat(100);
    const out = previewText(long, 50);
    expect(out.length).toBeLessThanOrEqual(50);
    expect(out.endsWith("…")).toBe(true);
  });
});
