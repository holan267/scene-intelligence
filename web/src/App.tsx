import { useRef, useState, type FormEvent } from 'react'
import './App.css'
import type { SearchResponse, SearchResult } from './types'

// Story 3.1: tìm kiếm NL + preview Scene (rê/bấm) qua <video> timecode fragment.
// Ngoài phạm vi: lọc (Story 2.3 filters UI), tải clip (3.2), cảnh giống cảnh này (3.3),
// đánh dấu đã dùng (3.4).
function App() {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<SearchResult[]>([])
  const [previewId, setPreviewId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  // Review fix: guard thứ tự request — response chậm của query cũ không được ghi
  // đè kết quả của query mới hơn (chỉ áp dụng kết quả nếu vẫn là request mới nhất).
  const latestRequest = useRef(0)

  async function handleSearch(e: FormEvent) {
    e.preventDefault()
    if (!query.trim()) return
    const requestId = ++latestRequest.current
    setError(null)
    try {
      const res = await fetch('/api/v1/search', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query }),
      })
      if (requestId !== latestRequest.current) return // có query mới hơn đã gửi sau
      if (!res.ok) {
        setError(`Tìm kiếm lỗi (${res.status})`)
        return
      }
      const body: SearchResponse = await res.json()
      setResults(body.results)
    } catch {
      if (requestId === latestRequest.current) {
        setError('Không gọi được API tìm kiếm')
      }
    }
  }

  function togglePreview(sceneId: string) {
    // Review fix: click để bật/tắt preview — cần cho thiết bị cảm ứng (không có hover).
    setPreviewId((cur) => (cur === sceneId ? null : sceneId))
  }

  return (
    <div className="app">
      <h1>Scene Intelligence</h1>
      <form onSubmit={handleSearch} className="search-form">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Gõ câu mô tả cảnh cần tìm..."
        />
        <button type="submit">Tìm</button>
      </form>
      {error && <p className="error">{error}</p>}
      <div className="results">
        {results.map((r) => (
          <div
            key={r.scene_id}
            className="result-card"
            onMouseEnter={() => setPreviewId(r.scene_id)}
            onMouseLeave={() => setPreviewId((cur) => (cur === r.scene_id ? null : cur))}
            onClick={() => togglePreview(r.scene_id)}
          >
            {previewId === r.scene_id ? (
              <video
                src={`/api/v1/videos/${r.video_id}/stream#t=${r.start_ms / 1000},${r.end_ms / 1000}`}
                autoPlay
                muted
                loop
                playsInline
                onError={() => setPreviewId(null)}
                className="preview-video"
              />
            ) : (
              <img
                src={r.thumbnail_url}
                alt=""
                className="thumbnail"
                onError={(e) => {
                  e.currentTarget.style.visibility = 'hidden'
                }}
              />
            )}
            <div className="meta">
              <span>{Math.round(r.score * 100)}%</span>
              {r.highlights.length > 0 && <span className="highlight">{r.highlights[0]}</span>}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

export default App
