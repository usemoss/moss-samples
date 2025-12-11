import { MossClient } from '@inferedge/moss';
import { MossClusteringClient } from '@inferedge/moss-clustering';
import * as dotenv from 'dotenv';

dotenv.config();

/**
 * Moss Clustering SDK - Subset Example
 *
 * Mirrors the complete example workflow but scopes clustering to a subset of indexes.
 */
async function main() {
  const {
    MOSS_PROJECT_ID: projectId,
    MOSS_PROJECT_KEY: projectKey,
    MOSS_INDEX_SET
  } = process.env;

  if (!projectId || !projectKey) {
    console.error('❌ Error: Set MOSS_PROJECT_ID and MOSS_PROJECT_KEY in .env file');
    process.exit(1);
  }

  const indexNames = MOSS_INDEX_SET
    ? MOSS_INDEX_SET.split(',').map(name => name.trim()).filter(Boolean)
    : ['support-tickets', 'billing-2024'];

  const moss = new MossClient(projectId, projectKey);
  const clustering = new MossClusteringClient({ projectId, projectKey });

  console.log('🚀 Moss Clustering SDK Example — Index Subset\n');

  // ============================================================================
  // METHOD 1: Manual Job Management (Full Control)
  // ============================================================================
  console.log('� Method 1: Manual Job Management with Progress Tracking\n');
  console.log(`🎯 Index subset: ${indexNames.join(', ')}`);
  console.log('   Set MOSS_INDEX_SET (comma-separated) to change the target indexes.\n');

  // Check if clustering already exists
  if (await clustering.hasActiveClustering()) {
    console.log('ℹ️  Clustering already exists. Deleting for demo...\n');
    await clustering.deleteClustering();
  }

  // Start cluster generation for the subset
  const jobResponse = await clustering.startClusterGeneration(5, { indexNames });
  console.log(`✅ Job started: ${jobResponse.jobId}`);
  console.log(`   Status: ${jobResponse.status}`);
  console.log(`   Index subset: ${indexNames.join(', ')}\n`);

  // Poll for completion with progress updates
  console.log('⏳ Polling for completion...\n');
  let lastProgress = -1;

  while (true) {
    const { job } = await clustering.getJobStatus(jobResponse.jobId);

    // Show progress when it changes
    if (job.progress !== lastProgress) {
      const phase = job.currentPhase || job.status;
      console.log(`   [${job.progress}%] ${phase}`);
      lastProgress = job.progress;
    }

    if (job.status === 'completed') {
      console.log('\n✅ Job completed!\n');
      if (job.result) {
        console.log(`📊 Results: ${job.result.clusters.length} clusters from ${job.result.totalIndexes} indexes`);
        const processed = job.result.processedIndexes ?? [];
        if (processed.length > 0) {
          console.log(`   Processed indexes: ${processed.join(', ')}`);
        }
      }
      break;
    }

    if (job.status === 'failed') {
      console.error(`❌ Job failed: ${job.error}\n`);
      process.exit(1);
    }

    await new Promise(r => setTimeout(r, 7000)); // Poll every 7 seconds
  }

  // ============================================================================
  // View Cluster Information
  // ============================================================================
  console.log('📁 Cluster Information:\n');

  const clusters = await clustering.getClusters();
  clusters.forEach((cluster, i) => {
    console.log(`${i + 1}. ${cluster.label} (${cluster.indexCount} indexes)`);
    console.log(`   Description: ${cluster.description || 'N/A'}`);
    if (cluster.indexes.length > 0) {
      const preview = cluster.indexes.slice(0, 3).join(', ');
      const more = cluster.indexes.length > 3 ? `, +${cluster.indexes.length - 3} more` : '';
      console.log(`   Indexes: ${preview}${more}`);
    }
    console.log();
  });
}

// Run the example
main().catch(error => {
  console.error('❌ Fatal Error:', error.message);
  if ((error as any)?.code) {
    console.error(`   Error Code: ${(error as any).code}`);
  }
  process.exit(1);
});
