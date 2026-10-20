import { MossClient } from '../src';
import { config } from 'dotenv';

// Load environment variables from the samples directory
config();

async function main() {
  console.log('⭐ Moss Index Query Demo ⭐');

  // Initialize search client with project credentials
  const projectId = process.env.MOSS_TEST_PROJECT_ID;
  const projectKey = process.env.MOSS_TEST_PROJECT_KEY;

  if (!projectId || !projectKey) {
    console.error('Please set MOSS_TEST_PROJECT_ID and MOSS_TEST_PROJECT_KEY in .env file');
    console.error('Copy .env.template to .env and fill in your credentials');
    return;
  }

  const mossClient = new MossClient(projectId, projectKey);

  try {
    // List available indexes first
    console.log('Listing available indexes...');
    const indexes = await mossClient.listIndexes();
    console.log(`Found ${indexes.length} indexes:`);
    indexes.forEach(index => {
      console.log(`  - ${index.name}: ${index.docCount} documents`);
    });

    if (indexes.length === 0) {
      console.log('No indexes found. Please create an index first using the example-usage.ts sample.');
      return;
    }

    // Use MOSS_INDEX_NAME env var or fall back to the first available index
    const indexName = process.env.MOSS_INDEX_NAME || indexes[0].name;
    console.log(`\nUsing index: ${indexName}`);

    // Get index information
    const indexInfo = await mossClient.getIndex(indexName);
    console.log(`Index details: ${indexInfo.docCount} documents, model: ${indexInfo.model.id}`);

    // Search the index
    const query = "How do we use cloudflare?";
    console.log(`\nSearching for: "${query}"`);

    await mossClient.loadIndex(indexName); // Ensure index is loaded before querying
    const result = await mossClient.query(indexName, query, { topK: 5 });

    console.log(`\nTotal matches found: ${result.docs.length}`);
    console.log(`Query: ${result.query}`);
    console.log('---');

    // Display results
    result.docs.forEach((match, index) => {
      console.log(`#${index + 1} - Score: ${match.score.toFixed(4)}`);
      console.log(`ID: ${match.id}`);
      console.log(`Text: ${match.text.substring(0, 150)}${match.text.length > 150 ? '...' : ''}`);
      console.log('---');
    });

  } catch (error) {
    console.error('Error occurred:', error instanceof Error ? error.message : String(error));
  } finally {
    await mossClient.close();
  }
}

main().catch(console.error);