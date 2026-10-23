import type { DocumentInfo } from "@moss-dev/moss";

/**
 * Markdown-aware chunker for Obsidian notes.
 *
 * A note is split into sections at ATX headings (`#` … `######`), ignoring
 * `#` lines inside fenced code blocks. Each section becomes one chunk, or
 * several windows with a small overlap when it exceeds `maxCharsPerChunk`.
 * A single over-long line (Obsidian soft-wraps, so a paragraph is usually one
 * line) is split at whitespace so no chunk exceeds the cap. YAML frontmatter
 * is skipped (it is rarely useful for semantic search and often contains
 * ids/dates that pollute embeddings). Setext headings (`===`/`---`
 * underlines) are not treated as section breaks; their text still lands in
 * the parent section.
 *
 * Every chunk carries the heading breadcrumb (`Note title > H2 > H3`) both as
 * metadata (for display / navigation) and as the first line of the embedded
 * text, so a query like "retry policy" still matches a section body that only
 * says "we back off exponentially" under a heading called "Retry policy".
 *
 * Chunk ids are stable per (path, index): `${path}#chunk-${n}`. The indexer
 * relies on this to upsert/delete incrementally.
 */

export interface ChunkOptions {
  /** Upper bound on characters of body text per chunk. */
  maxCharsPerChunk?: number;
  /** Lines of overlap between consecutive windows inside one long section. */
  overlapLines?: number;
}

export const DEFAULT_MAX_CHARS_PER_CHUNK = 1600;
export const DEFAULT_OVERLAP_LINES = 2;

// ATX heading with non-empty text (a bare `#` line is not a heading).
const HEADING_RE = /^ {0,3}(#{1,6})\s+(\S.*?)\s*(?:\s#+)?\s*$/;
// Fence opener: a run of 3+ backticks or tildes (CommonMark). Captured so the
// closer must use the same character with at least the same length.
const FENCE_RE = /^ {0,3}(`{3,}|~{3,})/;

interface Section {
  /** Breadcrumb of headings leading to (and including) this section. */
  headingPath: string[];
  /** 0-based index of the first line of the section body (heading line included). */
  startLine: number;
  /** Lines belonging to this section, heading line first when present. */
  lines: string[];
}

export function noteTitleFromPath(relativePath: string): string {
  const base = relativePath.split("/").pop() ?? relativePath;
  return base.replace(/\.md$/i, "");
}

/**
 * Returns the number of leading lines occupied by a YAML frontmatter block
 * (including both `---` fences), or 0 when there is none.
 */
export function frontmatterLineCount(lines: string[]): number {
  if (lines.length < 2 || lines[0].trim() !== "---") {
    return 0;
  }
  for (let i = 1; i < lines.length; i++) {
    const t = lines[i].trim();
    if (t === "---" || t === "...") {
      return i + 1;
    }
  }
  return 0;
}

function splitIntoSections(lines: string[], firstBodyLine: number, title: string): Section[] {
  const sections: Section[] = [];
  const stack: { level: number; text: string }[] = [];
  let current: Section = { headingPath: [title], startLine: firstBodyLine, lines: [] };
  let fenceMarker = "";

  for (let i = firstBodyLine; i < lines.length; i++) {
    const line = lines[i];
    const fence = line.match(FENCE_RE);
    if (fence) {
      const run = fence[1];
      const rest = line.slice(fence[0].length);
      // CommonMark: a backtick-fence opener's info string may not contain
      // backticks (such a line is inline code, not a fence).
      const validOpener = run[0] === "~" || !rest.includes("`");
      if (!fenceMarker) {
        if (validOpener) {
          fenceMarker = run;
        }
      } else if (run[0] === fenceMarker[0] && run.length >= fenceMarker.length && !rest.trim()) {
        fenceMarker = "";
      }
      current.lines.push(line);
      continue;
    }
    const inFence = fenceMarker !== "";

    const heading = !inFence ? line.match(HEADING_RE) : null;
    if (!heading) {
      current.lines.push(line);
      continue;
    }

    sections.push(current);
    const level = heading[1].length;
    const text = heading[2].trim();
    while (stack.length && stack[stack.length - 1].level >= level) {
      stack.pop();
    }
    stack.push({ level, text });
    current = {
      headingPath: [title, ...stack.map((h) => h.text)],
      startLine: i,
      lines: [line],
    };
  }
  sections.push(current);
  return sections;
}

/**
 * Break a single line longer than `maxChars` at whitespace so a wall-of-text
 * paragraph (Obsidian soft-wraps, so one paragraph is usually one line) still
 * fits the embedding window. Pieces keep the original line number.
 */
