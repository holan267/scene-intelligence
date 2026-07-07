// Khớp envelope search (AD-13, search/rank.py::build_envelope)
export interface SearchResult {
  scene_id: string
  video_id: string
  start_ms: number
  end_ms: number
  score: number
  thumbnail_url: string
  highlights: string[]
}

export interface SearchResponse {
  results: SearchResult[]
  meta: { next_cursor: string | null; count: number }
}
