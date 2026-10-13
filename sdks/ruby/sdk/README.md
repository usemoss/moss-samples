# Moss Ruby SDK

`moss` is the Ruby SDK for [Moss](https://docs.moss.dev/docs/start/what-is-moss),
a real-time semantic search runtime for AI agents. It gives Ruby and Rails
developers on-device semantic search — indexing, sub-10ms local search, and
metadata filtering — without leaving their stack.

The SDK has two layers:

- **`moss`** (this gem) — the ergonomic, pure-Ruby client.
- **[`moss-core`](../bindings)** — native FFI bindings over the `libmoss` C SDK
  that power local indexing and search.

Mutations go to Moss Cloud; queries run locally when an index is loaded and
otherwise fall back to the cloud query API.

## Features

- Typed client and value objects for indexes, documents, and search results
- Index creation and document mutation with async job polling
- Index and document reads
- Local index loading, metadata, and sub-10ms query via native bindings
- Cloud query fallback when an index is not loaded locally
- Metadata filtering (`$eq`, `$and`, `$or`, `$in`, `$near`, …)
- Optional caller-provided embeddings for custom indexes
- Ephemeral in-memory sessions
- Env-gated live integration tests

## Installation

Add to your `Gemfile`:

```ruby
gem "moss"
```

Then install the native `libmoss` runtime (required for local indexing and
search). Download the archive for your platform from the
[`c-sdk-v0.9.0` release](https://github.com/usemoss/moss/releases/tag/c-sdk-v0.9.0)
and point the bindings at it:

```bash
export MOSS_LIB_DIR="/path/to/libmoss/lib"
```

Get project credentials at [moss.dev](https://moss.dev) and export them:

```bash
export MOSS_PROJECT_ID=...
export MOSS_PROJECT_KEY=...
```

## Quick start

```ruby
require "moss"

client = Moss::Client.new # reads MOSS_PROJECT_ID / MOSS_PROJECT_KEY from ENV

documents = [
  Moss::DocumentInfo.new(
    id: "doc-1",
    text: "Refunds are processed within five to seven business days.",
    metadata: { "topic" => "refunds" }
  ),
  Moss::DocumentInfo.new(
    id: "doc-2",
    text: "Orders can be tracked from the account dashboard.",
    metadata: { "topic" => "shipping" }
  )
]

client.create_index("support-docs", documents)
client.load_index("support-docs")

result = client.query("support-docs", "how long do refunds take?", top_k: 3)
result.docs.each { |doc| puts "#{doc.id} #{format('%.3f', doc.score)}" }

client.close
```

Credentials can also be passed explicitly:

```ruby
client = Moss::Client.new(project_id: "…", project_key: "…")
```

## Metadata filtering

Filters require a locally loaded index. The filter is passed to the engine
verbatim, using its filter schema (`field` + `condition`):

```ruby
client.load_index("support-docs")

client.query(
  "support-docs",
  "how long do refunds take?",
  top_k: 3,
  filter: { "field" => "topic", "condition" => { "$eq" => "shipping" } }
)

# Compound filters:
client.query(
  "products",
  "running shoes",
  filter: {
    "$and" => [
      { "field" => "category", "condition" => { "$eq" => "shoes" } },
      { "field" => "price", "condition" => { "$lt" => "100" } }
    ]
  }
)
```

## Custom embeddings

If your documents already have embeddings, omit `model_id` and the SDK infers
the `custom` model automatically. All documents in a batch must either all have
embeddings or none:

```ruby
docs = [
  Moss::DocumentInfo.new(id: "doc-1", text: "…", embedding: [0.1, 0.2, 0.3, 0.4]),
  Moss::DocumentInfo.new(id: "doc-2", text: "…", embedding: [0.5, 0.6, 0.7, 0.8])
]

client.create_index("custom-embeddings", docs)
client.load_index("custom-embeddings")

client.query("custom-embeddings", "", embedding: [0.1, 0.2, 0.3, 0.4], top_k: 5)
```

## Progress callbacks

Long-running mutations poll an async job until completion. Pass `on_progress`
to observe it:

```ruby
client.create_index("support-docs", documents, on_progress: lambda { |p|
  puts "#{p.status} #{(p.progress * 100).round}%"
})
```

## Sessions

Build and query an index in memory, then push it to the cloud (sessions require
an enterprise plan):

```ruby
session = client.session("scratch")
session.add_documents([Moss::DocumentInfo.new(id: "1", text: "hello world")])
session.query("greeting", top_k: 3)
session.push_index
session.close
```

## API overview

| Method | Description |
| --- | --- |
| `create_index(name, docs, model_id:, on_progress:)` | Create an index (polls to completion) |
| `add_documents(name, docs, upsert:, on_progress:)` | Add/upsert documents (`add_docs`) |
| `delete_documents(name, ids, on_progress:)` | Delete documents by id (`delete_docs`) |
| `get_job_status(job_id)` | Fetch async job status |
| `get_index(name)` / `list_indexes` / `delete_index(name)` | Index metadata management |
| `get_documents(name, doc_ids:)` | Read stored documents (`get_docs`) |
| `load_index(name, …)` / `unload_index(name)` | Manage the local runtime |
| `refresh_index(name)` / `get_index_info(name)` | Local index metadata |
| `query(name, text, top_k:, alpha:, embedding:, filter:)` | Search (`search`); local, else cloud |
| `session(name, model_id:)` | Open an in-memory session |
| `close` | Release native runtime handles |

## Configuration

| Environment variable | Purpose |
| --- | --- |
| `MOSS_PROJECT_ID` | Project id (required) |
| `MOSS_PROJECT_KEY` | Project key (required) |
| `MOSS_LIB_DIR` / `MOSS_LIBRARY_PATH` | Location of the `libmoss` runtime |
| `MOSS_CLOUD_API_MANAGE_URL` | Override the manage endpoint |
| `MOSS_CLOUD_QUERY_URL` | Override the cloud query endpoint |

## Development

```bash
cd sdks/ruby/sdk
bundle install
bundle exec rake test          # unit tests (native/E2E auto-skip)
bundle exec rubocop            # lint
```

Run the standalone samples in [`samples/`](samples), e.g.:

```bash
MOSS_LIB_DIR=/path/to/libmoss/lib \
MOSS_PROJECT_ID=… MOSS_PROJECT_KEY=… \
ruby -Ilib -I../bindings/lib samples/comprehensive_sample.rb
```

### Live validation

An end-to-end validation harness exercises the whole stack against your Moss
project. It reads credentials at runtime from a repo-root `.env` file and
auto-provisions `libmoss`:

```bash
ruby sdks/ruby/sdk/scripts/validate.rb
```

## Integration tests

Live tests auto-skip unless `MOSS_PROJECT_ID` / `MOSS_PROJECT_KEY` are set and
`libmoss` is available:

```bash
MOSS_LIB_DIR=/path/to/libmoss/lib \
MOSS_PROJECT_ID=… MOSS_PROJECT_KEY=… \
ruby -Itest -Ilib -I../bindings/lib test/integration_test.rb
```

## License

BSD 2-Clause. See [LICENSE](LICENSE).
