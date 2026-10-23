# Changelog

## [1.0.0-beta.4] - 2026-09-18

### Changed
- **BREAKING**: Migrated from `@inferedge-rest/moss` to `@moss-dev/moss` SDK
  - The legacy `MossRestClient` is replaced with the current `MossClient`
  - This is a dependency change only; public API signatures remain the same

### Added
- Non-destructive index updates by default
  - `uploadDocuments()` now upserts new documents and deletes stale ones instead of deleting the entire index
  - The live index stays available during rebuilds, preventing search downtime
  - If an update fails, the existing index is not deleted, though partial updates may remain
- `recreate` option in `UploadOptions` to force legacy delete-then-create behavior
- Unit tests for `uploader.ts` with mocked MossClient

### Fixed
- Search is no longer broken during index rebuilds
- Failed uploads no longer leave the site without an index

## [1.0.0-beta.3] - 2026-02-18

- Internal maintenance

## [1.0.0-beta.2] - 2026-02-03

- Fixed ESM related conflicts

## [1.0.0-beta.1] - 2026-01-05

- function-based API for programmatic usage
  - Exported `sync()` function for building and uploading in one call
  - Exported `buildJsonDocs()` function for building search index programmatically
  - Exported `uploadDocuments()` function for uploading documents programmatically
  - Exported `createIndex()` function for uploading an existing index file
  - Functions can be imported and called directly in code
  - Support for passing credentials via function options or environment variables
  - Functions return structured data (e.g., `{ success: boolean, count: number }`)