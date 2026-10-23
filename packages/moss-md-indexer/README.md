# Moss MD Indexer

A library for building and uploading search indexes from documentation to Moss.

## Installation

```bash
pnpm add @moss-tools/md-indexer
```

## Setup

Create a `.env` file in your project root with the following environment variables (or pass them via options):

```env
MOSS_PROJECT_ID=your-project-id
MOSS_PROJECT_KEY=your-project-key
MOSS_INDEX_NAME=your-index-name
MOSS_MODEL_NAME=moss-minilm  # Optional, defaults to 'moss-minilm'
```

## Usage

This package exports the following functions:

### `sync`

Builds the search index in memory and uploads it to Moss.

```typescript
import { sync } from '@moss-tools/md-indexer'

// Basic usage (uses defaults and .env variables)
await sync()

// Custom configuration
await sync({
  root: './src/docs', // Path to your docs directory
  creds: {
    projectId: 'your-project-id',
    projectKey: 'your-project-key',
    indexName: 'your-index-name',
    modelName: 'moss-minilm' // Optional
  }
})
```

### `buildJsonDocs`

Builds the search index programmatically.

```typescript
import { buildJsonDocs } from '@moss-tools/md-indexer'

const docsPath = './src/docs'
const outputFile = './search-index.json'

// Build the index and save to a file
await buildJsonDocs(docsPath, { outputFile })

// Build the index in memory
const documents = await buildJsonDocs(docsPath)
```

### `createIndex`

Uploads an existing index file to Moss. Use this function when you already have a pre-built index file (e.g., generated using `buildJsonDocs`) and want to upload it to Moss.

```typescript
import { createIndex } from '@moss-tools/md-indexer'

const outputFile = './search-index.json'
const creds = {
  projectId: 'your-project-id',
  projectKey: 'your-project-key',
  indexName: 'your-index-name',
  modelName: 'moss-minilm' // Optional
}

// Upload the pre-built index file to Moss
await createIndex(outputFile, { creds })
```

## VitePress Configuration

The indexer uses `vp.resolveConfig()` to load your VitePress configuration. The behavior depends on whether a config file exists:

### Case 1: VitePress Config File Present

If a VitePress config file exists (e.g., `.vitepress/config.ts` or `.vitepress/config.js`), the indexer will:

- Load the configuration from that file
- Use the `srcDir` specified in the config (or default to the directory containing the config)
- Respect all VitePress settings (markdown options, base path, etc.)
- Process all pages found by VitePress

**Example structure:**

```text
docs/
  .vitepress/
    config.ts          # VitePress config file
  index.md
  guide.md
```

**Example config:**

```typescript
// docs/.vitepress/config.ts
import { defineConfig } from 'vitepress'

export default defineConfig({
  title: 'My Documentation',
  description: 'Documentation site',
  srcDir: '.',  // or specify a different directory
  // ... other VitePress config options
})
```

### Case 2: VitePress Config File Not Present

If no VitePress config file is found, VitePress will automatically:

- Use **zero-config defaults** - it treats the provided directory as the source root
- Auto-discover all `.md` files in that directory
- Apply default VitePress settings (base path, markdown options, etc.)

**This means you can use the indexer without creating a config file** if you have a simple documentation structure:

```text
docs/
  index.md
  guide.md
  api-reference.md
```

The indexer will successfully process all markdown files found in the `docs` directory.

**However**, if `resolveConfig` fails to resolve any configuration (e.g., invalid directory path), it will throw an error: `Could not resolve VitePress config in <path>`.

**For more control**, you can create a VitePress config file. The indexer looks for the config in:

1. The root directory you pass to `sync()` (e.g., `./docs/.vitepress/config.ts`)
2. Or at the project root if your docs folder is the VitePress root

**Minimal config example:**

```typescript
// docs/.vitepress/config.ts
import { defineConfig } from 'vitepress'

export default defineConfig({
  title: 'Documentation',
  srcDir: '.',  // Points to the docs directory
})
```

## Requirements

- Node.js (v20.4 or higher)
- VitePress (^1.0.0) - peer dependency

## Development

```bash
# Build the project
pnpm build

# Watch mode for development
pnpm dev
```
