/** Local document shape matching Moss DocumentInfo (id/text/metadata). */
export interface RepoDocument {
  id: string
  text: string
  metadata?: Record<string, string>
}
