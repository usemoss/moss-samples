/**
 * Simple Moss SDK Load Index and Query Sample
 * 
 * This sample shows how to load an existing FAQ index and perform search queries.
 * Includes sample returns-related questions for demonstration.
 * 
 * Required Environment Variables:
 * - MOSS_PROJECT_ID: Your Moss project ID  
 * - MOSS_PROJECT_KEY: Your Moss project key
 * - MOSS_INDEX_NAME: Name of existing FAQ index to query
 */

import { MossClient } from "@inferedge/moss";
import { config } from 'dotenv';

// Load environment variables
config();

/**
 * Simple sample showing how to load an existing index and perform queries.
 */
async function loadAndQuerySample(): Promise<void> {
  console.log('Moss SDK - Load Index & Query Sample');

  // Load configuration from environment variables
  const projectId = process.env.MOSS_PROJECT_ID;
  const projectKey = process.env.MOSS_PROJECT_KEY;
  const indexName = process.env.MOSS_INDEX_NAME;

  // Validate required environment variables
  if (!projectId || !projectKey || !indexName) {
    console.error('Error: Missing required environment variables!');
    console.error('Please set MOSS_PROJECT_ID, MOSS_PROJECT_KEY, and MOSS_INDEX_NAME in .env file');
    return;
  }

  console.log(`Using index: ${indexName}`);

  // Initialize Moss client
  const client = new MossClient(projectId, projectKey);

  try {
    // Load the index for querying
    console.log(`\nLoading index...`);
    await client.loadIndex(indexName);
    console.log(`Index loaded successfully`);

    // Perform sample searches
    console.log(`\nPerforming sample searches...`);
    
    const queries = [
      'how to return damaged item',
      'return shipping label process', 
      'refund processing time and policy'
    ];

    for (let i = 0; i < queries.length; i++) {
      const query = queries[i];
      console.log(`\nQuery ${i + 1}: '${query}'`);
      try {
  const results = await client.query(indexName, query, { topK: 3 });
        console.log(`Found ${results.docs.length} results in ${results.timeTakenInMs}ms`);
        
        results.docs.forEach((result, j) => {
          const preview = result.text.length > 80 ? result.text.substring(0, 80) + '...' : result.text;
          console.log(`  ${j + 1}. [${result.id}] Score: ${result.score.toFixed(3)}`);
          console.log(`     ${preview}`);
        });
        
      } catch (e) {
        console.log(`  Query failed: ${String(e)}`);
      }
    }

    console.log(`\nSample completed successfully!`);

  } catch (error) {
    console.error(`Error: ${error}`);
  }
}

// Run the example if this file is executed directly
if (require.main === module) {
  loadAndQuerySample().catch(console.error);
}