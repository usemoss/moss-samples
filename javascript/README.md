# Moss JavaScript SDK Examples

This project demonstrates the usage of the Moss JavaScript SDK for semantic search and document indexing.

## Setup

1. **Install dependencies:**

   ```bash
   npm install
   ```

2. **Configure environment variables:**
   - Copy `.env.template` to `.env`
   - Fill in your Moss project credentials:

     ```env
     MOSS_PROJECT_ID=your_actual_project_id
     MOSS_PROJECT_KEY=your_actual_project_key
     MOSS_INDEX_NAME=your_existing_index_name
     ```

## Running Samples

### Comprehensive Sample

Run the complete end-to-end example showing all SDK functions:

```bash
npx tsx comprehensive_sample.ts
```

### Load and Query Sample

Run the simple example to load an existing index and perform queries:

```bash
npx tsx load_and_query_sample.ts
```

### Custom Embedding Sample

Provision a fresh index (using the name supplied via `MOSS_INDEX_NAME`), push documents with manually generated OpenAI embeddings, and issue sample queries:

```bash
npx tsx custom_embedding_sample.ts
```

## Requirements

- Node.js (version 16 or higher)
- Valid Moss project credentials
