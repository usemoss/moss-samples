# Changelog

All notable changes to the `moss` gem are documented here. The format is based
on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.1.0] - Unreleased

### Added

- Initial release of the Moss Ruby SDK.
- `Moss::Client` with parity on index management, search, and metadata
  filtering:
  - Index mutations with async job polling: `create_index`, `add_documents`
    (`add_docs`), `delete_documents` (`delete_docs`), `get_job_status`.
  - Index reads: `get_index`, `list_indexes`, `delete_index`, `get_documents`
    (`get_docs`).
  - Local runtime: `load_index`, `unload_index`, `refresh_index`,
    `get_index_info`.
  - `query` (aliased `search`) with sub-10ms local execution when an index is
    loaded, plus a cloud query fallback; supports `top_k`, `alpha`, caller
    embeddings, and metadata `filter`.
  - `session` support (`Moss::Session`) for building and querying ephemeral
    in-memory indexes and pushing them to the cloud.
- Custom-embedding indexes with automatic model inference and dimension
  validation.
- Credentials resolved from constructor arguments or the `MOSS_PROJECT_ID` /
  `MOSS_PROJECT_KEY` environment variables.
- Local semantic search powered by the native `libmoss` runtime through the
  `moss-core` bindings gem.
