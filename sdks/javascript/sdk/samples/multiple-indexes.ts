import { MossClient } from '../src';
import { config } from 'dotenv';
// Load environment variables from the samples directory
config();

async function main() {
  console.log('⭐ Multiple Indexes Demo ⭐');

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
    // List all available indexes
    console.log('Listing all available indexes...');
    const indexes = await mossClient.listIndexes();
    console.log(`Found ${indexes.length} indexes:`);
    indexes.forEach(index => {
      console.log(`  - ${index.name}: ${index.docCount} documents`);
    });

    if (indexes.length === 0) {
      console.log('No indexes found. Please create indexes first using the example-usage.ts sample.');
      return;
    }

    // Search multiple indexes with the same query
    const query = "wireless bluetooth devices";
    console.log(`\nSearching for: "${query}" across all indexes:`);

    // Search each index and collect results
    const allResults: Array<{ indexName: string; id: string; text: string; score: number }> = [];
    for (const index of indexes) {
      try {
        console.log(`\nSearching in ${index.name}...`);
  const results = await mossClient.query(index.name, query, { topK: 3 });
        console.log(`Found ${results.docs.length} matches in ${index.name}`);

        // Add index name to each result for clarity
        results.docs.forEach(doc => {
          allResults.push({
            indexName: index.name,
            id: doc.id,
            text: doc.text,
            score: doc.score
          });
        });
      } catch (error) {
        console.warn(`Error searching ${index.name}:`, error instanceof Error ? error.message : String(error));
      }
    }

    // Sort all results by score and display top results
    allResults.sort((a, b) => b.score - a.score);
    const topResults = allResults.slice(0, 5);

    console.log(`\nTop ${topResults.length} results across all indexes:`);
    topResults.forEach((result, index) => {
      console.log(`#${index + 1} - Score: ${result.score.toFixed(4)} [${result.indexName}]`);
      console.log(`ID: ${result.id}`);
      console.log(`Text: ${result.text.substring(0, 100)}${result.text.length > 100 ? '...' : ''}`);
      console.log('---');
    });

    // Demonstrate different search query
    const secondQuery = "product return policy";
    console.log(`\nSearching for: "${secondQuery}" across all indexes:`);

    const secondResults: Array<{ indexName: string; id: string; text: string; score: number }> = [];
    for (const index of indexes) {
      try {
  const results = await mossClient.query(index.name, secondQuery, { topK: 2 });
        results.docs.forEach(doc => {
          secondResults.push({
            indexName: index.name,
            id: doc.id,
            text: doc.text,
            score: doc.score
          });
        });
      } catch (error) {
        console.warn(`Error searching ${index.name}:`, error instanceof Error ? error.message : String(error));
      }
    }

    // Sort and display second query results
    secondResults.sort((a, b) => b.score - a.score);
    const topSecondResults = secondResults.slice(0, 4);

    topSecondResults.forEach((result, index) => {
      console.log(`#${index + 1} - Score: ${result.score.toFixed(4)} [${result.indexName}]`);
      console.log(`ID: ${result.id}`);
      console.log(`Text: ${result.text.substring(0, 100)}${result.text.length > 100 ? '...' : ''}`);
      console.log('---');
    });

  } catch (error) {
    console.error('Error occurred:', error instanceof Error ? error.message : String(error));
  } finally {
    await mossClient.close();
  }
}

main().catch(console.error);
