import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'

import { afterEach, describe, expect, it, vi } from 'vitest'

import { isGitUrl, repoNameFromUrl, resolveSource } from '../src/clone.js'
import { discoverFiles } from '../src/discover.js'
import { buildDocuments } from '../src/documents.js'
import { chunkCode, chunkMarkdown } from '../src/chunkers/index.js'
import { sync } from '../src/sync.js'
import { metadataContract } from '../src/types.js'

const temps: string[] = []

afterEach(() => {
  for (const dir of temps.splice(0)) {
    fs.rmSync(dir, { recursive: true, force: true })
  }
  vi.restoreAllMocks()
})

function makeRepo(): string {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'moss-repo-test-'))
  temps.push(root)
  fs.mkdirSync(path.join(root, 'src'))
  fs.writeFileSync(path.join(root, 'src', 'app.py'), 'class AuthMiddleware:\n    pass\n' + '    # pad\n'.repeat(80))
  fs.writeFileSync(path.join(root, 'README.md'), '# Install\n\nRun npm.\n\n## Setup\n\nEnv.\n')
  fs.mkdirSync(path.join(root, 'node_modules'))
  fs.writeFileSync(path.join(root, 'node_modules', 'x.js'), 'export default 1\n')
  fs.writeFileSync(path.join(root, 'notes.txt'), 'skip\n')
  return root
}

describe('clone helpers', () => {
  it('detects git urls and names', () => {
    expect(isGitUrl('https://github.com/org/repo.git')).toBe(true)
    expect(isGitUrl('git@github.com:org/repo.git')).toBe(true)
    expect(isGitUrl('/local/path')).toBe(false)
    expect(repoNameFromUrl('https://github.com/org/cool-repo.git')).toBe('cool-repo')
  })

  it('resolves local path', () => {
    const root = makeRepo()
    const resolved = resolveSource(root)
    expect(resolved.cleanup).toBe(false)
    expect(resolved.repoName).toBe(path.basename(root))
  })
})

describe('discover + chunk', () => {
  it('filters files and builds documents', () => {
    const root = makeRepo()
    const files = discoverFiles(root)
    const rels = files.map((f) => path.relative(root, f).split(path.sep).join('/')).sort()
    expect(rels).toEqual(['README.md', 'src/app.py'])

    const docs = buildDocuments(root, { repoName: 'demo' })
    expect(docs.length).toBeGreaterThan(2)
    expect(docs.every((d) => d.metadata?.repo === 'demo')).toBe(true)
    expect(docs.some((d) => d.metadata?.type === 'page')).toBe(true)
    expect(docs.some((d) => d.metadata?.symbol === 'AuthMiddleware')).toBe(true)
  })

  it('chunks markdown and code directly', () => {
    const root = makeRepo()
    const md = chunkMarkdown({
      path: path.join(root, 'README.md'),
      root,
      content: fs.readFileSync(path.join(root, 'README.md'), 'utf8'),
      language: 'markdown',
    })
    expect(md[0].id).toBe('README.md')
    const code = chunkCode({
      path: path.join(root, 'src', 'app.py'),
      root,
      content: fs.readFileSync(path.join(root, 'src', 'app.py'), 'utf8'),
      language: 'python',
    })
    expect(code[0].metadata?.type).toBe('code')
  })
})

describe('sync dry-run', () => {
  it('returns chunks without uploading', async () => {
    const root = makeRepo()
    const result = await sync({
      source: root,
      creds: { projectId: 'p', projectKey: 'k', indexName: 'idx' },
      dryRun: true,
    })
    expect(result.dryRun).toBe(true)
    expect(result.mutation).toBeUndefined()
    expect(result.documents.length).toBeGreaterThan(0)
  })
})

describe('metadata contract', () => {
  it('exposes shared keys', () => {
    expect(Object.keys(metadataContract())).toContain('path')
    expect(Object.keys(metadataContract())).toContain('navigation')
  })
})
