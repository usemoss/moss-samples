import path from 'node:path'

import type { RepoDocument } from '../document.js'

import {
  METADATA_END_LINE,
  METADATA_LANGUAGE,
  METADATA_NAVIGATION,
  METADATA_PATH,
  METADATA_REF,
  METADATA_REPO,
  METADATA_START_LINE,
  METADATA_SYMBOL,
  METADATA_TITLE,
  METADATA_TYPE,
} from '../types.js'

export interface FileChunkRequest {
  path: string
  root: string
  content: string
  language: string
  repoName?: string
  ref?: string
}

export interface ChunkSlice {
  startLine: number
  endLine: number
  body: string
  chunkType: string
  symbol: string
  title: string
}

export function relativePath(filePath: string, root: string): string {
  return path.relative(root, filePath).split(path.sep).join('/')
}

export function slugify(value: string): string {
  const slug = value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
  return slug || 'section'
}

export function makeDocument(request: FileChunkRequest, slice: ChunkSlice): RepoDocument {
  const rel = relativePath(request.path, request.root)
  const chunkId = chunkIdFor(rel, slice.symbol, slice.startLine, slice.endLine)
  const prefix = slice.symbol ? `${rel} :: ${slice.symbol}` : rel
  const text = `${prefix}\n\n${slice.body}`.trim()
  return {
    id: chunkId,
    text,
    metadata: metadataFor(request, slice, rel),
  }
}

function chunkIdFor(rel: string, symbol: string, startLine: number, endLine: number): string {
  if (symbol) {
    return `${rel}#${slugify(symbol)}:${startLine}-${endLine}`
  }
  return `${rel}:${startLine}-${endLine}`
}

function metadataFor(
  request: FileChunkRequest,
  slice: ChunkSlice,
  rel: string,
): Record<string, string> {
  const meta: Record<string, string> = {
    [METADATA_PATH]: rel,
    [METADATA_LANGUAGE]: request.language,
    [METADATA_TYPE]: slice.chunkType,
    [METADATA_START_LINE]: String(slice.startLine),
    [METADATA_END_LINE]: String(slice.endLine),
    [METADATA_TITLE]: slice.title,
    [METADATA_NAVIGATION]: `${rel}:${slice.startLine}`,
    [METADATA_SYMBOL]: slice.symbol,
  }
  if (request.repoName) {
    meta[METADATA_REPO] = request.repoName
  }
  if (request.ref) {
    meta[METADATA_REF] = request.ref
  }
  return meta
}

export function splitLines(content: string): string[] {
  return content.split(/\r?\n/)
}
