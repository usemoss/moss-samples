export { resolveSource, isGitUrl, repoNameFromUrl, type ResolvedSource } from './clone.js'
export { discoverFiles } from './discover.js'
export { buildDocuments } from './documents.js'
export { chunkCode, chunkMarkdown, type FileChunkRequest } from './chunkers/index.js'
export { uploadDocuments, type UploadOptions, type MutationResultLike } from './uploader.js'
export { sync, type SyncResult } from './sync.js'
export type { RepoDocument } from './document.js'
export {
  CHUNK_TYPE_CODE,
  CHUNK_TYPE_HEADER,
  CHUNK_TYPE_MARKDOWN,
  CHUNK_TYPE_PAGE,
  CHUNK_TYPE_TEXT,
  DEFAULT_EXCLUDE_DIRS,
  DEFAULT_INCLUDE_GLOBS,
  DEFAULT_MODEL_NAME,
  metadataContract,
  type IndexOptions,
  type MossCreds,
  type SyncOptions,
} from './types.js'
