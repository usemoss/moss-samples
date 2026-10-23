# vitepress-plugin-moss

A [VitePress](https://vitepress.dev) plugin that adds [Moss](https://moss.dev) semantic (AI) search to your docs. At build time it reads your Markdown source, chunks it, and uploads it to the Moss cloud. At runtime the search UI uses a **hot-path**: it queries the cloud immediately so search works from the very first keystroke, while the local model and index download in the background. Once ready, all queries automatically switch to sub-10 ms on-device search — no user action needed.

**Live demo:** [moss-samples-plugin.vercel.app](https://moss-samples-plugin.vercel.app/)

---

## How it works

```
Build time                                      Runtime (browser)
────────────────────────────────────────────    ──────────────────────────────────────
VitePress calls buildEnd hook                   User presses Ctrl/⌘+K or /
    ↓                                               ↓
mossIndexerPlugin reads siteConfig              Phase 1 — SDK imported, client created
    ↓                                           Queries routed to Moss cloud  ← hot-path
@moss-tools/md-indexer reads source .md             (instant results from first keystroke)
using VitePress's own markdown renderer             ↓  (parallel)
(understands includes, extensions, etc.)        Phase 2 — model + index download (background)
    ↓                                               ↓
Uploads via @moss-dev/moss MossClient          Index ready → queries switch to local < 10 ms
(upserts new docs, removes stale ones)              ↓
    ↓                                           Active query re-run with local index
Index is live on Moss cloud                     (seamless handoff, no user action needed)
```

Two separate npm packages are involved:
- **`@moss-dev/moss`** — Node.js SDK used **at build time** (inside `@moss-tools/md-indexer`) to upload documents
- **`@moss-dev/moss-web`** — WebAssembly browser SDK used **at runtime** to download the index and run local queries

---

## Installation

```bash
npm install vitepress-plugin-moss
# or
pnpm add vitepress-plugin-moss
# or
yarn add vitepress-plugin-moss
```

> **Requirement:** your project's `package.json` must have `"type": "module"` because VitePress is ESM-only.

---

## Setup

### 1. Configure VitePress

The plugin is easy to integrate using the `vite.plugins` option in your VitePress config. This handles both the search configuration and the build-time indexing automatically.

```ts
// docs/.vitepress/config.ts
import { defineConfig } from 'vitepress'
import { mossIndexerPlugin } from 'vitepress-plugin-moss'

export default defineConfig({
  title: 'My Docs',
  themeConfig: {
    search: {
      provider: 'moss' as any,
      options: {
        projectId: process.env.MOSS_PROJECT_ID!,
        projectKey: process.env.MOSS_PROJECT_KEY!,
        indexName: 'my-docs',
      },
    },
  },
  vite: {
    plugins: [mossIndexerPlugin()]
  }
})
```

Once integrated via `vite.plugins`, the Moss search component will automatically replace the default VitePress search bar (Zero-Config UI).

The plugin activates only when `search.provider` is `'moss'`. If the provider is anything else, `mossIndexerPlugin` returns a no-op and `buildEnd` exits immediately.

### 2. Get your Moss credentials

1. Sign up at [moss.dev](https://moss.dev)
2. Create a project and note your **Project ID** and **API key**
3. Pass them via environment variables (see below)

### 3. Set environment variables

Never hard-code credentials in your config file.

```bash
# .env  ← add to .gitignore, never commit
MOSS_PROJECT_ID=your_project_id
MOSS_PROJECT_KEY=your_api_key
MOSS_INDEX_NAME=my-docs
```

> **Note:** `projectKey` ends up embedded in the client-side JavaScript bundle. Treat it as you would an Algolia search-only API key — use a key scoped to read/query operations only.

---

## Options reference

All options go under `themeConfig.search.options`:

```ts
{
  // Required
  projectId: string    // Moss project ID
  projectKey: string   // Moss API key
  indexName: string    // Name of the index to create/overwrite on every build

  // Optional — Search UI
  topK?: number        // Number of results to return (default: 10)
  placeholder?: string // Search input placeholder (default: 'Search docs...')
  buttonText?: string  // Nav bar button label (default: 'Search')
}
```

Indexing always runs on every `vitepress build` when the provider is `'moss'` — there is no `enabled` flag to toggle.

### Excluding a page from the index

Add `search: false` to the page's frontmatter:

```md
---
search: false
---
```

---

## Keyboard shortcuts

| Key | Action |
|-----|--------|
| `Ctrl+K` / `⌘+K` | Open / close search |
| `/` | Open search (when not focused on an input) |
| `↑` / `↓` | Navigate results |
| `↵` | Go to selected result |
| `Esc` | Close search |

---

## Build output

A successful build prints:

```
Moss Sync: Starting End-to-End Process
---------------------------------------

Step 1: Building Index in Memory...
Processing N pages...
✅ Index built in memory: N chunks generated

Step 2: Uploading to Moss...
  ✅ Deleted existing index "my-docs"
✅ Upload success! Index "my-docs" is live.

 Sync Successfully Completed!
```

If indexing fails (network error, bad credentials, etc.) the build **does not fail** — the error is logged and the rest of the VitePress build continues.

---

## Creating and Loading Indexes

### Automatic indexing on build

When you run `vitepress build`, the `mossIndexerPlugin` automatically builds and uploads the index to Moss at the end of the build. No extra step is needed — just make sure your credentials are set in environment variables.

### Manual indexing with `index:docs`

The demo site includes a standalone script for building and uploading the index without running a full VitePress build. This is useful when you update documentation content and want to refresh the index quickly.

```bash
# From demo-site/
pnpm index:docs                    # index the documentation/ folder (default)
pnpm index:docs docs               # index the docs/ folder instead
pnpm index:docs documentation --inspect   # preview chunks as JSON, no upload
```

The script:

1. Reads all `.md` files and chunks them using `@moss-tools/md-indexer`
2. Filters out chunks with 3 or fewer words (lone headings, empty sections, nav-only content)
3. Uploads the remaining chunks to your Moss index

The `--inspect` flag writes chunks to `.index-preview.json` and exits without uploading — useful for verifying index quality before committing to an upload.

---

## Testing Locally (Demo Site)

The repository includes a demo site in `demo-site/` with two VitePress sites:

- **`documentation/`** — full Moss SDK docs with Moss search enabled (recommended for testing)
- **`docs/`** — minimal site

### Step 1 — Build the plugin

From the repository root:

```bash
pnpm install
pnpm build
```

### Step 2 — Set up the demo site

```bash
cd demo-site
pnpm install
```

Create a `.env` file with your Moss credentials:

```bash
# demo-site/.env  (never commit this file)
MOSS_PROJECT_ID=your_project_id
MOSS_PROJECT_KEY=your_api_key
MOSS_INDEX_NAME=your_index_name
```

### Step 3 — Populate the index

Before starting the dev server, upload the documentation to your Moss index:

```bash
# From demo-site/
pnpm index:docs
```

You only need to re-run this when you add or change Markdown content.

### Step 4 — Start the dev server

```bash
pnpm documentation:dev
```

Open [http://localhost:5173](http://localhost:5173) and use `Ctrl/⌘+K` or `/` to test the search modal.

### Production build

```bash
pnpm docs:build     # builds docs/ site (also runs pnpm build in plugin root first)
pnpm docs:preview   # preview at http://localhost:4173
```

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| Build error: `"vitepress" resolved to an ESM file` | `package.json` missing `"type": "module"` | Add `"type": "module"` to your project's `package.json` |
| `Missing Moss configuration` error | `projectId`, `projectKey`, or `indexName` not set | Check environment variables and `themeConfig.search.options` |
| `Could not load search index` in browser | Index not built yet, or wrong credentials | Run `vitepress build` first; verify credentials |
| No results returned | Index is empty or query doesn't match | Check the Moss dashboard for your index contents |
| Page not indexed | Page has `search: false` in frontmatter | Remove the flag to include the page |
| Modal doesn't open | Keyboard shortcut conflict | Try clicking the nav button directly |

---

## Project structure

```
vitepress-plugin-moss/
├── index.ts          # mossIndexerPlugin — the main export; hooks into VitePress buildEnd
├── indexing.ts       # Re-exports buildJsonDocs + uploadDocuments from @moss-tools/md-indexer
├── Search.vue        # Search modal UI component (browser SDK)
├── SearchButton.vue  # Nav bar search button
├── types.ts          # MossSearchOptions interface + DefaultTheme module augmentation
├── vite.config.ts    # Build config for the plugin itself
├── tsconfig.json
└── package.json
```

### Dependency split

```
vitepress-plugin-moss
├── @moss-tools/md-indexer   ← build time only (Node.js)
│   ├── @moss-dev/moss           SDK for uploading to Moss cloud
│   ├── vitepress                uses resolveConfig + createMarkdownRenderer
│   └── cheerio / gray-matter   HTML parsing, frontmatter
└── @moss-dev/moss-web       ← runtime only (browser WebAssembly)
    └── Queries run locally after index is downloaded
```

---

## Running Tests

```bash
# Install dependencies
pnpm install

# Run unit tests
pnpm test

# Run tests with watch mode
pnpm test -- --watch
```

Tests are also run automatically in the CI pipeline.

---

## License

MIT
