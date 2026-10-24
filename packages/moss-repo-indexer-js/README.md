# @moss-tools/repo-indexer

Clone or walk a repository, chunk **code** and **Markdown**, and build a searchable Moss index.

TypeScript twin of the Python package [`moss-repo-indexer`](../moss-repo-indexer). Both emit the same `DocumentInfo` metadata contract.

## Install

```bash
npm install @moss-tools/repo-indexer @moss-dev/moss
```

## Usage

```ts
import { buildDocuments, sync } from '@moss-tools/repo-indexer'

const docs = buildDocuments('./my-repo', { repoName: 'my-repo' })

const dry = await sync({
  source: './my-repo', // or https://github.com/org/repo.git
  creds: {
    projectId: process.env.MOSS_PROJECT_ID!,
    projectKey: process.env.MOSS_PROJECT_KEY!,
    indexName: 'my-codebase',
  },
  dryRun: true,
})

const uploaded = await sync({
  source: './my-repo',
  creds: {
    projectId: process.env.MOSS_PROJECT_ID!,
    projectKey: process.env.MOSS_PROJECT_KEY!,
    indexName: 'my-codebase',
  },
})

// Destructive recreate (opt-in)
await sync({
  source: './my-repo',
  creds: {
    projectId: process.env.MOSS_PROJECT_ID!,
    projectKey: process.env.MOSS_PROJECT_KEY!,
    indexName: 'my-codebase',
  },
  replace: true,
})
```

## Document metadata contract

Same keys as the Python package (`path`, `language`, `type`, `start_line`, `end_line`, `symbol`, `repo`, `ref`, `title`, `navigation`). See `metadataContract()`.

## Scripts

```bash
pnpm install
pnpm test
pnpm build
pnpm example:dry-run
```
