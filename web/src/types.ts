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

// Envelope chung của API quản trị (AD-13): {results, meta}
export interface ListMeta {
  total: number
  limit: number
  offset: number
}

export interface ListResponse<T> {
  results: T[]
  meta: ListMeta
}

export interface VideoRow {
  video_id: string
  name: string
  framerate: number | null
  created_at: string | null
  scene_count: number
  indexed_count: number
  pending_count: number
}

export interface JobRow {
  job_id: string
  kind: string
  status: string
  created_at: string | null
  total: number
  done: number
  queued: number
  claimed: number
  skipped: number
  error: number
}

export interface TaskRow {
  task_id: string
  job_id: string
  name: string
  status: string
  reason: string | null
  attempts: number
  video_id: string | null
  claimed_at: string | null
  finished_at: string | null
  created_at: string | null
}

export interface Metrics {
  queue_depth: number
  ingest_throughput_per_min: number
  job_error_rate: number
  window_seconds: number
}

export interface MetricsResponse {
  results: unknown[]
  meta: Metrics
}

export interface RequeueResult {
  job_id: string | null
  requeued: number
  skipped: number
  matched?: number
}

export interface RequeueResponse {
  results: unknown[]
  meta: RequeueResult
}
