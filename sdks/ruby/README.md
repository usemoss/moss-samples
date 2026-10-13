# Moss Ruby SDK

On-device semantic search for Ruby and Rails, powered by the
[Moss](https://docs.moss.dev/docs/start/what-is-moss) runtime.

This directory contains two gems, following the same two-layer structure as the
other Moss SDKs:

| Directory | Gem | Role |
| --- | --- | --- |
| [`sdk/`](sdk) | `moss` | Ergonomic, pure-Ruby client — start here |
| [`bindings/`](bindings) | `moss-core` | Native FFI bindings over the `libmoss` C SDK |

## Getting started

See [`sdk/README.md`](sdk/README.md) for installation, quick start, metadata
filtering, custom embeddings, and the full API.

```ruby
require "moss"

client = Moss::Client.new # creds from MOSS_PROJECT_ID / MOSS_PROJECT_KEY
client.create_index("support-docs", documents)
client.load_index("support-docs")
client.query("support-docs", "how long do refunds take?", top_k: 3)
```

## Requirements

- Ruby >= 3.0
- The native `libmoss` runtime for local indexing and search — download from the
  [`c-sdk-v0.9.0` release](https://github.com/usemoss/moss/releases/tag/c-sdk-v0.9.0)
  and point `MOSS_LIB_DIR` at its `lib/` directory.
- Moss project credentials from [moss.dev](https://moss.dev).

## Layout

```text
sdks/ruby/
├── sdk/            # the `moss` gem (high-level client)
│   ├── lib/moss/   # client, models, cloud query fallback, sessions
│   ├── test/       # unit tests + env-gated integration test
│   ├── samples/    # runnable usage examples
│   └── scripts/    # live end-to-end validation harness
└── bindings/       # the `moss-core` gem (FFI over libmoss)
    └── lib/moss/core/
```

## Development

```bash
# high-level SDK
cd sdks/ruby/sdk && bundle install && bundle exec rake test && bundle exec rubocop

# bindings
cd sdks/ruby/bindings && ruby -Itest -Ilib test/library_test.rb
```

Local semantic search, metadata filtering, and E2E tests require `libmoss` and
credentials; they auto-skip gracefully when either is absent.
