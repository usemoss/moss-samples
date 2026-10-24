import type { RepoDocument } from './document.js'
import { resolveSource, type ResolvedSource } from './clone.js'
import { buildDocuments } from './documents.js'
import { SyncOptions, resolveIndexOptions, type IndexOptions } from './types.js'
import { uploadDocuments, type MutationResultLike } from './uploader.js'

export interface SyncResult {
  documents: RepoDocument[]
  mutation?: MutationResultLike
  dryRun: boolean
  repoName: string
  root: string
}

export async function sync(options: SyncOptions): Promise<SyncResult> {
  const index = resolveIndexOptions(options.index ?? {})
  const resolved = resolveSource(options.source, index.ref)
  try {
    return await syncResolved(options, resolved, index)
  } finally {
    resolved.close()
  }
}

async function syncResolved(
  options: SyncOptions,
  resolved: ResolvedSource,
  index: ReturnType<typeof resolveIndexOptions>,
): Promise<SyncResult> {
  const indexOpts: IndexOptions = {
    ...index,
    repoName: index.repoName ?? resolved.repoName,
  }
  const documents = buildDocuments(resolved.root, indexOpts)
  if (options.dryRun) {
    return {
      documents,
      dryRun: true,
      repoName: resolved.repoName,
      root: resolved.root,
    }
  }
  const mutation = await uploadDocuments(documents, options.creds, {
    upsert: options.upsert ?? false,
    replace: options.replace ?? false,
  })
  return {
    documents,
    mutation,
    dryRun: false,
    repoName: resolved.repoName,
    root: resolved.root,
  }
}
