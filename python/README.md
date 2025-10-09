# Moss - Python Sample

This project demonstrates the usage of the Moss in Python for semantic search and document indexing.

## Setup

1. **Clone or download this repository**

2. **Set up Python environment:**
   - Ensure you have Python 3.7+ installed
   - Create a virtual environment (recommended):

     ```bash
     python -m venv venv
     source venv/bin/activate  # On Windows: venv\Scripts\activate
     ```

3. **Install dependencies:**

   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables:**
   - Copy `.env.template` to `.env`
   - Fill in your Moss project credentials:

     ```bash
     MOSS_PROJECT_ID=your_actual_project_id
     MOSS_PROJECT_KEY=your_actual_project_key
     ```
   - **NOTE:** If you don't have credentials, please fill out the form to request access — [request credentials form](https://form.typeform.com/to/KdqOaXWu) or send an email to [contact@inferedge.dev](mailto:contact@inferedge.dev).

## Usage

Run the example script to see the complete Moss workflow:

```bash
python example_usage.py
```

This will demonstrate:

- Creating an index with documents
- Adding and retrieving documents
- Performing semantic search queries
- Managing indexes and documents

## Requirements

- Python 3.7+
- Valid Moss project credentials

## API Reference

The example uses the following Moss features:

- `MossClient`: Main client for interacting with Moss API
- Index operations: create, list, get info, delete
- Document operations: add, get, delete and update
- Semantic search: load, query

For full API documentation, refer to the official [Moss Documentation](https://docs.inferedge.dev/).
