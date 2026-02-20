export interface MossSearchOptions {
  /** Moss project ID */
  projectId: string
  /** Moss project API key */
  projectKey: string
  /** Name of the Moss index to use */
  indexName: string
  /** Number of results to return. Default: 10 */
  topK?: number
  /** Placeholder text in the search input. Default: 'Search docs...' */
  placeholder?: string
  /** Text shown on the nav search button. Default: 'Search' */
  buttonText?: string
}

declare module 'vitepress' {
  namespace DefaultTheme {
    interface Config {
      search?:
        | { provider: 'local'; options?: unknown }
        | { provider: 'algolia'; options?: unknown }
        | { provider: 'moss'; options?: MossSearchOptions }
    }
  }
}
