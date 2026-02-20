// Build-time indexing is delegated entirely to @moss-tools/md-indexer which:
//  - uses VitePress's own createMarkdownRenderer (understands includes, extensions, frontmatter)
//  - uses @inferedge-rest/moss MossRestClient for uploading
//  - produces richer metadata: navigation, displayBreadcrumb, type, groupId/groupTitle
//
// This file re-exports only what index.ts needs so it stays the single import point.

export { buildJsonDocs, uploadDocuments } from '@moss-tools/md-indexer'
export type { MossDocument, MossCreds } from '@moss-tools/md-indexer'
