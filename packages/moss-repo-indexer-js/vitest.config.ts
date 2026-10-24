import path from 'node:path'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  test: {
    include: ['test/**/*.test.ts'],
  },
  resolve: {
    alias: {
      '@moss-tools/repo-indexer': path.resolve('src/index.ts'),
    },
  },
})
