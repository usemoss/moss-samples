import fs from 'node:fs'
import path from 'node:path'

import type { RepoDocument } from './document.js'
import { chunkCode, chunkMarkdown, type FileChunkRequest } from './chunkers/index.js'
import { discoverFiles } from './discover.js'
import { isMarkdownPath, languageForPath } from './language.js'
import { IndexOptions, resolveIndexOptions } from './types.js'

export function buildDocuments(root: string, options: IndexOptions = {}): RepoDocument[] {
  const resolvedRoot = path.resolve(root)
  const opts = resolveIndexOptions(options)
  const documents: RepoDocument[] = []
  for (const filePath of discoverFiles(resolvedRoot, opts)) {
    documents.push(...chunkFile(filePath, resolvedRoot, opts))
  }
  return documents
}

function chunkFile(
  filePath: string,
  root: string,
  options: ReturnType<typeof resolveIndexOptions>,
): RepoDocument[] {
  let content: string
  try {
    content = fs.readFileSync(filePath, 'utf8')
  } catch {
    return []
  }
  const request: FileChunkRequest = {
    path: filePath,
    root,
    content,
    language: languageForPath(filePath),
    repoName: options.repoName,
    ref: options.ref,
  }
  if (isMarkdownPath(filePath)) {
    return chunkMarkdown(request)
  }
  return chunkCode(request)
}
