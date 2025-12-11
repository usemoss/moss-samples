import { MossClusteringClient } from '@inferedge/moss-clustering';
// @ts-ignore - dotenv types resolved at runtime for examples
import * as dotenv from 'dotenv';

dotenv.config();

/**
 * Moss Clustering SDK - Document Clustering Example
 *
 * Demonstrates how to synchronously cluster documents stored inside a single index
 * and inspect the cached snapshot afterwards.
 */
async function main() {
  const {
    MOSS_PROJECT_ID: projectId,
    MOSS_PROJECT_KEY: projectKey,
    MOSS_DOCUMENT_INDEX,
    MOSS_DOCUMENT_CLUSTER_K
  } = process.env;

  if (!projectId || !projectKey) {
    console.error('❌ Error: Set MOSS_PROJECT_ID and MOSS_PROJECT_KEY in .env file');
    process.exit(1);
  }

  const indexName = (MOSS_DOCUMENT_INDEX ?? 'conversation-964970.0').trim();
  const k = Number(MOSS_DOCUMENT_CLUSTER_K ?? '4');

  const clustering = new MossClusteringClient({ projectId, projectKey });

  console.log('🧩 Moss Document Clustering Example\n');
  console.log(`   Target index: ${indexName}`);
  console.log(`   Cluster count (k): ${k}`);

  const response = await clustering.clusterIndexDocuments(indexName, k, {
    maxDocuments: 500,
    sampleStrategy: 'random',
    representativeDocumentCount: 3
  });

  console.log('\n📈 Progress by phase:');
  response.progress.forEach(step => {
    console.log(`   ${step.phase.padEnd(20)} ${step.progress}%`);
  });

  console.log('\n📚 Cluster summary:');
  response.clusters.forEach(cluster => {
    console.log(`   Cluster ${cluster.clusterId}: ${cluster.label}`);
    console.log(`     Description: ${cluster.description}`);
    console.log(`     Document count: ${cluster.documentCount}`);
    console.log(`     Representative IDs: ${cluster.representativeDocumentIds.join(', ')}`);
  });

  const cached = await clustering.getIndexDocumentClusters(indexName);
  if (cached) {
    console.log('\n🗃️  Cached snapshot metadata:');
    console.log(`   Created: ${cached.createdAt}`);
    console.log(`   Updated: ${cached.updatedAt}`);
    console.log(`   Documents processed: ${cached.documentsProcessed}`);
  } else {
    console.log('\nℹ️  No cached snapshot found. Run clusterIndexDocuments first.');
  }

// Example result:
// 🧩 Moss Document Clustering Example

//    Target index: conversation-964970.0
//    Cluster count (k): 4

// 📈 Progress by phase:
//    Fetching documents   10%
//    Preprocessing documents 30%
//    Generating embeddings 50%
//    Clustering items     70%
//    Extracting labels    80%
//    Saving results       90%
//    Finalizing           95%

// 📚 Cluster summary:
//    Cluster 0: Delivery Window Issues
//      Description: Conversations focused on missed or specified delivery time windows.
//      Document count: 51
//      Representative IDs: conv-964970.0-msg-3, conv-964970.0-msg-8, conv-964970.0-msg-11
//    Cluster 1: Delivery Handling Concerns
//      Description: Issues related to package handling, including delivery without required signatures and parcel tracking.
//      Document count: 104
//      Representative IDs: conv-964970.0-msg-1, conv-964970.0-msg-4, conv-964970.0-msg-5
//    Cluster 2: Damaged Shipment Claims
//      Description: Discussions about approving claims for shipments that arrived damaged.
//      Document count: 26
//      Representative IDs: conv-964970.0-msg-6, conv-964970.0-msg-14, conv-964970.0-msg-22
//    Cluster 3: Signature Protocol Violations
//      Description: Conversations addressing violations of required signature protocols for deliveries.
//      Document count: 26
//      Representative IDs: conv-964970.0-msg-2, conv-964970.0-msg-10, conv-964970.0-msg-18

// 🗃️  Cached snapshot metadata:
//    Created: 2025-12-11T10:00:27.881Z
//    Updated: 2025-12-11T10:00:53.333Z
//    Documents processed: 207
}

main().catch(error => {
  console.error('❌ Fatal Error:', error.message);
  if (error.code) {
    console.error(`   Error Code: ${error.code}`);
  }
  process.exit(1);
});

