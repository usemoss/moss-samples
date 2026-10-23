import { describe, expect, it } from "vitest";
import { isExcludedFromIndex, isMarkdownPath, parseExcludedFolders } from "../src/indexer/excludes";

describe("parseExcludedFolders", () => {
  it("splits lines, trims, drops comments/blank lines and trailing slashes", () => {
    expect(parseExcludedFolders("templates/\n\n# comment\n  archive \n./daily/")).toEqual([
      "templates",
      "archive",
      "daily",
    ]);
  });
});

describe("isExcludedFromIndex", () => {
  const excluded = ["templates", "archive/old"];

  it("always skips .obsidian, .trash, .git", () => {
    expect(isExcludedFromIndex(".obsidian/plugins/x/data.json", [])).toBe(true);
    expect(isExcludedFromIndex(".trash/Note.md", [])).toBe(true);
    expect(isExcludedFromIndex("a/.git/HEAD", [])).toBe(true);
  });

  it("matches excluded folders by prefix segment, not substring", () => {
    expect(isExcludedFromIndex("templates/Daily.md", excluded)).toBe(true);
    expect(isExcludedFromIndex("templates-old/Daily.md", excluded)).toBe(false);
    expect(isExcludedFromIndex("archive/old/x.md", excluded)).toBe(true);
    expect(isExcludedFromIndex("archive/new/x.md", excluded)).toBe(false);
  });

  it("treats empty path as excluded", () => {
    expect(isExcludedFromIndex("", [])).toBe(true);
  });

  it("matches case-insensitively (macOS/Windows vault filesystems)", () => {
    expect(isExcludedFromIndex("Templates/Daily.md", ["templates"])).toBe(true);
    expect(isExcludedFromIndex("templates/Daily.md", ["Templates"])).toBe(true);
  });
});

describe("isMarkdownPath", () => {
  it("matches .md case-insensitively", () => {
    expect(isMarkdownPath("a.md")).toBe(true);
    expect(isMarkdownPath("a.MD")).toBe(true);
    expect(isMarkdownPath("a.canvas")).toBe(false);
    expect(isMarkdownPath("a.md.png")).toBe(false);
  });
});
