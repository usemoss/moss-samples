# Moss Python SDK Examples

This project demonstrates the usage of the Moss Python SDK for semantic search and document indexing.

## Setup

1. **Set up Python environment:**
   - Ensure you have Python 3.7+ installed
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

## Requirements

- Python 3.7+
- Valid Moss project credentials
