/**
 * @fileoverview Comprehensive End-to-End Moss JavaScript SDK Sample
 * @description This example demonstrates the complete workflow of the Moss JavaScript SDK,
 * showcasing ALL available functions with a dynamic index name based on timestamp.
 * 
 * Features demonstrated:
 * - Index creation and management
 * - Document operations (add, retrieve, update, delete)
 * - Semantic search functionality
 * - Advanced querying with metadata filtering
 * - Index lifecycle management
 * - Error handling best practices
 * 
 * @author Moss SDK Examples
 * @version 1.0.0
 * @since 2024-10-09
 * 
 * @example
 * ```bash
 * # Run this comprehensive example
 * npx tsx comprehensive_sample.ts
 * ```
 * 
 * @requires @inferedge/moss ^1.0.0-beta.1
 * @requires dotenv ^17.2.3
 * @requires node >=16.0.0
 */

import { MossClient, DocumentInfo, AddDocumentsOptions, GetDocumentsOptions } from "@inferedge/moss";
import { config } from 'dotenv';

// Load environment variables
config();

/**
 * Comprehensive end-to-end example demonstrating ALL Moss SDK functionality.
 * 
 * This function covers:
 * 1. Client initialization with environment variables
 * 2. Index creation with initial documents
 * 3. Index information retrieval
 * 4. Index listing
 * 5. Document addition with upsert
 * 6. Document retrieval (all and specific)
 * 7. Index loading for querying
 * 8. Multiple semantic search operations
 * 9. Document deletion
 * 10. Index cleanup
 * 11. Comprehensive error handling
 */
