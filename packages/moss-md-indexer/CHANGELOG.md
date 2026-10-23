# Changelog

## [1.0.0-beta.4] - 2026-10-23

- Upload through `@moss-dev/moss` instead of the legacy `@inferedge-rest/moss` SDK. Indexes are now built by Moss's index service, so current SDKs can run text queries on them. The legacy SDK used the `/manage` write actions that the service is retiring.

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