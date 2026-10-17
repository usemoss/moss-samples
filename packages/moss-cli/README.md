# Moss CLI

**Command-line interface for Moss semantic search** — manage indexes, documents, and queries directly from your terminal.

Moss CLI wraps the [Moss Python SDK](https://docs.moss.dev/) so you can build and query semantic search indexes without writing any code. Ideal for quick prototyping, scripting, CI/CD pipelines, and data workflows.

## Features

- **Full SDK coverage** — every SDK operation available as a CLI command
- **Semantic search** — query indexes with configurable hybrid search (semantic + keyword)
- **Index management** — create, list, inspect, and delete indexes
- **Document management** — add, update, retrieve, and delete documents
- **Local by default** — downloads indexes for on-device queries, `--cloud` to skip
- **Flexible auth** — CLI flags, environment variables, or config file
- **Multiple output formats** — rich tables for humans, `--json` for scripts
- **Latency benchmarking** — measure p50/p95/p99 retrieval latency with `moss bench`
- **Job tracking** — poll background jobs with live progress display
- **Pipe-friendly** — stdin/stdout support for composing with other tools

## Installation

```bash
pip install moss-cli
```

## Quick Start

```bash
# 1. Save your credentials
moss init

# 2. List your indexes
moss index list

# 3. Create an index from a JSON file
moss index create my-index -f docs.json --wait

# 4. Search it
moss query my-index "what is machine learning"

# 5. Search via cloud API (skips local download)
moss query my-index "neural networks" --cloud
```

## Authentication

Credentials are resolved in this order:

1. **CLI flags**: `--project-id` and `--project-key`
2. **Environment variables**: `MOSS_PROJECT_ID` and `MOSS_PROJECT_KEY`
3. **Config profile**: selected by `--profile`, `MOSS_PROFILE`, or the active profile in `~/.moss/config.json`

```bash
# Option 1: Interactive setup (recommended)
moss init
moss init --profile staging

# Option 2: Environment variables
export MOSS_PROJECT_ID="your-project-id"
export MOSS_PROJECT_KEY="your-project-key"
export MOSS_PROFILE="staging"

# Option 3: Inline flags
moss index list --project-id "..." --project-key "..."

# Option 4: Profile-based usage
moss index list --profile staging
moss profile list
```

## Commands

### Index Management

```bash
# Create an index with documents from a JSON file
moss index create my-index -f documents.json --model moss-minilm

# Create and wait for completion
moss index create my-index -f documents.json --wait

# List all indexes
moss index list
moss index list --profile staging

# Get index details
moss index get my-index

# Delete an index
moss index delete my-index
moss index delete my-index --confirm  # skip prompt
```

### Document Management

```bash
# Add documents to an existing index
moss doc add my-index -f new-docs.json

# Add with upsert (update existing, insert new)
moss doc add my-index -f docs.json --upsert --wait

# Get all documents
moss doc get my-index

# Get specific documents
moss doc get my-index --ids doc1,doc2,doc3

# Delete documents
moss doc delete my-index --ids doc1,doc2
```

### Query

```bash
# Search (downloads index and queries on-device by default)
moss query my-index "what is deep learning"

# Tune results: more results, keyword-heavy
moss query my-index "neural networks" --top-k 20 --alpha 0.3

# Cloud mode (skip download, query via cloud API)
moss query my-index "transformers" --cloud

# Interactive mode (keeps one loaded index for multiple queries)
moss query my-index --interactive

# Interactive mode with session defaults
moss query my-index --interactive --top-k 20 --alpha 0.4

# Note: interactive mode is local-only (no --cloud) and not supported with --json
# Note: with redirected/piped stdin, interactive mode runs the piped query (if provided) and exits

# In interactive prompt:
#   /set alpha 0.5
#   /set top-k 10
#   /exit

# With metadata filter (local only)
moss query my-index "shoes" --filter '{"field": "category", "condition": {"$eq": "footwear"}}'

# Pipe query from stdin
echo "what is AI" | moss query my-index

# JSON output for scripting
moss query my-index "query" --json | jq '.docs[0].text'
```

### Benchmark

```bash
# Benchmark latency with a single inline query
moss bench my-index --query "what is semantic search?" --runs 20

# Multiple inline queries
moss bench my-index \
  --query "what is semantic search?" \
  --query "how does embedding work?" \
  --runs 20 --warmup 5

# Load queries from a file (one per line)
moss bench my-index --queries-file queries.txt --runs 50

# JSON output for CI/scripting
moss bench my-index --query "what is AI?" --json

# Cloud mode (skip local index download)
moss bench my-index --query "what is AI?" --cloud --runs 10
```

### Job Tracking

```bash
# Check job status
moss job status <job-id>

# Wait for job to finish (with live progress)
moss job status <job-id> --wait
```

### Other

```bash
# Print version info
moss version

# Global JSON output
moss index list --json
moss doc get my-index --json

# List available auth profiles
moss profile list

# Delete a profile
moss profile delete staging --force
```

## Shell Completions

Enable tab-completion for commands, subcommands, flags, and index names in Bash
and Zsh. `moss completions <shell>` prints a completion script to stdout.

```bash
# Bash — add to your shell startup file
moss completions bash >> ~/.bashrc

# Zsh
moss completions zsh >> ~/.zshrc
```

Then restart your shell (or `source` the file) to activate it. Once enabled,
index-name arguments complete dynamically against your available indexes:

```bash
moss query <TAB>        # lists your indexes
moss index delete sup<TAB>
```

Dynamic index completion uses your resolved credentials (flags, env vars, or the
active profile). If credentials are missing or unreachable, completion simply
falls back to no suggestions rather than erroring.

## Document File Format

### JSON (recommended)

```json
[
  {"id": "doc1", "text": "Machine learning fundamentals", "metadata": {"topic": "ml"}},
  {"id": "doc2", "text": "Deep learning with neural networks"},
  {"id": "doc3", "text": "Natural language processing", "metadata": {"topic": "nlp"}}
]
```

Also supports a wrapper format: `{"documents": [...]}`.

### CSV

```csv
id,text,metadata
doc1,Machine learning fundamentals,"{""topic"": ""ml""}"
doc2,Deep learning with neural networks,
doc3,Natural language processing,"{""topic"": ""nlp""}"
```

### stdin

```bash
cat docs.json | moss index create my-index -f -
cat docs.json | moss doc add my-index -f -
```

## Global Options

| Flag | Short | Description |
|---|---|---|
| `--project-id` | `-p` | Project ID (overrides env/config) |
| `--project-key` | | Project key (overrides env/config) |
| `--profile` | | Credential profile name (overrides `MOSS_PROFILE`) |
| `--json` | | Machine-readable JSON output |
| `--verbose` | `-v` | Enable debug logging |

## Available Models

| Model | Description |
|---|---|
| `moss-minilm` | Lightweight, optimized for speed (default) |
| `moss-mediumlm` | Balanced accuracy and performance |
| `custom` | Used automatically when documents include embeddings |

## License

Copyright (c) 2026 InferEdge Inc. — BSD 2-Clause License.

See [LICENSE](LICENSE) for full terms.
