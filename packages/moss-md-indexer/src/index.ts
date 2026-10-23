import path from 'node:path'
import pc from 'picocolors'
import dotenv from 'dotenv'
import { buildJsonDocs } from './builder.js'
import { uploadDocuments, type UploadOptions } from './uploader.js'
import type { MossCreds } from './types.js'

// Re-export functions for advanced usage
export { buildJsonDocs, type BuildOptions } from './builder.js'
export { uploadDocuments, createIndex, type UploadOptions } from './uploader.js'
export type { MossDocument, MossMetadata, MossCreds } from './types.js'

// Load environment variables
dotenv.config()

export interface SyncOptions {
  root?: string
  recreate?: boolean
  creds?: {
    projectId: string
    projectKey: string
    indexName: string
    modelName?: string
  }
}

function getMossCreds(providedCreds?: SyncOptions['creds']): MossCreds {
  if (providedCreds) {
    if (!providedCreds.projectId || !providedCreds.projectKey || !providedCreds.indexName) {
      throw new Error('Missing required credentials in options')
    }
    return {
      projectId: providedCreds.projectId,
      projectKey: providedCreds.projectKey,
      indexName: providedCreds.indexName,
      modelName: providedCreds.modelName || 'moss-minilm'
    }
  }

  const projectId = process.env.MOSS_PROJECT_ID
  const projectKey = process.env.MOSS_PROJECT_KEY
  const indexName = process.env.MOSS_INDEX_NAME
  const modelName = process.env.MOSS_MODEL_NAME || 'moss-minilm'

  if (!projectId || !projectKey || !indexName) {
    throw new Error(
      'Missing Environment Variables: MOSS_PROJECT_ID, MOSS_PROJECT_KEY, MOSS_INDEX_NAME. ' +
      'Please add these to your .env file or pass them in the options.'
    )
  }

  return { projectId, projectKey, indexName, modelName }
}

export async function sync(options: SyncOptions = {}) {
  try {
    const cwd = process.cwd()
    const root = options.root || './docs'
    const mdRoot = path.resolve(cwd, root)

    // Fail fast if creds are missing before building
    const creds = getMossCreds(options.creds)

    console.log(pc.cyan(`\nMoss Sync: Starting End-to-End Process`))
    console.log(pc.dim('---------------------------------------'))

    // Step 1: Build (in memory)
    console.log(pc.blue('\nStep 1: Building Index in Memory...'))
    // buildJsonDocs returns documents. We do not pass an outputFile.
    const documents = await buildJsonDocs(mdRoot)

    // Step 2: Upload
    console.log(pc.blue('\nStep 2: Uploading to Moss...'))
    await uploadDocuments(documents, creds, { recreate: options.recreate })

    console.log(pc.green(`\n Sync Successfully Completed!\n`))
    return { success: true, count: documents.length }
  } catch (error: any) {
    console.error(pc.red(`\nFATAL: ${error.message}\n`))
    throw error
  }
}
