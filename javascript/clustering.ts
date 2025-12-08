import { MossClient } from '@inferedge/moss';
import { MossClusteringClient } from '@inferedge/moss-clustering';
import * as dotenv from 'dotenv';

dotenv.config();

/**
 * Moss Clustering SDK - Complete Example
 * 
 * Demonstrates all key features:
 * - Environment configuration
 * - Cluster generation (3 methods)
 * - Progress tracking
 * - Job management
 * - Querying clusters
 */

async function main() {
  // Load credentials from .env
  const { MOSS_PROJECT_ID: projectId, MOSS_PROJECT_KEY: projectKey } = process.env;
  
  if (!projectId || !projectKey) {
    console.error('❌ Error: Set MOSS_PROJECT_ID and MOSS_PROJECT_KEY in .env file');
    process.exit(1);
  }
  
  const moss = new MossClient(projectId, projectKey);
  const clustering = new MossClusteringClient({ projectId, projectKey });
  
  console.log('🚀 Moss Clustering SDK Example\n');
  
  // ============================================================================
  // METHOD 1: Manual Job Management (Full Control)
  // ============================================================================
  console.log('📊 Method 1: Manual Job Management with Progress Tracking\n');
  
  // Check if clustering already exists
  if (await clustering.hasActiveClustering()) {
    console.log('ℹ️  Clustering already exists. Deleting for demo...\n');
    await clustering.deleteClustering();
  }
  
  // Start cluster generation
  const jobResponse = await clustering.startClusterGeneration(5);
  console.log(`✅ Job started: ${jobResponse.jobId}`);
  console.log(`   Status: ${jobResponse.status}\n`);
  
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
        console.log(`📊 Results: ${job.result.clusters.length} clusters from ${job.result.totalIndexes} indexes\n`);
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
  
//   // ============================================================================
//   // METHOD 2: Helper Method for Polling
//   // ============================================================================
//   console.log('� Method 2: Using Helper Method\n');
//   console.log('Use waitForJobCompletion() to automatically poll:\n');
//   console.log('```typescript');
//   console.log('const result = await clustering.waitForJobCompletion(jobId, 2000);');
//   console.log('```\n');
  
//   // ============================================================================
//   // METHOD 3: Convenience Method (Simplest)
//   // ============================================================================
//   console.log('💡 Method 3: Convenience Method (Simplest)\n');
//   console.log('For simplest usage, use generateClusters() which handles everything:\n');
//   console.log('```typescript');
//   console.log('const result = await clustering.generateClusters(5);');
//   console.log('console.log(`Created ${result.clusters.length} clusters`);');
//   console.log('```\n');
  
//   // ============================================================================
//   // Summary
//   // ============================================================================
//   console.log('✅ Example Complete!\n');
//   console.log('Key Takeaways:');
//   console.log('  • Use .env file for credentials (never commit!)');
//   console.log('  • Method 1 (startClusterGeneration) for full control & progress');
//   console.log('  • Method 2 (waitForJobCompletion) for automatic polling');
//   console.log('  • Method 3 (generateClusters) for simplicity');
//   console.log('  • Poll every 2 seconds for good balance');
//   console.log('  • Always handle job failures\n');
}

// Run the example
main().catch(error => {
  console.error('❌ Fatal Error:', error.message);
  if (error.code) {
    console.error(`   Error Code: ${error.code}`);
  }
  process.exit(1);
});
