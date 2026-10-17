# Moss Python SDK Examples

This project demonstrates the usage of the Moss Python SDK for semantic search and document indexing.

## Setup

1. **Set up Python environment:**
   - Ensure you have Python 3.10+ installed
   - Create a virtual environment (recommended):

     ```bash
     python3 -m venv venv
     source venv/bin/activate  # On Windows: venv\Scripts\activate
     ```

2. **Install dependencies:**

   ```bash
   python3 -m pip install -r requirements.txt
   ```

3. **Configure environment variables:**
   - Copy `.env.template` to `.env`
   - Fill in your Moss project credentials:

     ```bash
     MOSS_PROJECT_ID=your_actual_project_id
     MOSS_PROJECT_KEY=your_actual_project_key
     MOSS_INDEX_NAME=your_existing_index_name
     ```

## Running Samples

### Comprehensive Sample

Run the complete end-to-end example showing all SDK functions:

```bash
python comprehensive_sample.py
```

### Load and Query Sample

Run the simple example to load an existing index and perform queries:

```bash
python load_and_query_sample.py
```

### Custom Embedding Sample

Create a brand-new index, add documents with manually generated OpenAI embeddings, and issue sample queries:

```bash
python custom_embedding_sample.py
```

### Metadata Filtering Sample

Create an index, load it locally, and run queries filtered by document metadata using `$eq`, `$and`, `$in`, and `$near` operators.

Requires `moss>=1.0.0`.

```bash
python metadata_filtering.py
```

### Multi-Index Search Sample

Create three related indexes (products, reviews, faqs), bulk-load them with `load_indexes`, search across all three in one call with `query_multi_index`, and inspect the per-result `index_name` tagging.

Requires `moss>=1.1.0`.

```bash
python multi_index_search.py
```

### Session Sample

Open a local-first `SessionIndex`, add documents in real time (no cloud round trip), query the in-memory index, then `push_index` to the cloud so another agent or device can resume it. This is how Moss indexes a live conversation.

### Metrics & Tracing Sample

Demonstrate opt-in metrics and tracing callbacks (`QueryMetrics`, `on_query`) for observing query latency, counts, and result stats without vendor lock-in.

```bash
python metrics_and_tracing_sample.py
```

## Requirements

- Python 3.10+
- Valid Moss project credentials
