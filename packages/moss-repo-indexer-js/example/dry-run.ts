/**
 * Dry-run a local path into Moss document chunks (no upload).
 *
 *   pnpm example:dry-run
 *   pnpm exec tsx example/dry-run.ts /path/to/repo
 */
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { sync } from '../src/index.js'

const here = path.dirname(fileURLToPath(import.meta.url))
const source = process.argv[2] ?? path.resolve(here, '..')

const result = await sync({
  source,
  creds: {
    projectId: 'unused-in-dry-run',
    projectKey: 'unused-in-dry-run',
    indexName: 'repo-dry-run',
  },
  dryRun: true,
})

console.log(`repo=${result.repoName} chunks=${result.documents.length} dryRun=${result.dryRun}`)
for (const doc of result.documents.slice(0, 5)) {
  const meta = doc.metadata ?? {}
  console.log(`- ${doc.id} [${meta.type}] ${meta.navigation}`)
}
if (result.documents.length > 5) {
  console.log(`... and ${result.documents.length - 5} more`)
}
