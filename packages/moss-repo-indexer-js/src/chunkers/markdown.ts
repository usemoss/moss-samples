import path from 'node:path'

import type { RepoDocument } from '../document.js'

import { CHUNK_TYPE_HEADER, CHUNK_TYPE_PAGE, CHUNK_TYPE_TEXT } from '../types.js'
import { FileChunkRequest, makeDocument, relativePath, splitLines } from './common.js'

const HEADING_RE = /^(#{1,6})\s+(.+?)\s*$/

export function chunkMarkdown(request: FileChunkRequest): RepoDocument[] {
  const lines = splitLines(request.content)
  const docs: RepoDocument[] = [pageDocument(request)]
  const sections = parseSections(lines, relativePath(request.path, request.root))
  for (const section of sections) {
    docs.push(...documentsForSection(request, section))
  }
  return docs
}

function pageDocument(request: FileChunkRequest): RepoDocument {
  const rel = relativePath(request.path, request.root)
  const title = path.basename(request.path, path.extname(request.path))
  const endLine = Math.max(1, splitLines(request.content).length)
  const generated = makeDocument(request, {
    startLine: 1,
    endLine,
    body: title,
    chunkType: CHUNK_TYPE_PAGE,
    symbol: '',
    title,
  })
  return { id: rel, text: generated.text, metadata: generated.metadata }
}

type Section = { heading: string; startLine: number; endLine: number; body: string }

function parseSections(lines: string[], fallbackTitle: string): Section[] {
  const buffered: Array<{ heading: string; start: number; body: string[] }> = []
  let heading = fallbackTitle
  let start = 1
  let body: string[] = []

  lines.forEach((line, index) => {
    const lineNo = index + 1
    const match = HEADING_RE.exec(line)
    if (match) {
      flushSection(buffered, heading, start, body)
      heading = match[2].trim()
      start = lineNo
      body = [line]
      return
    }
    body.push(line)
  })
  flushSection(buffered, heading, start, body)

  return buffered
    .filter((item) => item.body.length > 0)
    .map((item) => ({
      heading: item.heading,
      startLine: item.start,
      endLine: item.start + item.body.length - 1,
      body: item.body.join('\n').trim(),
    }))
}

function flushSection(
  sections: Array<{ heading: string; start: number; body: string[] }>,
  heading: string,
  start: number,
  body: string[],
): void {
  if (body.length > 0) {
    sections.push({ heading, start, body: [...body] })
  }
}

function documentsForSection(request: FileChunkRequest, section: Section): RepoDocument[] {
  const docs: RepoDocument[] = [
    makeDocument(request, {
      startLine: section.startLine,
      endLine: section.startLine,
      body: section.heading,
      chunkType: CHUNK_TYPE_HEADER,
      symbol: section.heading,
      title: section.heading,
    }),
  ]
  const bodyWithoutHeading = stripLeadingHeading(section.body)
  if (bodyWithoutHeading) {
    docs.push(
      makeDocument(request, {
        startLine: section.startLine,
        endLine: section.endLine,
        body: bodyWithoutHeading,
        chunkType: CHUNK_TYPE_TEXT,
        symbol: section.heading,
        title: section.heading,
      }),
    )
  }
  return docs
}

function stripLeadingHeading(body: string): string {
  const lines = body.split(/\r?\n/)
  if (lines.length > 0 && HEADING_RE.test(lines[0])) {
    return lines.slice(1).join('\n').trim()
  }
  return body.trim()
}
