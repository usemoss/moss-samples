import { defineConfig } from 'vite';
import dts from 'vite-plugin-dts';

export default defineConfig({
  build: {
    lib: {
      entry: 'index.ts',
      formats: ['es', 'cjs'],
      fileName: (format) => `index.${format === 'es' ? 'js' : 'cjs'}`,
    },
    rollupOptions: {
      external: [
        'vite',
        'vitepress',
        'obug',
        '@moss-tools/md-indexer',
        'path',
        'fs',
        'url',
        'node:path',
        'node:fs',
        'node:url',
      ],
    },
  },
  plugins: [
    dts({ insertTypesEntry: true, rollupTypes: true }),
  ],
});
