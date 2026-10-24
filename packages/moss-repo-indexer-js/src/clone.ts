import { spawnSync } from 'node:child_process'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'

const GIT_SSH_RE = /^git@[^:]+:.+\.git$/
const GIT_URL_RE = /^(https?|git):\/\//i

export interface ResolvedSource {
  root: string
  repoName: string
  ref?: string
  cleanup: boolean
  close: () => void
}

export function resolveSource(source: string, ref?: string): ResolvedSource {
  const stripped = source.trim()
  if (isGitUrl(stripped)) {
    return cloneGitUrl(stripped, ref)
  }
  return resolveLocalPath(stripped, ref)
}

export function isGitUrl(source: string): boolean {
  if (GIT_SSH_RE.test(source) || GIT_URL_RE.test(source)) {
    return true
  }
  return source.endsWith('.git') && source.includes('://')
}

export function repoNameFromUrl(url: string): string {
  let name = GIT_SSH_RE.test(url) ? url.split(':').pop() ?? url : new URL(url).pathname
  name = path.basename(name)
  if (name.endsWith('.git')) {
    name = name.slice(0, -4)
  }
  return name || 'repo'
}

function resolveLocalPath(source: string, ref?: string): ResolvedSource {
  const root = path.resolve(source)
  if (!fs.existsSync(root) || !fs.statSync(root).isDirectory()) {
    throw new Error(`Source path is not a directory: ${root}`)
  }
  return {
    root,
    repoName: path.basename(root),
    ref,
    cleanup: false,
    close: () => undefined,
  }
}

function cloneGitUrl(url: string, ref?: string): ResolvedSource {
  if (!hasGit()) {
    throw new Error('git is required to clone a repository URL')
  }
  const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'moss-repo-'))
  try {
    runGitClone(url, tempDir, ref)
  } catch (error) {
    fs.rmSync(tempDir, { recursive: true, force: true })
    throw error
  }
  return {
    root: tempDir,
    repoName: repoNameFromUrl(url),
    ref,
    cleanup: true,
    close: () => {
      fs.rmSync(tempDir, { recursive: true, force: true })
    },
  }
}

function hasGit(): boolean {
  return spawnSync('git', ['--version'], { encoding: 'utf8' }).status === 0
}

function runGitClone(url: string, dest: string, ref?: string): void {
  const args = ['clone', '--depth', '1']
  if (ref) {
    args.push('--branch', ref)
  }
  args.push(url, dest)
  const result = spawnSync('git', args, { encoding: 'utf8' })
  if (result.status !== 0) {
    const detail = (result.stderr || result.stdout || 'git clone failed').trim()
    throw new Error(`Failed to clone ${url}: ${detail}`)
  }
}
