import fs from 'fs-extra'
import { MossClient } from "@moss-js/moss";
import type { MossCreds, MossDocument } from './types.js'

/**
 * Deletes an index from Moss cloud if it exists.
 * Silently handles the case where the index doesn't exist.
 */
export async function deleteIndex(creds: MossCreds, client?: MossClient): Promise<void> {
  const mossClient = client || new MossClient(creds.projectId, creds.projectKey);

  try {
    await mossClient.deleteIndex(creds.indexName);
    console.log(`  ✅ Deleted existing index "${creds.indexName}"`);
  } catch (err: any) {
    // If index doesn't exist, that's fine - we'll create it anyway
    const message = String(err?.message ?? '').toLowerCase();
    if (message.includes('not found') || message.includes('does not exist')) {
      console.log(`  ℹ️  Index "${creds.indexName}" does not exist (will be created)`);
    } else {
      // For other errors, log a warning but don't fail
      console.warn(`  ⚠️  Could not delete index "${creds.indexName}": ${err?.message}`);
    }
  } finally {
    // Only close a client this function created
    if (!client) await mossClient.close();
  }
}

export async function uploadDocuments(documents: MossDocument[], creds: MossCreds) {
  console.log(`  Uploading ${documents.length} documents to Moss...`);

  if (documents.length === 0) {
    console.warn('  ⚠️  No documents to upload.');
    return;
  }

  const mossClient = new MossClient(creds.projectId, creds.projectKey);

  try {
    // Always delete the index first before creating a new one
    await deleteIndex(creds, mossClient);

    try {
      const result = await mossClient.createIndex(creds.indexName, documents, {
        modelId: creds.modelName
      });
      console.log(`✅ Upload success! Index "${creds.indexName}" is live.`);
      return result;
    } catch (err: any) {
      const errorMsg = err?.response?.data || err?.message;
      throw new Error(`Moss Upload Failed: ${errorMsg}`);
    }
  } finally {
    await mossClient.close();
  }
}

export async function createIndex(jsonPath: string, creds: MossCreds) {
  if (!fs.existsSync(jsonPath)) {
    throw new Error(`JSON file not found at ${jsonPath}`);
  }

  // Read Data
  const documents: MossDocument[] = await fs.readJSON(jsonPath);
  return uploadDocuments(documents, creds);
}
