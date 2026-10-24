import path from 'node:path'

import type { RepoDocument } from '../document.js'

import { CHUNK_TYPE_CODE } from '../types.js'
import { FileChunkRequest, makeDocument, splitLines } from './common.js'

export const WINDOW_LINES = 60
export const OVERLAP_LINES = 15

const SYMBOL_PATTERNS = [
  /^\s*(?:async\s+)?def\s+([A-Za-z_][\w]*)/,
  /^\s*class\s+([A-Za-z_][\w]*)/,
  /^\s*(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_][\w]*)/,
  /^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_][\w]*)\s*=/,
  /^\s*func\s+([A-Za-z_][\w]*)/,
  /^\s*(?:pub\s+)?(?:async\s+)?fn\s+([A-Za-z_][\w]*)/,
]

export function chunkCode(request: FileChunkRequest): RepoDocument[] {
  const lines = splitLines(request.content)
  if (lines.length === 0) {
    return []
  }
  const docs: RepoDocument[] = []
  let start = 1
  const total = lines.length
  while (start <= total) {
    const end = Math.min(start + WINDOW_LINES - 1, total)
    const body = lines.slice(start - 1, end).join('\n')
    const symbol = detectSymbol(lines.slice(start - 1, end)) ?? ''
    const title = symbol || path.basename(request.path)
    docs.push(
      makeDocument(request, {
        startLine: start,
        endLine: end,
        body,
        chunkType: CHUNK_TYPE_CODE,
        symbol,
        title,
      }),
    )
    if (end >= total) {
      break
    }
    start = Math.max(end - OVERLAP_LINES + 1, start + 1)
  }
  return docs
}

function detectSymbol(windowLines: string[]): string | undefined {
  for (const line of windowLines) {
    for (const pattern of SYMBOL_PATTERNS) {
      const match = pattern.exec(line)
      if (match) {
        return match[1]
      }
    }
  }
  return undefined
}
