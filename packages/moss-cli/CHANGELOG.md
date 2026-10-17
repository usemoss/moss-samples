# Changelog

## [Unreleased]

- Shell completions: `moss completions bash` and `moss completions zsh` output
  completion scripts covering commands, subcommands, and global flags, with
  dynamic completion of index names
- `~/.moss/config.json` is now always written with `0600` permissions, including
  when the file already existed with looser permissions

## [0.1.0] - 2026-03-29

- **Initial release** — CLI wrapper for the Moss Python SDK (v1.0.0)
- Index management: `moss index create`, `list`, `get`, `delete`
- Document management: `moss doc add`, `delete`, `get`
- Semantic search: `moss query` with `--cloud`, `--filter`, `--alpha`, `--top-k`
- Job tracking: `moss job status` with `--wait` for live progress
- Interactive credential setup: `moss init`
- Three-tier auth resolution: CLI flags > env vars > config file
- JSON and CSV document input, stdin piping with `--file -`
- `--json` flag on all commands for machine-readable output
- Rich terminal output: tables, progress spinners, colored status
