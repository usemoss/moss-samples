import fs from 'fs-extra'
import { MossClient } from "@moss-dev/moss";
import type { MossCreds, MossDocument } from './types.js'

/**
 * Deletes an index from Moss cloud if it exists.
 * Silently handles the case where the index doesn't exist.
 */
export async function deleteIndex(creds: MossCreds, client?: MossClient): Promise<void> {
  const owned = !client;
  const mossClient = client || new MossClient(creds.projectId, creds.projectKey);

  try {
    await mossClient.deleteIndex(creds.indexName);
    console.log(`  ✅ Deleted existing index "${creds.indexName}"`);
  } catch (err: any) {
    if (err.message?.includes('not found') || err.message?.includes('does not exist')) {
      console.log(`  ℹ️  Index "${creds.indexName}" does not exist (will be created)`);
    } else {
      console.warn(`  ⚠️  Could not delete index "${creds.indexName}": ${err.message}`);
    }
  } finally {
    if (owned) await mossClient.close();
  }
}

export interface UploadOptions {
  /**
   * Force recreate the index from scratch (legacy behavior).
   * When false (default), uses non-destructive upsert.
   */
  recreate?: boolean;
}

export async function uploadDocuments(
  documents: MossDocument[],
  creds: MossCreds,
  options?: UploadOptions
) {
  console.log(`  Uploading ${documents.length} documents to Moss...`);

  if (documents.length === 0) {
    console.warn('  ⚠️  No documents to upload.');
    return;
  }

  const mossClient = new MossClient(creds.projectId, creds.projectKey);

  try {
    // Force recreate: delete then create (legacy behavior)
    if (options?.recreate) {
      await deleteIndex(creds, mossClient);
      try {
        const result = await mossClient.createIndex(creds.indexName, documents, {
          modelId: creds.modelName
        });
        console.log(`✅ Upload success! Index "${creds.indexName}" is live.`);
        return result;
      } catch (err: any) {
        const errorMsg = err.response?.data || err.message;
        throw new Error(`Moss Upload Failed: ${errorMsg}`);
      }
    }

    // Non-destructive upsert (default): preserve live index during rebuild
    // Check if index exists - this runs outside the upload error wrapper
    // so auth/network errors propagate with their original type
    let indexInfo: { name: string; model?: { id?: string | null; version?: string | null }; version?: string | null } | null = null;
    try {
      indexInfo = await mossClient.getIndex(creds.indexName);
    } catch (err: any) {
      const msg = String(err?.message ?? '').toLowerCase();
      if (!msg.includes('not found') && !msg.includes('does not exist')) {
        throw err;
      }
      // Index doesn't exist - we'll create it below
    }

    if (!indexInfo) {
      try {
        const result = await mossClient.createIndex(creds.indexName, documents, {
          modelId: creds.modelName
        });
        console.log(`✅ Created new index "${creds.indexName}" with ${documents.length} documents.`);
        return result;
      } catch (err: any) {
        const errorMsg = err.response?.data || err.message;
        throw new Error(`Moss Upload Failed: ${errorMsg}`);
      }
    }

    // Index exists - check model compatibility
    // Legacy indexes (built by old SDK) have no model artifact version
    // and won't work with text queries in the new SDK - auto-recreate
    const indexModel = indexInfo.model?.id;
    const modelVersion = indexInfo.model?.version;
    const isLegacy = !modelVersion;
    const isModelMismatch = indexModel && indexModel !== creds.modelName;

    if (isLegacy) {
      throw new Error(
        `Index "${creds.indexName}" was built by an older SDK version ` +
        `and does not support text queries. ` +
        `Re-run with { recreate: true } to rebuild with the current SDK.`
      );
    }

    if (isModelMismatch) {
      throw new Error(
        `Index "${creds.indexName}" was built with model "${indexModel}" ` +
        `but you're using "${creds.modelName}". ` +
        `Re-run with { recreate: true } to rebuild with the correct model.`
      );
    }

    // Index exists: upsert new docs and delete stale ones
    const newIds = new Set(documents.map(d => d.id));
    const existingDocs = await mossClient.getDocs(creds.indexName);
    const existingIds = existingDocs.map(d => d.id);

    const result = await mossClient.addDocs(creds.indexName, documents, { upsert: true });

    const staleIds = existingIds.filter(id => !newIds.has(id));
    if (staleIds.length > 0) {
      await mossClient.deleteDocs(creds.indexName, staleIds);
      console.log(`  🗑️  Removed ${staleIds.length} stale documents`);
    }

    console.log(`✅ Upserted ${documents.length} documents to index "${creds.indexName}".`);
    return result;
  } finally {
    await mossClient.close();
  }
}

export async function createIndex(jsonPath: string, creds: MossCreds, options?: UploadOptions) {
  if (!fs.existsSync(jsonPath)) {
    throw new Error(`JSON file not found at ${jsonPath}`);
  }

  const documents: MossDocument[] = await fs.readJSON(jsonPath);
  return uploadDocuments(documents, creds, options);
}
