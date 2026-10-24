import path from 'node:path'

const EXTENSION_LANGUAGE: Record<string, string> = {
  '.py': 'python',
  '.ts': 'typescript',
  '.tsx': 'typescript',
  '.js': 'javascript',
  '.jsx': 'javascript',
  '.go': 'go',
  '.rs': 'rust',
  '.java': 'java',
  '.md': 'markdown',
  '.mdx': 'markdown',
}

const MARKDOWN_EXTENSIONS = new Set(['.md', '.mdx'])

export function languageForPath(filePath: string): string {
  return EXTENSION_LANGUAGE[path.extname(filePath).toLowerCase()] ?? 'text'
}

export function isMarkdownPath(filePath: string): boolean {
  return MARKDOWN_EXTENSIONS.has(path.extname(filePath).toLowerCase())
}