export function splitLongLine(line: string, maxChars: number): string[] {
  if (line.length <= maxChars) {
    return [line];
  }
  const pieces: string[] = [];
  let rest = line;
  while (rest.length > maxChars) {
    // Prefer a sentence end, then any whitespace, in the back half of the window.
    const window = rest.slice(0, maxChars);
    const floor = Math.floor(maxChars / 2);
    let cut = -1;
    for (const re of [/[.!?]["')\]]?\s+(?=[^\s])/g, /\s+/g]) {
      let m: RegExpExecArray | null;
      let last = -1;
      while ((m = re.exec(window)) !== null) {
        if (m.index + m[0].length > floor) {
          last = m.index + m[0].length;
        }
      }
      if (last > 0) {
        cut = last;
        break;
      }
    }
    if (cut <= 0) {
      cut = maxChars;
    }
    pieces.push(rest.slice(0, cut).trimEnd());
    rest = rest.slice(cut).trimStart();
  }
  if (rest) {
    pieces.push(rest);
  }
  return pieces;
}

interface Window {
  /** 0-based offset of the first source line in this window. */
  startOffset: number;
  /** 0-based offset of the last source line in this window. */
  endOffset: number;
  text: string;
}

function windows(lines: string[], maxChars: number, overlap: number): Window[] {
  // Over-long lines (soft-wrapped paragraphs) are pre-split at whitespace so
  // no window ever exceeds maxChars; each piece keeps its source line offset.
  const pieces: { offset: number; text: string }[] = [];
  lines.forEach((line, offset) => {
    for (const text of splitLongLine(line, maxChars)) {
      pieces.push({ offset, text });
    }
  });

  const out: Window[] = [];
  let start = 0;
  while (start < pieces.length) {
    let end = start;
    let size = 0;
    while (end < pieces.length) {
      const pieceLen = pieces[end].text.length + 1;
      if (size > 0 && size + pieceLen > maxChars) {
        break;
      }
      size += pieceLen;
      end += 1;
    }
    if (end === start) {
      end = start + 1;
    }
    const slice = pieces.slice(start, end);
    out.push({
      startOffset: slice[0].offset,
      endOffset: slice[slice.length - 1].offset,
      text: slice.map((p) => p.text).join("\n"),
    });
    if (end >= pieces.length) {
      break;
    }
    start = Math.max(end - overlap, start + 1);
  }
  return out;
}

export function chunkNote(
  relativePath: string,
  content: string,
  options: ChunkOptions = {},
): DocumentInfo[] {
  // Clamp: a zero/negative/NaN cap (corrupt settings) must never stall the
  // window loop, and the breadcrumb prefix must fit inside the cap too.
  const rawMax = options.maxCharsPerChunk ?? DEFAULT_MAX_CHARS_PER_CHUNK;
  const maxChars = Number.isFinite(rawMax) ? Math.max(200, Math.floor(rawMax)) : DEFAULT_MAX_CHARS_PER_CHUNK;
  const overlap = options.overlapLines ?? DEFAULT_OVERLAP_LINES;

  const normalized = content.replace(/\r\n/g, "\n");
  if (!normalized.trim()) {
    return [];
  }

  const lines = normalized.split("\n");
  const title = noteTitleFromPath(relativePath);
  const firstBodyLine = frontmatterLineCount(lines);
  const sections = splitIntoSections(lines, firstBodyLine, title);

  const docs: DocumentInfo[] = [];
  let chunkIndex = 0;

  for (const section of sections) {
    // Trim leading/trailing blank lines but keep line numbers accurate.
    let first = 0;
    let last = section.lines.length;
    while (first < last && !section.lines[first].trim()) first++;
    while (last > first && !section.lines[last - 1].trim()) last--;
    if (first >= last) {
      continue;
    }
    const body = section.lines.slice(first, last);
    const bodyStart = section.startLine + first;
    const breadcrumb = section.headingPath.join(" > ");
    // Reserve room for the breadcrumb line so text never exceeds maxChars.
    const bodyBudget = Math.max(100, maxChars - breadcrumb.length - 1);

    for (const win of windows(body, bodyBudget, overlap)) {
      const text = win.text;
      if (!text.trim()) {
        continue;
      }
      const startLine = bodyStart + win.startOffset + 1; // 1-based
      const endLine = bodyStart + win.endOffset + 1;
      docs.push({
        id: chunkId(relativePath, chunkIndex),
        text: `${breadcrumb}\n${text}`,
        metadata: {
          filePath: relativePath,
          title,
          headingPath: breadcrumb,
          heading: section.headingPath[section.headingPath.length - 1] ?? title,
          startLine: String(startLine),
          endLine: String(endLine),
          chunkIndex: String(chunkIndex),
        },
      });
      chunkIndex += 1;
    }
  }

  return docs;
}

export function chunkId(relativePath: string, index: number): string {
  return `${relativePath}#chunk-${index}`;
}

export function chunkIdsForPath(relativePath: string, count: number): string[] {
  return Array.from({ length: count }, (_, i) => chunkId(relativePath, i));
}