async function comprehensiveMossExample(): Promise<void> {
  console.log('Comprehensive Moss SDK End-to-End Sample');
  console.log('='.repeat(50));

  // Initialize client with project credentials from environment
  const projectId = process.env.MOSS_PROJECT_ID;
  const projectKey = process.env.MOSS_PROJECT_KEY;

  if (!projectId || !projectKey) {
    console.error('Error: Missing environment variables!');
    console.error('Please set MOSS_PROJECT_ID and MOSS_PROJECT_KEY in .env file');
    console.error('Copy .env.template to .env and fill in your credentials');
    return;
  }

  const client = new MossClient(projectId, projectKey);

  // Create comprehensive document collection with rich metadata
  const documents: DocumentInfo[] = [
    {
      id: 'tech-ai-001',
      text: 'Artificial Intelligence (AI) is transforming industries by enabling machines to perform tasks that typically require human intelligence. From healthcare diagnostics to autonomous vehicles, AI applications are revolutionizing how we work and live.',
      metadata: {
        category: 'technology',
        subcategory: 'artificial_intelligence',
        difficulty: 'beginner',
        topic: 'ai_overview',
        author: 'Tech Research Team',
        tags: 'ai,technology,automation,machine_learning',
        word_count: '42',
        reading_time: '1 minute',
        published_date: '2024-01-15',
        language: 'en'
      }
    },
    {
      id: 'tech-ml-002',
      text: 'Machine Learning is a subset of AI that enables systems to automatically learn and improve from experience without being explicitly programmed. It uses algorithms to analyze data, identify patterns, and make predictions or decisions.',
      metadata: {
        category: 'technology',
        subcategory: 'machine_learning',
        difficulty: 'intermediate',
        topic: 'ml_fundamentals',
        author: 'ML Engineering Team',
        tags: 'machine_learning,algorithms,data_science,predictions',
        word_count: '38',
        reading_time: '1 minute',
        published_date: '2024-01-20',
        language: 'en'
      }
    },
    {
      id: 'tech-dl-003',
      text: 'Deep Learning uses artificial neural networks with multiple layers to model and understand complex patterns in data. It has achieved breakthrough results in image recognition, natural language processing, and game playing.',
      metadata: {
        category: 'technology',
        subcategory: 'deep_learning',
        difficulty: 'advanced',
        topic: 'neural_networks',
        author: 'Deep Learning Lab',
        tags: 'deep_learning,neural_networks,image_recognition,nlp',
        word_count: '35',
        reading_time: '1 minute',
        published_date: '2024-01-25',
        language: 'en'
      }
    },
    {
      id: 'tech-nlp-004',
      text: 'Natural Language Processing (NLP) enables computers to understand, interpret, and generate human language. Applications include chatbots, language translation, sentiment analysis, and text summarization.',
      metadata: {
        category: 'technology',
        subcategory: 'natural_language_processing',
        difficulty: 'intermediate',
        topic: 'language_processing',
        author: 'NLP Research Group',
        tags: 'nlp,language,chatbots,translation,sentiment_analysis',
        word_count: '31',
        reading_time: '1 minute',
        published_date: '2024-02-01',
        language: 'en'
      }
    },
    {
      id: 'tech-cv-005',
      text: 'Computer Vision allows machines to interpret and understand visual information from the world. It powers applications like facial recognition, medical image analysis, autonomous driving, and quality control in manufacturing.',
      metadata: {
        category: 'technology',
        subcategory: 'computer_vision',
        difficulty: 'intermediate',
        topic: 'visual_recognition',
        author: 'Computer Vision Team',
        tags: 'computer_vision,image_processing,facial_recognition,autonomous_driving',
        word_count: '33',
        reading_time: '1 minute',
        published_date: '2024-02-05',
        language: 'en'
      }
    },
    {
      id: 'business-data-006',
      text: 'Data Science combines statistics, programming, and domain expertise to extract actionable insights from data. It involves data collection, cleaning, analysis, and visualization to support business decision-making.',
      metadata: {
        category: 'business',
        subcategory: 'data_science',
        difficulty: 'intermediate',
        topic: 'analytics',
        author: 'Data Analytics Team',
        tags: 'data_science,statistics,analytics,business_intelligence',
        word_count: '32',
        reading_time: '1 minute',
        published_date: '2024-02-10',
        language: 'en'
      }
    },
    {
      id: 'business-cloud-007',
      text: 'Cloud Computing provides on-demand access to computing resources over the internet, including servers, storage, databases, and software. It offers scalability, cost-efficiency, and global accessibility for businesses.',
      metadata: {
        category: 'business',
        subcategory: 'cloud_computing',
        difficulty: 'beginner',
        topic: 'infrastructure',
        author: 'Cloud Architecture Team',
        tags: 'cloud_computing,infrastructure,scalability,saas',
        word_count: '30',
        reading_time: '1 minute',
        published_date: '2024-02-15',
        language: 'en'
      }
    }
  ];

  // Create dynamic index name with timestamp
  const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
  const indexName = `comprehensive-demo-${timestamp}`;

  try {
    console.log(`\n📝 Step 1: Creating index '${indexName}' with ${documents.length} documents...`);
    const created = await client.createIndex(indexName, documents, 'moss-minilm');
    console.log(`Index created successfully: ${created}`);

    console.log(`\nStep 2: Retrieving index information...`);
    const indexInfo = await client.getIndex(indexName);
    console.log(`Index Details:`);
    console.log(`   • Name: ${indexInfo.name}`);
    console.log(`   • Document Count: ${indexInfo.docCount}`);
    console.log(`   • Model: ${indexInfo.model.id}`);
    console.log(`   • Status: ${indexInfo.status}`);

    console.log(`\nStep 3: Listing all available indexes...`);
    const indexes = await client.listIndexes();
    console.log(`Found ${indexes.length} total indexes:`);
    indexes.forEach(idx => {
      console.log(`   ${idx.name}: ${idx.docCount} docs, status: ${idx.status}`);
    });

    console.log(`\nStep 4: Adding additional documents with upsert...`);
    const additionalDocs: DocumentInfo[] = [
      {
        id: 'security-cyber-008',
        text: 'Cybersecurity protects digital systems, networks, and data from cyber threats. It involves implementing security measures, monitoring for vulnerabilities, and responding to incidents to maintain data integrity and privacy.',
        metadata: {
          category: 'security',
          subcategory: 'cybersecurity',
          difficulty: 'intermediate',
          topic: 'digital_security',
          author: 'Security Team',
          tags: 'cybersecurity,data_protection,privacy,threats',
          word_count: '34',
          reading_time: '1 minute',
          published_date: '2024-02-20',
          language: 'en'
        }
      },
      {
        id: 'health-biotech-009',
        text: 'Biotechnology applies biological processes and organisms to develop products and technologies that improve human health and the environment. It includes genetic engineering, drug development, and personalized medicine.',
        metadata: {
          category: 'healthcare',
          subcategory: 'biotechnology',
          difficulty: 'advanced',
          topic: 'medical_innovation',
          author: 'Biotech Research Lab',
          tags: 'biotechnology,genetic_engineering,drug_development,personalized_medicine',
          word_count: '33',
          reading_time: '1 minute',
          published_date: '2024-02-25',
          language: 'en'
        }
      },
      {
        id: 'env-sustainability-010',
        text: 'Sustainable Technology focuses on developing solutions that meet present needs without compromising future generations. It includes renewable energy, green computing, and environmentally friendly manufacturing processes.',
        metadata: {
          category: 'environment',
          subcategory: 'sustainability',
          difficulty: 'intermediate',
          topic: 'green_technology',
          author: 'Sustainability Team',
          tags: 'sustainability,renewable_energy,green_computing,environment',
          word_count: '31',
          reading_time: '1 minute',
          published_date: '2024-03-01',
          language: 'en'
        }
      }
    ];

    const addResult = await client.addDocs(indexName, additionalDocs, { upsert: true } as AddDocumentsOptions);
    console.log(`Added ${additionalDocs.length} additional documents: ${addResult}`);

    console.log(`\nStep 5: Retrieving all documents from index...`);
    const allDocs = await client.getDocs(indexName);
    console.log(`Total documents in index: ${allDocs.length}`);

    // Display sample of documents with metadata
    console.log(`Sample documents preview:`);
    allDocs.slice(0, 3).forEach((doc, i) => {
      const textPreview = doc.text.length > 80 ? doc.text.substring(0, 80) + '...' : doc.text;
      console.log(`   ${i + 1}. [${doc.id}] ${textPreview}`);
      if (doc.metadata) {
        console.log(`      Category: ${doc.metadata.category} | Difficulty: ${doc.metadata.difficulty}`);
      }
    });

    console.log(`\nStep 6: Retrieving specific documents by ID...`);
    const targetDocIds = ['tech-ai-001', 'business-data-006', 'security-cyber-008'];
    const specificDocs = await client.getDocs(indexName, {
      docIds: targetDocIds
    } as GetDocumentsOptions);
    console.log(`Retrieved ${specificDocs.length} specific documents:`);
    specificDocs.forEach(doc => {
      const textPreview = doc.text.length > 60 ? doc.text.substring(0, 60) + '...' : doc.text;
      console.log(`   • [${doc.id}] ${textPreview}`);
      if (doc.metadata && doc.metadata.tags) {
        const tags = doc.metadata.tags.split(',').slice(0, 3).join(', ');
        console.log(`     🏷️  Tags: ${tags}${doc.metadata.tags.split(',').length > 3 ? '...' : ''}`);
      }
    });

    console.log(`\nStep 7: Loading index for semantic search operations...`);
    const loadedIndex = await client.loadIndex(indexName);
    console.log(`Index loaded for querying: ${loadedIndex}`);

    console.log(`\n🔎 Step 8: Performing comprehensive semantic search tests...`);
    const searchQueries = [
      { query: 'artificial intelligence and machine learning', topK: 4 },
      { query: 'data analysis and business insights', topK: 3 },
      { query: 'visual recognition and image processing', topK: 3 },
      { query: 'cybersecurity and data protection', topK: 2 },
      { query: 'healthcare innovation and biotechnology', topK: 2 },
      { query: 'sustainable technology and environment', topK: 2 }
    ];

    for (let i = 0; i < searchQueries.length; i++) {
      const { query, topK } = searchQueries[i];
      console.log(`\n   Search ${i + 1}: "${query}"`);

      const searchResults = await client.query(indexName, query, { topK });

      console.log(`   ⏱️  Time taken: ${searchResults.timeTakenInMs} ms`);
      console.log(`   Found ${searchResults.docs.length} results:`);

      searchResults.docs.forEach((result, j) => {
        const textPreview = result.text.length > 70 ? result.text.substring(0, 70) + '...' : result.text;
        console.log(`      ${j + 1}. [${result.id}] Score: ${result.score.toFixed(3)}`);
        console.log(`         ${textPreview}`);
        if (result.metadata) {
          console.log(`         ${result.metadata.category} | ${result.metadata.topic}`);
        }
      });
    }

    console.log(`\n🗑️  Step 9: Demonstrating document deletion...`);
    const docsToDelete = ['health-biotech-009', 'env-sustainability-010'];
    const deleteResult = await client.deleteDocs(indexName, docsToDelete);
    console.log(`Delete operation result: ${JSON.stringify(deleteResult)}`);

    console.log(`\nStep 10: Verifying document count after deletion...`);
    const remainingDocs = await client.getDocs(indexName);
    console.log(`Remaining documents: ${remainingDocs.length}`);

    console.log(`\nStep 11: Final search validation...`);
    const finalSearch = await client.query(
      indexName,
      'technology innovation and automation',
      { topK: 5 }
    );

    console.log(`Final search results:`);
    console.log(`   Query: "${finalSearch.query}"`);
    console.log(`   Time: ${finalSearch.timeTakenInMs} ms`);
    console.log(`   Results: ${finalSearch.docs.length}`);

    finalSearch.docs.forEach((item, i) => {
      console.log(`   ${i + 1}. [${item.id}] Score: ${item.score.toFixed(3)}`);
    });

    console.log(`\nStep 12: Cleaning up - deleting the test index...`);
    const deleted = await client.deleteIndex(indexName);
    console.log(`Index deleted: ${deleted}`);

    console.log(`\nComprehensive Moss SDK Example Completed Successfully!`);
    console.log('='.repeat(60));
    console.log('Summary of operations performed:');
    console.log('   Index creation with initial documents');
    console.log('   Index information retrieval');
    console.log('   Index listing');
    console.log('   Document addition with upsert');
    console.log('   Document retrieval (all and specific)');
    console.log('   Index loading for querying');
    console.log('   Multiple semantic search operations');
    console.log('   Document deletion');
    console.log('   Index cleanup');
    console.log('   Comprehensive error handling');

  } catch (error) {
    console.error(`Error occurred: ${error}`);
    if (error instanceof Error) {
      console.error(`   Error message: ${error.message}`);
      if ('status' in error) {
        console.error(`   Status code: ${(error as { status: unknown }).status}`);
      }
    }

    // Attempt cleanup even if there was an error
    try {
      console.log(`\nAttempting cleanup due to error...`);
      await client.deleteIndex(indexName);
      console.log(`Cleanup completed`);
    } catch {
      console.log(`Cleanup failed - manual cleanup may be required`);
    }
  }
}

/**
 * Export the main example function for use in tests or other modules
 * 
 * @exports comprehensiveMossExample - Complete Moss SDK demonstration function
 */
export { comprehensiveMossExample };

// Run the example if this file is executed directly
if (require.main === module) {
  comprehensiveMossExample().catch(console.error);
}