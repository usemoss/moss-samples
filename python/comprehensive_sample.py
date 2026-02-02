"""
Comprehensive End-to-End Moss SDK Sample

This example demonstrates the complete workflow of the Moss Python SDK, showcasing ALL available functions:
- Index creation and management
- Document operations (add, retrieve, update, delete)
- Semantic search functionality
- Advanced querying with metadata filtering
- Index lifecycle management
- Error handling best practices

The sample uses a dynamic index name based on current timestamp to avoid conflicts.
"""

import asyncio
import os
from typing import List
from dotenv import load_dotenv
from datetime import datetime
from inferedge_moss import MossClient, DocumentInfo, AddDocumentsOptions, GetDocumentsOptions

# Load environment variables
load_dotenv()


async def comprehensive_moss_example():
    """
    Complete end-to-end example demonstrating ALL Moss SDK functionality.
    
    This comprehensive sample covers:
    1. Client initialization
    2. Index creation with initial documents
    3. Index information retrieval
    4. Index listing
    5. Document addition with upsert
    6. Document retrieval (all and specific)
    7. Index loading for querying
    8. Semantic search operations
    9. Document deletion
    10. Index cleanup
    11. Error handling throughout
    """
    print("Comprehensive Moss SDK End-to-End Sample")
    print("=" * 60)

    # Initialize client with project credentials from environment
    project_id = os.getenv("MOSS_PROJECT_ID")
    project_key = os.getenv("MOSS_PROJECT_KEY")

    if not project_id or not project_key:
        print("❌ Error: Missing environment variables!")
        print("Please set MOSS_PROJECT_ID and MOSS_PROJECT_KEY in .env file")
        print("Copy .env.template to .env and fill in your credentials")
        return

    client = MossClient(project_id, project_key)

    # Create comprehensive document collection with rich metadata
    documents: List[DocumentInfo] = [
        DocumentInfo(
            id="tech-ai-001",
            text="Artificial Intelligence (AI) is transforming industries by enabling machines to perform tasks that typically require human intelligence. From healthcare diagnostics to autonomous vehicles, AI applications are revolutionizing how we work and live.",
            metadata={
                "category": "technology",
                "subcategory": "artificial_intelligence", 
                "difficulty": "beginner",
                "topic": "ai_overview",
                "author": "Tech Research Team",
                "tags": "ai,technology,automation,machine_learning",
                "word_count": "42",
                "reading_time": "1 minute",
                "published_date": "2024-01-15",
                "language": "en"
            }
        ),
        DocumentInfo(
            id="tech-ml-002",
            text="Machine Learning is a subset of AI that enables systems to automatically learn and improve from experience without being explicitly programmed. It uses algorithms to analyze data, identify patterns, and make predictions or decisions.",
            metadata={
                "category": "technology",
                "subcategory": "machine_learning",
                "difficulty": "intermediate",
                "topic": "ml_fundamentals",
                "author": "ML Engineering Team",
                "tags": "machine_learning,algorithms,data_science,predictions",
                "word_count": "38",
                "reading_time": "1 minute",
                "published_date": "2024-01-20",
                "language": "en"
            }
        ),
        DocumentInfo(
            id="tech-dl-003",
            text="Deep Learning uses artificial neural networks with multiple layers to model and understand complex patterns in data. It has achieved breakthrough results in image recognition, natural language processing, and game playing.",
            metadata={
                "category": "technology",
                "subcategory": "deep_learning",
                "difficulty": "advanced",
                "topic": "neural_networks",
                "author": "Deep Learning Lab",
                "tags": "deep_learning,neural_networks,image_recognition,nlp",
                "word_count": "35",
                "reading_time": "1 minute",
                "published_date": "2024-01-25",
                "language": "en"
            }
        ),
        DocumentInfo(
            id="tech-nlp-004",
            text="Natural Language Processing (NLP) enables computers to understand, interpret, and generate human language. Applications include chatbots, language translation, sentiment analysis, and text summarization.",
            metadata={
                "category": "technology",
                "subcategory": "natural_language_processing",
                "difficulty": "intermediate",
                "topic": "language_processing",
                "author": "NLP Research Group",
                "tags": "nlp,language,chatbots,translation,sentiment_analysis",
                "word_count": "31",
                "reading_time": "1 minute",
                "published_date": "2024-02-01",
                "language": "en"
            }
        ),
        DocumentInfo(
            id="tech-cv-005",
            text="Computer Vision allows machines to interpret and understand visual information from the world. It powers applications like facial recognition, medical image analysis, autonomous driving, and quality control in manufacturing.",
            metadata={
                "category": "technology",
                "subcategory": "computer_vision",
                "difficulty": "intermediate",
                "topic": "visual_recognition",
                "author": "Computer Vision Team",
                "tags": "computer_vision,image_processing,facial_recognition,autonomous_driving",
                "word_count": "33",
                "reading_time": "1 minute",
                "published_date": "2024-02-05",
                "language": "en"
            }
        ),
        DocumentInfo(
            id="business-data-006",
            text="Data Science combines statistics, programming, and domain expertise to extract actionable insights from data. It involves data collection, cleaning, analysis, and visualization to support business decision-making.",
            metadata={
                "category": "business",
                "subcategory": "data_science",
                "difficulty": "intermediate",
                "topic": "analytics",
                "author": "Data Analytics Team",
                "tags": "data_science,statistics,analytics,business_intelligence",
                "word_count": "32",
                "reading_time": "1 minute",
                "published_date": "2024-02-10",
                "language": "en"
            }
        ),
        DocumentInfo(
            id="business-cloud-007",
            text="Cloud Computing provides on-demand access to computing resources over the internet, including servers, storage, databases, and software. It offers scalability, cost-efficiency, and global accessibility for businesses.",
            metadata={
                "category": "business",
                "subcategory": "cloud_computing",
                "difficulty": "beginner",
                "topic": "infrastructure",
                "author": "Cloud Architecture Team",
                "tags": "cloud_computing,infrastructure,scalability,saas",
                "word_count": "30",
                "reading_time": "1 minute",
                "published_date": "2024-02-15",
                "language": "en"
            }
        )
    ]

    # Create dynamic index name with timestamp
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    index_name = f"comprehensive-demo-{timestamp}"

    try:
        print(f"\nStep 1: Creating index '{index_name}' with {len(documents)} documents...")
        created = await client.create_index(index_name, documents, "moss-minilm")
        print(f"Index created successfully: {created}")

        print("\nStep 2: Retrieving index information...")
        index_info = await client.get_index(index_name)
        print("Index Details:")
        print(f"   - Name: {index_info.name}")
        print(f"   - Document Count: {index_info.doc_count}")
        print(f"   - Model: {index_info.model.id}")
        print(f"   - Status: {index_info.status}")
        print(f"   - Created: {index_info.created_at if hasattr(index_info, 'created_at') else 'N/A'}")

        print("\nStep 3: Listing all available indexes...")
        indexes = await client.list_indexes()
        print(f"Found {len(indexes)} total indexes:")
        for idx in indexes:
            print(f"   - {idx.name}: {idx.doc_count} docs, status: {idx.status}")

        print("\nStep 4: Adding additional documents with upsert...")
        additional_docs: List[DocumentInfo] = [
            DocumentInfo(
                id="security-cyber-008",
                text="Cybersecurity protects digital systems, networks, and data from cyber threats. It involves implementing security measures, monitoring for vulnerabilities, and responding to incidents to maintain data integrity and privacy.",
                metadata={
                    "category": "security",
                    "subcategory": "cybersecurity",
                    "difficulty": "intermediate",
                    "topic": "digital_security",
                    "author": "Security Team",
                    "tags": "cybersecurity,data_protection,privacy,threats",
                    "word_count": "34",
                    "reading_time": "1 minute",
                    "published_date": "2024-02-20",
                    "language": "en"
                }
            ),
            DocumentInfo(
                id="health-biotech-009",
                text="Biotechnology applies biological processes and organisms to develop products and technologies that improve human health and the environment. It includes genetic engineering, drug development, and personalized medicine.",
                metadata={
                    "category": "healthcare",
                    "subcategory": "biotechnology",
                    "difficulty": "advanced",
                    "topic": "medical_innovation",
                    "author": "Biotech Research Lab",
                    "tags": "biotechnology,genetic_engineering,drug_development,personalized_medicine",
                    "word_count": "33",
                    "reading_time": "1 minute",
                    "published_date": "2024-02-25",
                    "language": "en"
                }
            ),
            DocumentInfo(
                id="env-sustainability-010",
                text="Sustainable Technology focuses on developing solutions that meet present needs without compromising future generations. It includes renewable energy, green computing, and environmentally friendly manufacturing processes.",
                metadata={
                    "category": "environment",
                    "subcategory": "sustainability",
                    "difficulty": "intermediate",
                    "topic": "green_technology",
                    "author": "Sustainability Team",
                    "tags": "sustainability,renewable_energy,green_computing,environment",
                    "word_count": "31",
                    "reading_time": "1 minute",
                    "published_date": "2024-03-01",
                    "language": "en"
                }
            )
        ]
        
        add_result = await client.add_docs(index_name, additional_docs, AddDocumentsOptions(upsert=True))
        print(f"Added {len(additional_docs)} additional documents: {add_result}")

        print("\nStep 5: Retrieving all documents from index...")
        all_docs = await client.get_docs(index_name)
        print(f"Total documents in index: {len(all_docs)}")
        
        # Display sample of documents with metadata
        print("Sample documents preview:")
        for i, doc in enumerate(all_docs[:3]):
            text_preview = doc.text[:80] + "..." if len(doc.text) > 80 else doc.text
            print(f"   {i+1}. [{doc.id}] {text_preview}")
            if doc.metadata:
                category = doc.metadata.get('category', 'N/A')
                difficulty = doc.metadata.get('difficulty', 'N/A')
                print(f"      Category: {category} | Difficulty: {difficulty}")

        print("\nStep 6: Retrieving specific documents by ID...")
        target_doc_ids = ["tech-ai-001", "business-data-006", "security-cyber-008"]
        specific_docs = await client.get_docs(
            index_name, 
            GetDocumentsOptions(doc_ids=target_doc_ids)
        )
        print(f"Retrieved {len(specific_docs)} specific documents:")
        for doc in specific_docs:
            text_preview = doc.text[:60] + "..." if len(doc.text) > 60 else doc.text
            print(f"   - [{doc.id}] {text_preview}")
            if doc.metadata:
                tags_str = doc.metadata.get('tags', '')
                tags = tags_str.split(',') if tags_str else []
                print(f"     Tags: {', '.join(tags[:3])}{'...' if len(tags) > 3 else ''}")

        print("\nStep 7: Loading index for semantic search operations...")
        loaded_index = await client.load_index(index_name)
        print(f"Index loaded for querying: {loaded_index}")

        print("\nStep 8: Performing comprehensive semantic search tests...")
        search_queries = [
            ("artificial intelligence and machine learning", 4),
            ("data analysis and business insights", 3),
            ("visual recognition and image processing", 3),
            ("cybersecurity and data protection", 2),
            ("healthcare innovation and biotechnology", 2),
            ("sustainable technology and environment", 2)
        ]

        for i, (query, limit) in enumerate(search_queries, 1):
            print(f"\n   Search {i}: \"{query}\"")
            search_results = await client.query(index_name, query, top_k=limit)
            
            print(f"   Time taken: {search_results.time_taken_ms} ms")
            print(f"   Found {len(search_results.docs)} results:")
            
            for j, result in enumerate(search_results.docs, 1):
                text_preview = result.text[:70] + "..." if len(result.text) > 70 else result.text
                print(f"      {j}. [{result.id}] Score: {result.score:.3f}")
                print(f"         {text_preview}")
                if result.metadata:
                    category = result.metadata.get('category', 'N/A')
                    topic = result.metadata.get('topic', 'N/A')
                    print(f"         {category} | {topic}")

        print("\nStep 9: Demonstrating document deletion...")
        docs_to_delete = ["health-biotech-009", "env-sustainability-010"]
        delete_result = await client.delete_docs(index_name, docs_to_delete)
        print(f"Deleted documents: {delete_result}")

        print("\nStep 10: Verifying document count after deletion...")
        remaining_docs = await client.get_docs(index_name)
        print(f"Remaining documents: {len(remaining_docs)}")

        print("\nStep 11: Final search validation...")
        final_search = await client.query(
            index_name,
            "technology innovation and automation",
            top_k=5
        )
        
        print("Final search results:")
        print(f"   Query: \"{final_search.query}\"")
        print(f"   Time: {final_search.time_taken_ms} ms")
        print(f"   Results: {len(final_search.docs)}")
        
        for i, item in enumerate(final_search.docs, 1):
            print(f"   {i}. [{item.id}] Score: {item.score:.3f}")

        print("\nStep 12: Cleaning up - deleting the test index...")
        deleted = await client.delete_index(index_name)
        print(f"Index deleted: {deleted}")

        print("\nComprehensive Moss SDK Example Completed Successfully!")
        print("=" * 60)
        print("Summary of operations performed:")
        print("   - Index creation with initial documents")
        print("   - Index information retrieval")
        print("   - Index listing")
        print("   - Document addition with upsert")
        print("   - Document retrieval (all and specific)")
        print("   - Index loading for querying")
        print("   - Multiple semantic search operations")
        print("   - Document deletion")
        print("   - Index cleanup")
        print("   - Comprehensive error handling")

    except Exception as error:
        print(f"Error occurred: {error}")
        if hasattr(error, 'message'):
            print(f"   Error message: {error.message}")
        if hasattr(error, 'status_code'):
            print(f"   Status code: {error.status_code}")
        
        # Attempt cleanup even if there was an error
        try:
            print("\nAttempting cleanup due to error...")
            await client.delete_index(index_name)
            print("Cleanup completed")
        except Exception:
            print("Cleanup failed - manual cleanup may be required")


# Export for use in tests or other modules
__all__ = ["comprehensive_moss_example"]


# Run the example
if __name__ == "__main__":
    asyncio.run(comprehensive_moss_example())