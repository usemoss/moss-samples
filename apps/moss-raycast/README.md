# Moss Search (Raycast)

Semantic search over a [Moss](https://moss.dev) index, right from Raycast.

This extension queries an index you've already created in Moss — it doesn't
index anything itself. Create and populate an index first (e.g. with the
[JavaScript SDK](../../sdks/javascript) or [Python SDK](../../sdks/python)),
then use this extension to search it from anywhere on your machine.

## Setup

```bash
cd apps/moss-raycast
npm install
npm run dev
```

`npm run dev` starts Raycast's development mode and imports the extension
into your local Raycast app. The first time you run the **Search Moss
Index** command, Raycast will prompt you for:

- **Project ID** — your Moss project ID
- **Project Key** — your Moss project key
- **Index Name** — the name of the index to query

## Usage

1. Open Raycast and run **Search Moss Index**
2. Type a query — results update as you type
3. Press `Enter` to copy a result's text to the clipboard

## Architecture

The command loads the configured index once with `MossClient.loadIndex()`
so repeat queries run in-memory, then calls `MossClient.query()` on every
keystroke (throttled) via `@raycast/utils`'s `useCachedPromise`.

## License

[BSD 2-Clause License](./LICENSE)
