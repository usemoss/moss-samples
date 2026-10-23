# Moss Semantic Search (Obsidian)

Local-first semantic search over your Obsidian vault, powered by [Moss](https://moss.dev) `SessionIndex`.

Notes are chunked by heading and embedded **on your machine** by the Moss native runtime. Queries run in-memory in a few milliseconds. Nothing is uploaded unless you turn on cloud sync.

Resolves [usemoss/moss#414](https://github.com/usemoss/moss/issues/414). Same architecture as [`apps/moss-vscode`](../moss-vscode): the native runtime runs in a separate worker process so a native fault cannot take down Obsidian.

## Features

- **Search by meaning** — `Moss: Search vault by meaning` (ribbon icon, status bar, or command palette). Type, get ranked sections, press Enter to jump to the matching heading (`Cmd/Ctrl+Enter` or `Cmd/Ctrl+click` opens in a new tab).
- **Heading-aware chunks** — each `#`/`##`/`###` section is one document, carrying its breadcrumb (`Note > H2 > H3`) so results land on the right section, not just the right note. Long sections are windowed with overlap, and a single over-long line (a soft-wrapped paragraph) is split at whitespace so every chunk fits the embedding window. Frontmatter is skipped; `#` inside code fences (including nested fences) is not a heading.
- **Hybrid search** — semantic + BM25, tunable `alpha`.
- **Incremental** — create / modify / delete / rename are re-indexed within ~1s of the change; no full rebuild. On startup the restored index is reconciled against the vault, so notes edited while Obsidian was closed (sync, git, another device) are caught up automatically.
- **Persisted** — the index is saved with `saveToDisk` under the plugin folder; reopening the vault restores it instantly.
- **Optional cloud sync** — off by default. When on, `pushIndex` uploads the index so another device can restore it.
- **Crash-isolated** — the Moss native module runs in a forked worker (`mossWorker.js`), not in Obsidian's renderer.

## Requirements

- Obsidian **desktop** 1.7.2+ (macOS arm64/x64, Linux x64/arm64, Windows x64 — the platforms `@moss-dev/moss-core` ships binaries for).
- A Moss project ID and key from the [Moss portal](https://moss.dev). The key is used to open the session; your note text does not leave the machine unless cloud sync is on (see [PRIVACY.md](./PRIVACY.md)).
- Node.js 20+ is used for the worker when found on the machine (each candidate binary is version-probed; older ones are skipped); otherwise the plugin runs Obsidian's own runtime as Node. You can pin a binary under **Settings → Advanced → Node binary path**.

## Install

The plugin ships a native dependency, so it is installed from source (not from the community plugin store):

```bash
cd apps/moss-obsidian
npm install
npm run install-to-vault -- /path/to/your/vault
```

This builds `main.js` / `mossWorker.js` and copies them, `manifest.json`, `styles.css` and `node_modules/@moss-dev/*` into `<vault>/.obsidian/plugins/moss-search/`. Then:

1. **Settings → Community plugins** → enable **Moss Semantic Search**.
2. **Settings → Moss Semantic Search** → paste your Project ID and Project key.
3. Run **Moss: Create index** (command palette). The status bar shows progress, then `Moss: N notes · M sections`.
4. Click the status bar item, the ribbon icon, or run **Moss: Search vault by meaning**.

## Commands

| Command | Description |
|---------|-------------|
| `Moss: Search vault by meaning` | Open the search modal |
| `Moss: Create index` / `Rebuild index` | Scan and embed every note (required once; rebuild after changing model or exclusions) |
| `Moss: Cancel indexing` | Stop a running build |
| `Moss: Sync index to Moss Cloud` | Upload the current index with `pushIndex` |
| `Moss: Restart Moss worker` | Recover from a crashed native runtime |

## Settings

| Setting | Default | Notes |
|---------|---------|-------|
| Project ID / key | — | Stored in `data.json` inside `.obsidian/plugins/moss-search/`. Exclude that file from sync if you share the vault. |
| Embedding model | `moss-minilm` | `moss-mediumlm` is available; rebuild after switching. |
| Excluded folders | `templates` | One vault-relative folder per line, matched case-insensitively. `.obsidian`, `.trash`, `.git` are always skipped. |
| Chunk size | 1600 chars | Sections longer than this are split into overlapping windows; over-long single lines are split at whitespace. |
| Results | 20 | `topK` |
| Semantic weight | 0.7 | `alpha`: 1.0 semantic, 0.0 keyword |
| One result per note | off | Collapse multiple sections of one note into its best match |
| Sync index to Moss Cloud | **off** | See PRIVACY.md |
| Node binary path | auto | Absolute path to a Node 20+ binary for the worker |

## How it works

```text
Obsidian renderer (main.js)                     worker process (mossWorker.js)
┌─────────────────────────────┐  IPC (child)   ┌──────────────────────────────┐
│ VaultIndexer                │ ─────────────▶ │ @moss-dev/moss  SessionIndex │
│  vault events → chunkNote() │  addDocs /     │  embeds locally (moss-minilm)│
│ MossSearchModal             │  deleteDocs /  │  hybrid query, in-memory     │
│  debounced query → hits     │  query / save  │  saveToDisk / loadFromDisk   │
└─────────────────────────────┘                └──────────────────────────────┘
```

- Session name is `obsidian-<sha256(vaultId)[:12]>`, where `vaultId` is a random UUID generated once and stored in the plugin's `data.json` — so two vaults that share a display name never collide on one cloud index, and a vault synced with its `.obsidian` folder keeps one identity across devices.
- Chunk ids are `<path>#chunk-<n>`, with metadata `filePath`, `title`, `headingPath`, `heading`, `startLine`, `endLine`. Incremental updates upsert the first `n` ids and delete any surplus.
- The cache lives at `.obsidian/plugins/moss-search/cache/` (`meta.json` — file → chunk counts and mtimes — plus the Moss session files). On startup the plugin restores from it and reconciles against the vault's current mtimes. Delete it and run **Rebuild index** to start over.

## Development

```bash
npm install
npm run dev        # rebuild on change
npm run typecheck
npm test           # vitest: chunker, excludes, search mapping, indexer (with a fake session)
```

Tests cover the pure modules; the worker/native path is exercised manually in a vault (the SDK needs live credentials).

## Known limitations

- Desktop only (`isDesktopOnly: true`) — the native runtime does not run on Obsidian mobile.
- Not distributable through the Obsidian community plugin store as-is: the store ships only `main.js`/`manifest.json`/`styles.css`, and this plugin needs `node_modules/@moss-dev/*` alongside them. Installing from source is the supported path for now.
- Only `.md` files are indexed (no canvas, PDFs, or attachments).
- Setext headings (`===` / `---` underlines) are not section breaks; their text is still indexed under the parent section.
- Cancelling an index build leaves the index incomplete — the plugin marks it as such and asks for a rebuild rather than searching partial data.
- Opening the session validates the project key with Moss Cloud, so first launch needs network access; subsequent searches are local.

## License

BSD-2-Clause, same as the repository.
