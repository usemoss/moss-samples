/**
 * Example usage of the Moss JavaScript SDK
 *
 * This example demonstrates the complete workflow.
 */

import { MossClient, DocumentInfo } from "../src/index";
import { config } from 'dotenv';

// Load environment variables
config();

async function exampleUsage() {
  console.log('⭐ Moss API Complete Example ⭐');

  // Initialize client with project credentials from environment
  const projectId = process.env.MOSS_TEST_PROJECT_ID;
  const projectKey = process.env.MOSS_TEST_PROJECT_KEY;

  if (!projectId || !projectKey) {
    console.error('Please set MOSS_TEST_PROJECT_ID and MOSS_TEST_PROJECT_KEY in .env file');
    console.error('Copy .env.template to .env and fill in your credentials');
    return;
  }

  const client = new MossClient(projectId, projectKey);

  // Example documents following the API contract
  const documents: DocumentInfo[] = [
    {
      id: 'doc1',
      text: 'Machine learning is a subset of artificial intelligence that enables computers to learn and improve from experience without being explicitly programmed.'
    },
    {
      id: 'doc2',
      text: 'Deep learning uses neural networks with multiple layers to model and understand complex patterns in data.'
    },
    {
      id: 'doc3',
      text: 'Natural language processing enables computers to interpret and manipulate human language for various applications.'
    },
    {
      id: 'doc4',
      text: 'Computer vision enables machines to interpret and understand visual information from the world around them.'
    },
    {
      id: 'doc5',
      text: 'Reinforcement learning is a type of machine learning where an agent learns to make decisions by performing actions and receiving rewards.'
    }
  ];

  const indexName = `example-cloud-index-${Date.now()}`;

  try {
    console.log('1. Creating index with documents...');
    const created = await client.createIndex(indexName, documents, { modelId: "moss-minilm" });
    console.log('✅ Index created:', created);

    console.log('\n2. Getting index information...');
    const indexInfo = await client.getIndex(indexName);
    console.log('✅ Index info:', {
      name: indexInfo.name,
      docCount: indexInfo.docCount,
      model: indexInfo.model.id,
      status: indexInfo.status
    });

    console.log('\n3. Listing all indexes...');
    const indexes = await client.listIndexes();
    console.log('✅ All indexes:', indexes.map(idx => ({
      name: idx.name,
      docCount: idx.docCount,
      status: idx.status
    })));

    console.log('\n4. Adding more documents...');
    const newDocs: DocumentInfo[] = [
      {
        id: 'doc6',
        text: 'Data science combines statistics, programming, and domain expertise to extract insights from data.'
      },
      {
        id: 'doc7',
        text: 'Cloud computing provides on-demand access to computing resources over the internet.'
      }
    ];
    const addResult = await client.addDocs(indexName, newDocs, { upsert: true });
    console.log('✅ Documents added:', addResult);

    console.log('\n5. Getting all documents...');
    const allDocs = await client.getDocs(indexName);
    console.log('✅ Total documents:', allDocs.length);

    console.log('\n6. Getting specific documents...');
    const specificDocs = await client.getDocs(indexName, {
      docIds: ['doc1', 'doc2', 'doc6']
    });
    console.log('✅ Specific documents:', specificDocs.map(doc => ({ id: doc.id, text: doc.text.substring(0, 50) + '...' })));

    console.log('\n7. Performing semantic search...');
    const searchResults = await client.query(
      indexName,
      'artificial intelligence and neural networks',
      { topK: 3 }
    );

    console.log('✅ Search results:');
    console.log(`Query: "${searchResults.query}"`);
    console.log(`Found ${searchResults.docs.length} results`);

    searchResults.docs.forEach((item, index) => {
      console.log(`${index + 1}. [${item.id}] Score: ${item.score.toFixed(3)}`);
      console.log(`   Text: ${item.text.substring(0, 80)}${item.text.length > 80 ? '...' : ''}`);
    });

    console.log('\n8. Deleting some documents...');
    const deleteResult = await client.deleteDocs(indexName, ['doc6', 'doc7']);
    console.log('✅ Documents deleted:', deleteResult.docCount);

    console.log('\n9. Verifying document count after deletion...');
    const remainingDocs = await client.getDocs(indexName);
    console.log('✅ Remaining documents:', remainingDocs.length);

    console.log('\n10. Loading index ...');
    const loadedIndex = await client.loadIndex(indexName);
    console.log('✅ Loaded index:', loadedIndex);

    console.log('\n11. Final search to verify everything works...');
    const finalResults = await client.query(
      indexName,
      'machine learning algorithms',
      { topK: 2 }
    );

    console.log('✅ Final search results:');
    finalResults.docs.forEach((item, index) => {
      console.log(`${index + 1}. [${item.id}] Score: ${item.score.toFixed(3)}`);
    });

    console.log('\n12. Cleaning up - deleting the test index...');
    // const deleted = await client.deleteIndex(indexName);
    // console.log('✅ Index deleted:', deleted);

    console.log('\n🎉 All operations completed successfully!');

  } catch (error) {
    console.error('❌ Error:', error);
    if (error instanceof Error) {
      console.error('Error message:', error.message);
    }
  } finally {
    await client.close();
  }
}

// Export for use in tests or other modules
export { exampleUsage };

// Run the example
exampleUsage().catch(console.error);