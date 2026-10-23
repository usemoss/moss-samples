import { describe, expect, it } from "vitest";
import { chunkIdsForPath, chunkNote, frontmatterLineCount, noteTitleFromPath, splitLongLine } from "../src/indexer/chunker";

const NOTE = `---
title: Ignored
tags: [a, b]
---
Intro paragraph before any heading.

# Retry policy

We back off exponentially.

## Limits

Max five attempts.

\`\`\`ts
# not a heading inside a fence
const x = 1;
\`\`\`

### Exceptions

Timeouts are not retried.

# Second top-level

Body two.
`;

describe("chunkNote", () => {
  it("returns nothing for empty or whitespace-only notes", () => {
    expect(chunkNote("a.md", "")).toEqual([]);
    expect(chunkNote("a.md", "   \n\n")).toEqual([]);
  });

  it("splits on headings and builds breadcrumbs with the note title first", () => {
    const docs = chunkNote("notes/Ops.md", NOTE);
    const paths = docs.map((d) => d.metadata?.headingPath);
    expect(paths).toEqual([
      "Ops",
      "Ops > Retry policy",
      "Ops > Retry policy > Limits",
      "Ops > Retry policy > Limits > Exceptions",
      "Ops > Second top-level",
    ]);
  });

  it("ignores '#' lines inside fenced code blocks", () => {
    const docs = chunkNote("Ops.md", NOTE);
    const limits = docs.find((d) => d.metadata?.heading === "Limits");
    expect(limits?.text).toContain("# not a heading inside a fence");
    expect(docs.some((d) => d.metadata?.heading === "not a heading inside a fence")).toBe(false);
  });

  it("skips frontmatter but keeps 1-based line numbers accurate", () => {
    const docs = chunkNote("Ops.md", NOTE);
    const intro = docs[0];
    expect(intro.text).not.toContain("tags: [a, b]");
    // Line 5 is "Intro paragraph before any heading."
    expect(intro.metadata?.startLine).toBe("5");
    const retry = docs[1];
    expect(retry.metadata?.startLine).toBe("7"); // "# Retry policy"
  });

  it("prefixes each chunk's text with its breadcrumb", () => {
    const docs = chunkNote("Ops.md", NOTE);
    for (const doc of docs) {
      expect(doc.text.startsWith(`${doc.metadata?.headingPath}\n`)).toBe(true);
    }
  });

  it("assigns stable sequential ids", () => {
    const docs = chunkNote("dir/Note.md", NOTE);
    expect(docs.map((d) => d.id)).toEqual(chunkIdsForPath("dir/Note.md", docs.length));
    expect(docs.map((d) => d.metadata?.chunkIndex)).toEqual(docs.map((_, i) => String(i)));
  });

  it("windows long sections with overlap and contiguous line ranges", () => {
    const body = Array.from({ length: 60 }, (_, i) => `line ${i + 1} ${"x".repeat(40)}`).join("\n");
    const docs = chunkNote("Long.md", `# Big\n${body}`, { maxCharsPerChunk: 500, overlapLines: 2 });
    expect(docs.length).toBeGreaterThan(1);
    for (const doc of docs) {
      expect(doc.metadata?.headingPath).toBe("Long > Big");
      expect(doc.text.length).toBeLessThanOrEqual(500 + "Long > Big\n".length + 60);
    }
    for (let i = 1; i < docs.length; i++) {
      const prevEnd = Number(docs[i - 1].metadata?.endLine);
      const start = Number(docs[i].metadata?.startLine);
      // Overlap of 2 lines: next window starts 2 lines before the previous end.
      expect(start).toBe(prevEnd - 1);
    }
  });

  it("handles a lone heading with no body", () => {
    const docs = chunkNote("H.md", "# Only a heading");
    expect(docs).toHaveLength(1);
    expect(docs[0].metadata?.heading).toBe("Only a heading");
  });

  it("normalizes CRLF", () => {
    const docs = chunkNote("W.md", "# A\r\n\r\nbody\r\n");
    expect(docs).toHaveLength(1);
    expect(docs[0].text).toBe("W > A\n# A\n\nbody");
  });

  it("resets deeper headings when a shallower heading appears", () => {
    const docs = chunkNote("T.md", "# A\n## B\n### C\n## D\n");
    expect(docs.map((d) => d.metadata?.headingPath)).toEqual(["T > A", "T > A > B", "T > A > B > C", "T > A > D"]);
  });

  it("does not treat a bare '#' line as a heading", () => {
    const docs = chunkNote("T.md", "# A\nbody\n#\nmore");
    expect(docs).toHaveLength(1);
    expect(docs[0].text).toContain("#\nmore");
  });

  it("keeps '#' inside a four-backtick fence quoting a three-backtick fence", () => {
    const note = "# A\n````md\n```\n# quoted\n```\n````\nafter";
    const docs = chunkNote("T.md", note);
    expect(docs).toHaveLength(1);
    expect(docs[0].text).toContain("# quoted");
  });

  it("caps chunks even when a section is one enormous line", () => {
    const paragraph = Array.from({ length: 400 }, (_, i) => `word${i} stuff here.`).join(" ");
    const docs = chunkNote("Long.md", `# Big\n${paragraph}`, { maxCharsPerChunk: 500 });
    expect(docs.length).toBeGreaterThan(1);
    for (const doc of docs) {
      // Total text (breadcrumb + body) never exceeds the cap.
      expect(doc.text.length).toBeLessThanOrEqual(500);
      // Every piece keeps its source line (heading is line 1, paragraph line 2).
      expect(["1", "2"]).toContain(doc.metadata?.startLine);
      expect(["1", "2"]).toContain(doc.metadata?.endLine);
    }
    expect(docs.some((doc) => doc.metadata?.endLine === "2")).toBe(true);
  });
});

describe("splitLongLine", () => {
  it("returns short lines untouched", () => {
    expect(splitLongLine("short", 100)).toEqual(["short"]);
  });

  it("splits at whitespace and never exceeds the cap", () => {
    const line = "aaa bbb ccc ddd eee fff".repeat(20);
    const pieces = splitLongLine(line, 50);
    expect(pieces.length).toBeGreaterThan(1);
    for (const piece of pieces) {
      expect(piece.length).toBeLessThanOrEqual(50);
    }
    expect(pieces.join(" ").replace(/\s+/g, " ")).toBe(line.replace(/\s+/g, " "));
  });

  it("hard-cuts a single token longer than the cap", () => {
    const pieces = splitLongLine("x".repeat(120), 50);
    expect(pieces.map((piece) => piece.length)).toEqual([50, 50, 20]);
  });
});

describe("helpers", () => {
  it("frontmatterLineCount", () => {
    expect(frontmatterLineCount(["---", "a: 1", "---", "x"])).toBe(3);
    expect(frontmatterLineCount(["x", "---", "a: 1", "---"])).toBe(0);
    expect(frontmatterLineCount(["---", "never closed"])).toBe(0);
  });

  it("noteTitleFromPath", () => {
    expect(noteTitleFromPath("a/b/Note Name.md")).toBe("Note Name");
    expect(noteTitleFromPath("Note.MD")).toBe("Note");
  });
});
