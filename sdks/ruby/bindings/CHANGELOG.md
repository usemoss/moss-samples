# Changelog

All notable changes to the `moss-core` gem are documented here.

## [0.9.0] - Unreleased

### Added

- Initial release of the Ruby FFI bindings over the `libmoss` C SDK (targets
  libmoss `0.9.0`).
- `Moss::Core::ManageClient` — cloud mutations and reads.
- `Moss::Core::IndexManager` — local index load/unload/query/refresh.
- `Moss::Core::Session` — ephemeral in-memory index sessions.
- Lazy library resolution via `MOSS_LIBRARY_PATH` / `MOSS_LIB_DIR`, degrading to
  `Moss::Core::BindingsUnavailableError` when `libmoss` is absent.
