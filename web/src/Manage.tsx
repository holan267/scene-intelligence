import { useCallback, useEffect, useState } from 'react'
import type {
  JobRow,
  ListResponse,
  MetricsResponse,
  RequeueResponse,
  TaskRow,
  VideoRow,
} from './types'

const POLL_MS = 5000

async function getJson<T>(url: string): Promise<T> {
  const res = await fetch(url)
  if (!res.ok) throw new Error(`${res.status}`)
  return (await res.json()) as T
}

function shortId(id: string): string {
  return id.slice(0, 8)
}

function fmtDate(value: string | null): string {
  if (!value) return '—'
  const d = new Date(value)
  return Number.isNaN(d.getTime()) ? '—' : d.toLocaleString('vi-VN')
}

function StatusBadge({ status }: { status: string }) {
  return <span className={`badge badge-${status}`}>{status}</span>
}

// Giao diện quản lý kho: video + ingest status, requeue task lỗi/bỏ-qua từ UI.
// Tự làm mới mỗi 5s để thấy tiến độ worker; mọi thao tác đi qua REST /api/v1 (AD-13).
function Manage() {
  const [videos, setVideos] = useState<VideoRow[]>([])
  const [jobs, setJobs] = useState<JobRow[]>([])
  const [tasks, setTasks] = useState<TaskRow[]>([])
  const [metrics, setMetrics] = useState<MetricsResponse['meta'] | null>(null)
  const [statusFilter, setStatusFilter] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const reload = useCallback(async () => {
    const query = statusFilter ? `&status=${statusFilter}` : ''
    try {
      const [v, j, t, m] = await Promise.all([
        getJson<ListResponse<VideoRow>>('/api/v1/videos?limit=100'),
        getJson<ListResponse<JobRow>>('/api/v1/jobs?limit=50'),
        getJson<ListResponse<TaskRow>>(`/api/v1/ingest/tasks?limit=100${query}`),
        getJson<MetricsResponse>('/api/v1/metrics'),
      ])
      setVideos(v.results)
      setJobs(j.results)
      setTasks(t.results)
      setMetrics(m.meta)
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? `Không tải được dữ liệu (${e.message})` : 'Không tải được dữ liệu')
    }
  }, [statusFilter])

  useEffect(() => {
    reload()
    const timer = setInterval(reload, POLL_MS)
    return () => clearInterval(timer)
  }, [reload])

  async function requeue(url: string, body?: unknown) {
    setBusy(true)
    setMessage(null)
    try {
      const res = await fetch(url, {
        method: 'POST',
        headers: body ? { 'Content-Type': 'application/json' } : undefined,
        body: body ? JSON.stringify(body) : undefined,
      })
      if (!res.ok) {
        setError(`Requeue lỗi (${res.status})`)
        return
      }
      const data: RequeueResponse = await res.json()
      setMessage(
        `Đã requeue ${data.meta.requeued} task` +
          (data.meta.skipped ? `, bỏ qua ${data.meta.skipped} task đang chạy/chờ` : ''),
      )
      await reload()
    } catch {
      setError('Không gọi được API requeue')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="manage">
      <div className="metrics-bar">
        <div className="metric">
          <span className="metric-value">{metrics?.queue_depth ?? '—'}</span>
          <span className="metric-label">Đang chờ</span>
        </div>
        <div className="metric">
          <span className="metric-value">{metrics ? metrics.ingest_throughput_per_min.toFixed(1) : '—'}</span>
          <span className="metric-label">Task/phút</span>
        </div>
        <div className="metric">
          <span className="metric-value">{metrics ? `${Math.round(metrics.job_error_rate * 100)}%` : '—'}</span>
          <span className="metric-label">Tỷ lệ lỗi</span>
        </div>
      </div>

      <div className="toolbar">
        <button disabled={busy} onClick={() => requeue('/api/v1/ingest/requeue-failed')}>
          Requeue tất cả lỗi
        </button>
        <button disabled={busy} onClick={() => reload()}>
          Làm mới
        </button>
        {message && <span className="notice">{message}</span>}
        {error && <span className="error">{error}</span>}
      </div>

      <h2>Ingest jobs</h2>
      <table className="data-table">
        <thead>
          <tr>
            <th>Job</th>
            <th>Loại</th>
            <th>Trạng thái</th>
            <th>Tiến độ</th>
            <th>Tạo lúc</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {jobs.map((job) => {
            const failed = job.error + job.skipped
            return (
              <tr key={job.job_id}>
                <td title={job.job_id}>{shortId(job.job_id)}</td>
                <td>{job.kind}</td>
                <td>
                  <StatusBadge status={job.status} />
                </td>
                <td>
                  {job.done}/{job.total} xong
                  {failed > 0 && <span className="error"> · {failed} lỗi</span>}
                  {job.queued + job.claimed > 0 && ` · ${job.queued + job.claimed} đang chờ`}
                </td>
                <td>{fmtDate(job.created_at)}</td>
                <td>
                  {failed > 0 ? (
                    <button disabled={busy} onClick={() => requeue(`/api/v1/jobs/${job.job_id}/requeue`, {})}>
                      Requeue lỗi
                    </button>
                  ) : job.done > 0 ? (
                    <button
                      disabled={busy}
                      onClick={() => requeue(`/api/v1/jobs/${job.job_id}/requeue`, { include_done: true })}
                    >
                      Chạy lại
                    </button>
                  ) : null}
                </td>
              </tr>
            )
          })}
          {jobs.length === 0 && (
            <tr>
              <td colSpan={6}>Chưa có job nào.</td>
            </tr>
          )}
        </tbody>
      </table>

      <h2>Tasks</h2>
      <div className="toolbar">
        <label>
          Lọc trạng thái:{' '}
          <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
            <option value="">Tất cả</option>
            <option value="queued">queued</option>
            <option value="claimed">claimed</option>
            <option value="done">done</option>
            <option value="error">error</option>
            <option value="skipped">skipped</option>
          </select>
        </label>
      </div>
      <table className="data-table">
        <thead>
          <tr>
            <th>Tệp</th>
            <th>Trạng thái</th>
            <th>Lý do</th>
            <th>Lần thử</th>
            <th>Video</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {tasks.map((task) => {
            const inFlight = task.status === 'queued' || task.status === 'claimed'
            return (
              <tr key={task.task_id}>
                <td title={task.name}>{task.name}</td>
                <td>
                  <StatusBadge status={task.status} />
                </td>
                <td title={task.reason ?? ''}>{task.reason ?? '—'}</td>
                <td>{task.attempts}</td>
                <td title={task.video_id ?? ''}>{task.video_id ? shortId(task.video_id) : '—'}</td>
                <td>
                  <button
                    disabled={busy || inFlight}
                    title={inFlight ? 'Task đang chờ/đang chạy' : 'Đưa task về hàng đợi'}
                    onClick={() => requeue(`/api/v1/ingest/tasks/${task.task_id}/requeue`)}
                  >
                    Requeue
                  </button>
                </td>
              </tr>
            )
          })}
          {tasks.length === 0 && (
            <tr>
              <td colSpan={6}>Không có task nào.</td>
            </tr>
          )}
        </tbody>
      </table>

      <h2>Videos</h2>
      <table className="data-table">
        <thead>
          <tr>
            <th>Tệp</th>
            <th>Scene</th>
            <th>Đã index</th>
            <th>Chờ index</th>
            <th>FPS</th>
            <th>Tạo lúc</th>
          </tr>
        </thead>
        <tbody>
          {videos.map((video) => (
            <tr key={video.video_id}>
              <td title={video.name}>{video.name}</td>
              <td>{video.scene_count}</td>
              <td>{video.indexed_count}</td>
              <td>{video.pending_count}</td>
              <td>{video.framerate ?? '—'}</td>
              <td>{fmtDate(video.created_at)}</td>
            </tr>
          ))}
          {videos.length === 0 && (
            <tr>
              <td colSpan={6}>Chưa có video nào.</td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  )
}

export default Manage
