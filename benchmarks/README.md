# Benchmarks

- [`local/`](local/): Moss against vector search engines that run inside your application (FAISS, Chroma, LanceDB, Qdrant local, zvec, sqlite-vec, DuckDB-VSS). Recall, latency, memory, build cost, filters and text retrieval on public datasets. Results: [summary](local/RESULTS.md), [full detail](local/RESULTS-DETAIL.md).
- [`cloud/`](cloud/): end-to-end query latency (embedding + search) of Moss against Pinecone, Qdrant Cloud and ChromaDB with an external embedding service, on 100,000 documents.
