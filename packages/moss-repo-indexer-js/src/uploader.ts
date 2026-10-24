import type { RepoDocument } from './document.js'
import { DEFAULT_MODEL_NAME, type MossCreds } from './types.js'

export interface UploadOptions {
  upsert?: boolean
  /** When true, delete the existing index then recreate it. Opt-in destructive path. */
  replace?: boolean
}

export interface MutationResultLike {
  jobId?: string
  docCount?: number
}

export async function uploadDocuments(
  documents: RepoDocument[],
  creds: MossCreds,
  options: UploadOptions = {},
): Promise<MutationResultLike> {
  if (documents.length === 0) {
    throw new Error('No documents to upload')
  }
  if (options.upsert && options.replace) {
    throw new Error('Pass only one of upsert or replace')
  }
  const { MossClient } = await import('@moss-dev/moss')
  const client = new MossClient(creds.projectId, creds.projectKey)
  if (options.upsert) {
    return client.addDocs(creds.indexName, documents, { upsert: true })
  }
  if (options.replace) {
    await deleteIndexIfPresent(client, creds.indexName)
  }
  return client.createIndex(creds.indexName, documents, {
    modelId: creds.modelName ?? DEFAULT_MODEL_NAME,
  })
}

async function deleteIndexIfPresent(
  client: { deleteIndex: (name: string) => Promise<boolean> },
  indexName: string,
): Promise<void> {
  try {
    await client.deleteIndex(indexName)
  } catch (error) {
    const message = String(error).toLowerCase()
    if (message.includes('not found') || message.includes('does not exist')) {
      return
    }
    throw error
  }
}
