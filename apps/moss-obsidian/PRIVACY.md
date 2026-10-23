# Moss Semantic Search (Obsidian) — Privacy Notes

This describes what the plugin does with your notes and credentials. It mirrors [`apps/moss-vscode/PRIVACY.md`](../moss-vscode/PRIVACY.md) and applies to the code in this folder.

## Summary

- **Your notes are chunked and embedded locally** on your machine by `@moss-dev/moss-core`. Search runs in memory.
- **Cloud sync is off by default.** Nothing about your notes is uploaded unless you enable **Sync index to Moss Cloud** or run **Moss: Sync index to Moss Cloud**.
- **Credentials are stored in the plugin's `data.json`** inside your vault's `.obsidian` folder.
- The Moss SDK may emit **usage telemetry** unless disabled (see below).

## Data stored on your device

| Data | Location | Purpose |
|------|----------|---------|
| Moss Project ID / key | `.obsidian/plugins/moss-search/data.json` | Open a `SessionIndex` |
| Search index (embeddings + chunk text) | `.obsidian/plugins/moss-search/cache/` | Fast local search, instant restore on reopen |
| Index metadata (`meta.json`) | same folder | Which notes are indexed and how many sections each has |

If you sync or commit your `.obsidian` folder, exclude `plugins/moss-search/data.json` (your key) and `plugins/moss-search/cache/` (your note text).

## Data sent to Moss Cloud

1. **Authentication** — the project ID and key are sent to Moss to validate the session when the plugin starts.
2. **Cloud sync (opt-in)** — when enabled, the note text of every indexed section, its metadata (path, headings, line numbers) and the locally computed embeddings are uploaded via `pushIndex()` to the index `obsidian-<hash>` in your Moss project — after the initial build **and again, in full, shortly after any note edit** (the upload replaces the cloud index). On another device with the same credentials, the same synced plugin `data.json` (which carries the vault's generated id) and no local cache, the plugin restores from that index.

Moss does not re-embed documents server-side during `pushIndex`; embeddings are computed on your machine.

## Telemetry

The `@moss-dev/moss` SDK may send pseudonymous usage telemetry, including a stable per-device identifier the SDK stores on disk. To opt out, set the environment variable before Obsidian starts — note that launching Obsidian from the Dock/Start menu does not inherit shell exports, so set it system-wide or launch from a terminal:

```bash
export MOSS_DISABLE_TELEMETRY=1
```

## Your choices

- Keep cloud sync off (default) for a fully local index.
- Delete the local index: remove `.obsidian/plugins/moss-search/cache/`.
- Delete a synced index: remove `obsidian-<hash>` from your Moss project dashboard.
- Remove credentials: clear them in the plugin settings (this rewrites `data.json`).
