# vitepress-plugin-moss

A [VitePress](https://vitepress.dev) plugin that adds [Moss](https://moss.dev) semantic (AI) search to your docs. At build time it reads your Markdown source, chunks it, and uploads it to the Moss cloud. At runtime the search UI downloads the index once and runs all queries locally in the browser — no round-trips on every keystroke.

---

## How it works

```
Build time                                      Runtime (browser)
────────────────────────────────────────────    ──────────────────────────────────────
VitePress calls buildEnd hook                   User presses Ctrl/⌘+K or /
    ↓                                               ↓
mossIndexerPlugin reads siteConfig              @inferedge/moss downloads the index
    ↓                                               ↓
@moss-tools/md-indexer reads source .md         Queries run locally < 10 ms
using VitePress's own markdown renderer             ↓
(understands includes, extensions, etc.)        Results navigate via metadata.navigation
    ↓                                           (pre-computed URL + anchor per chunk)
Uploads via @inferedge-rest/moss REST client
(deletes old index, then re-uploads chunks)
    ↓
Index is live on Moss cloud
```

Two separate npm packages are involved:
- **`@inferedge-rest/moss`** — Node.js REST client used **at build time** (inside `@moss-tools/md-indexer`) to upload documents
- **`@inferedge/moss`** — WebAssembly browser SDK used **at runtime** to download the index and run local queries

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

The plugin is invoked from VitePress's own `buildEnd` hook — it is **not** added to `vite.plugins`.

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
  async buildEnd(siteConfig) {
    const plugin = await mossIndexerPlugin(siteConfig)
    if (typeof plugin.buildEnd === 'function') {
      await (plugin.buildEnd as Function).call({ environment: { name: 'client' } })
    }
  },
})
```

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

## Testing the plugin locally

### Step 1 — Build the plugin

```bash
cd vitepress-plugin-moss
pnpm install
pnpm build
# dist/ is now populated
```

### Step 2 — Create a minimal test VitePress site

```bash
mkdir /tmp/test-docs && cd /tmp/test-docs
npm init -y
npm install vitepress
```

Add `"type": "module"` to the generated `package.json`:

```json
{
  "name": "test-docs",
  "type": "module",
  ...
}
```

Create some pages:

```bash
mkdir -p docs/.vitepress
echo "# Home\n\nThis is the home page." > docs/index.md
echo "# Guide\n\n## Installation\n\nRun npm install." > docs/guide.md
```

### Step 3 — Link the local plugin

```bash
# From inside /tmp/test-docs
npm install /path/to/vitepress-plugin-moss
```

### Step 4 — Configure VitePress

```ts
// docs/.vitepress/config.ts
import { defineConfig } from 'vitepress'
import { mossIndexerPlugin } from 'vitepress-plugin-moss'

export default defineConfig({
  title: 'Test Docs',
  themeConfig: {
    search: {
      provider: 'moss' as any,
      options: {
        projectId: process.env.MOSS_PROJECT_ID!,
        projectKey: process.env.MOSS_PROJECT_KEY!,
        indexName: 'test-docs',
      },
    },
  },
  async buildEnd(siteConfig) {
    const plugin = await mossIndexerPlugin(siteConfig)
    if (typeof plugin.buildEnd === 'function') {
      await (plugin.buildEnd as Function).call({ environment: { name: 'client' } })
    }
  },
})
```

### Step 5 — Run the build

```bash
cd /tmp/test-docs
MOSS_PROJECT_ID=xxx MOSS_PROJECT_KEY=yyy npx vitepress build docs
```

You should see the indexing output described in [Build output](#build-output) above.

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
│   ├── @inferedge-rest/moss     REST client for uploading to Moss cloud
│   ├── vitepress                uses resolveConfig + createMarkdownRenderer
│   └── cheerio / gray-matter   HTML parsing, frontmatter
└── @inferedge/moss          ← runtime only (browser WebAssembly)
    └── Queries run locally after index is downloaded
```

---

## License

MIT
