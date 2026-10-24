/** Shared credentials, options, and document metadata contract (mirrors Python). */

export const METADATA_PATH = 'path'
export const METADATA_LANGUAGE = 'language'
export const METADATA_TYPE = 'type'
export const METADATA_START_LINE = 'start_line'
export const METADATA_END_LINE = 'end_line'
export const METADATA_SYMBOL = 'symbol'
export const METADATA_REPO = 'repo'
export const METADATA_REF = 'ref'
export const METADATA_TITLE = 'title'
export const METADATA_NAVIGATION = 'navigation'

export const CHUNK_TYPE_CODE = 'code'
export const CHUNK_TYPE_MARKDOWN = 'markdown'
export const CHUNK_TYPE_HEADER = 'header'
export const CHUNK_TYPE_TEXT = 'text'
export const CHUNK_TYPE_PAGE = 'page'

export const DEFAULT_MODEL_NAME = 'moss-minilm'

export const DEFAULT_INCLUDE_GLOBS = [
  '**/*.py',
  '**/*.ts',
  '**/*.tsx',
  '**/*.js',
  '**/*.jsx',
  '**/*.go',
  '**/*.rs',
  '**/*.java',
  '**/*.md',
  '**/*.mdx',
]

export const DEFAULT_EXCLUDE_DIRS = [
  '.git',
  'node_modules',
  'vendor',
  'dist',
  'build',
  '__pycache__',
  '.venv',
  'venv',
  '.pytest_cache',
  '.ruff_cache',
  '.mypy_cache',
]

export interface MossCreds {
  projectId: string
  projectKey: string
  indexName: string
  modelName?: string
}

export interface IndexOptions {
  includeGlobs?: string[]
  excludeDirs?: string[]
  respectGitignore?: boolean
  ref?: string
  maxFileBytes?: number
  repoName?: string
}

export interface SyncOptions {
  source: string
  creds: MossCreds
  index?: IndexOptions
  dryRun?: boolean
  upsert?: boolean
  /** Opt-in destructive recreate (delete index then create). */
  replace?: boolean
}

export function metadataContract(): Record<string, string> {
  return {
    [METADATA_PATH]: 'Repository-relative file path',
    [METADATA_LANGUAGE]: 'Language id (python, typescript, markdown, ...)',
    [METADATA_TYPE]: 'Chunk kind: code | markdown | header | text | page',
    [METADATA_START_LINE]: '1-based start line (string)',
    [METADATA_END_LINE]: '1-based end line (string)',
    [METADATA_SYMBOL]: 'Optional symbol or heading name',
    [METADATA_REPO]: 'Optional repository name or URL',
    [METADATA_REF]: 'Optional git ref / branch',
    [METADATA_TITLE]: 'Display title (symbol, heading, or basename)',
    [METADATA_NAVIGATION]: 'Editor/UI target, e.g. path:startLine',
  }
}

export function resolveIndexOptions(options: IndexOptions = {}): Required<
  Pick<IndexOptions, 'includeGlobs' | 'excludeDirs' | 'respectGitignore' | 'maxFileBytes'>
> &
  IndexOptions {
  return {
    includeGlobs: options.includeGlobs ?? [...DEFAULT_INCLUDE_GLOBS],
    excludeDirs: options.excludeDirs ?? [...DEFAULT_EXCLUDE_DIRS],
    respectGitignore: options.respectGitignore ?? true,
    maxFileBytes: options.maxFileBytes ?? 1_000_000,
    ref: options.ref,
    repoName: options.repoName,
  }
}
