import { createDebug } from 'obug'
import type { Plugin } from 'vite'
import type { SiteConfig, DefaultTheme } from 'vitepress'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import fs from 'node:fs'

export type { MossSearchOptions } from './types.js'

const debug = createDebug('vitepress:moss-indexer')
const __dirname = path.dirname(fileURLToPath(import.meta.url))

const charMap: Record<string, string> = {
  '<': '\\u003C',
  '>': '\\u003E',
  '/': '\\u002F',
  '\\': '\\\\',
  '\b': '\\b',
  '\f': '\\f',
  '\n': '\\n',
  '\r': '\\r',
  '\t': '\\t',
  '\0': '\\0',
  '\u2028': '\\u2028',
  '\u2029': '\\u2029'
}

function escapeUnsafeChars(str: string): string {
  return str.replace(/[<>/\\\b\f\n\r\t\0\u2028\u2029]/g, x => charMap[x] ?? x)
}

export function mossIndexerPlugin(): Plugin {
  const virtualModuleId = 'virtual:moss-config'
  const resolvedVirtualModuleId = '\0' + virtualModuleId
  let siteConfig: SiteConfig<DefaultTheme.Config>

  return {
    name: 'vitepress:moss-indexer',
    enforce: 'pre',
    resolveId(id) {
      if (id === virtualModuleId) {
        return resolvedVirtualModuleId
      }
      
      // Shadowing components
      if (id.endsWith('/VPNavBarSearch.vue') || id === './VPNavBarSearch.vue') {
        const replacement = path.resolve(__dirname, '..', 'Search.vue')
        if (fs.existsSync(replacement)) {
          return replacement
        }
      }
      if (id.endsWith('/VPNavBarSearchButton.vue') || id === './VPNavBarSearchButton.vue') {
        const replacement = path.resolve(__dirname, '..', 'SearchButton.vue')
        if (fs.existsSync(replacement)) {
          return replacement
        }
      }
    },
    configResolved(config) {
      siteConfig = (config as any).vitepress
    },
    load(id) {
      if (id === resolvedVirtualModuleId) {
        // If siteConfig isn't available yet or search isn't moss, return empty config
        const searchConfig = siteConfig?.site?.themeConfig?.search as any
        if (searchConfig?.provider !== 'moss') {
          return 'export default () => ({})'
        }
        const searchOptions = searchConfig.options || {}
        return `export default () => (${escapeUnsafeChars(JSON.stringify(searchOptions))})`
      }
    },
    async buildEnd() {
      // Only run when siteConfig is available and Moss search is enabled
      const searchConfig = siteConfig.site.themeConfig?.search as any
      if (!siteConfig || searchConfig?.provider !== 'moss') {
        return
      }

      // Only run for client build and only during production build
      // NOTE: environment.name is used in newer Vite/VitePress
      try {
        debug('Starting Moss index sync...')

        const searchConfig = siteConfig.site.themeConfig?.search as any
        const searchOptions =
          searchConfig?.provider === 'moss' ? searchConfig.options : undefined

        // Get credentials from config options only
        const projectId = searchOptions?.projectId
        const projectKey = searchOptions?.projectKey
        const indexName = searchOptions?.indexName
        const recreate = searchOptions?.recreate ?? false

        // Validate required credentials
        if (!projectId || !projectKey || !indexName) {
          throw new Error(
            'Missing Moss configuration: projectId, projectKey, and indexName must be provided in themeConfig.search.options. ' +
              'Example: search: { provider: "moss", options: { projectId: "...", projectKey: "...", indexName: "..." } }'
          )
        }

        const creds = {
          projectId,
          projectKey,
          indexName
        }

        const mdIndexer = await import('@moss-tools/md-indexer')
        const buildJsonDocs = mdIndexer.buildJsonDocs
        const uploadDocuments = mdIndexer.uploadDocuments

        // Build chunks
        const allDocs = await buildJsonDocs(siteConfig.root) as any[]
        debug(`Built ${allDocs.length} chunks`)

        // Filter: remove chunks with 3 or fewer words
        const wordFiltered = allDocs.filter((doc: any) => {
          const wordCount = doc.text?.trim().split(/\s+/).filter(Boolean).length ?? 0
          return wordCount > 3
        })

        // Filter: remove structural-only section headings
        const STRUCTURAL_TITLES = new Set(['Parameters', 'Constructors', 'Methods', 'Properties', 'Type declaration'])
        const structuralFiltered = wordFiltered.filter((doc: any) => {
          const title: string = (doc.metadata?.title ?? '').trim().replace(/\u200b/g, '').trim()
          return !STRUCTURAL_TITLES.has(title)
        })

        // Deduplicate: keep only the first chunk per (groupId, title)
        const seen = new Set<string>()
        const filtered = structuralFiltered.filter((doc: any) => {
          const key = `${doc.metadata?.groupId ?? ''}||${doc.metadata?.title ?? ''}`
          if (seen.has(key)) return false
          seen.add(key)
          return true
        })

        debug(`After filtering: ${filtered.length} chunks (removed ${allDocs.length - filtered.length})`)

        await uploadDocuments(filtered, { ...creds, modelName: 'moss-minilm' }, { recreate })

        debug('Moss index sync completed.')
      } catch (error) {
        const err = error as Error
        siteConfig.logger.error(
          `Moss index sync failed: ${err.message}\n` +
            'The documentation build will continue without an updated Moss index.'
        )
        debug('Moss index sync error', err)
      }
    },
    async closeBundle() {
      await (this as any).buildEnd?.()
    }
  }
}
