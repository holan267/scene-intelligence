---
baseline_commit: NO_VCS
---

# Story 1.2: Nạp video theo lô qua hàng đợi có tiến độ

Status: done

## Story

As a **thủ thư kho**,
I want **trỏ hệ thống vào một thư mục/ổ nội bộ để nạp cả một lô video và theo dõi tiến độ**,
so that **tôi đưa cả kho vào hệ thống mà không phải thao tác từng tệp**.

## Acceptance Criteria

1. **Given** một thư mục chứa nhiều video, **When** tạo một job nạp lô, **Then** hệ thống quét, xếp mọi video hợp lệ vào **hàng đợi bền (Postgres-backed)** và trả `job_id` — [Source: epics.md#Story-1.2; #AD-10].
2. **Given** một `job_id`, **Then** truy vấn được trạng thái/tiến độ (tổng, đã xong, còn hàng đợi, bỏ qua, lỗi).
3. **Given** trong lô có tệp lỗi/không đọc được, **Then** tệp đó bị **bỏ qua + ghi lý do**, KHÔNG làm dừng cả lô — [Source: PRD FR-1].
4. **Given** cơ chế trạng thái, **Then** trạng thái job do **orchestrator** quyết; worker chỉ chuyển trạng thái task của chính nó — [Source: #AD-18].
5. **Given** nạp lại một tệp đã có, **Then** KHÔNG tạo Video/Task trùng (idempotent theo `source_key`) — [Source: #AD-5, NFR-2].

## Tasks / Subtasks

- [x] **Task 1 — Schema hàng đợi** (AC: #1, #4)
  - [x] Migration `0002`: bảng `job` (batch) và `ingest_task` (mỗi video 1 task, `source_key` unique, `status`, `reason`, `video_id` nullable).
  - [x] `framerate` của `video` chuyển nullable (xác định ở Story 1.3 khi detect).
- [x] **Task 2 — Logic ingest** (AC: #1, #3, #5)
  - [x] `discover_videos(root)`: quét đệ quy, lọc theo đuôi video.
  - [x] `enqueue_batch(session, paths)`: tạo Job + Task; **dedupe theo source_key** (đã có → bỏ qua); tệp không đọc được → task `skipped` kèm reason; không dừng lô.
  - [x] `job_progress(session, job_id)`: đếm theo trạng thái.
- [x] **Task 3 — Worker & orchestrator** (AC: #4)
  - [x] `claim_next_task` (Postgres `FOR UPDATE SKIP LOCKED`; fallback không-skip-lock cho test/sqlite).
  - [x] `process_task`: đăng ký `Video` từ task (framerate để null, detect ở 1.3), chuyển task `done`; lỗi → `error` + reason. Orchestrator kết luận job `done` khi hết task đang chạy.
- [x] **Task 4 — API** (AC: #1, #2)
  - [x] `POST /api/v1/ingest` (body `{source_dir}`) → tạo job, trả envelope `{job_id, queued, duplicates, invalid}`.
  - [x] `GET /api/v1/jobs/{job_id}` → envelope tiến độ.
- [x] **Task 5 — Test** (AC: tất cả)
  - [x] Unit: discover, dedupe, error-skip, enqueue counts, progress, worker đăng ký Video (async sqlite).

## Dev Notes

- **AD-10/AD-18**: ingest bất đồng bộ; job = domain của orchestrator; worker chỉ đụng task của mình. `job.status` không do worker ghi trực tiếp — worker cập nhật task, orchestrator/`job_progress` suy ra.
- **AD-5/NFR-2**: idempotent theo `source_key` (unique) → nạp lại không nhân đôi.
- **AD-4**: job/task/video ở Postgres (SoT). **AD-23**: video tham chiếu bằng `source_key` (media-key), không path tuyệt đối lưu DB.
- Story này CHƯA làm scene detection/enrichment (Story 1.3+). Worker chỉ **đăng ký Video** tồn tại.
- [Source: ARCHITECTURE-SPINE.md#AD-4,#AD-5,#AD-10,#AD-18,#AD-23; epics.md#Story-1.2; prd.md#FR-1]

## Dev Agent Record

### Agent Model Used

claude-opus-4-8[1m] (BMad dev-story)

### Debug Log References

- `uv run pytest` → **19 passed** (13 của 1.1 + 6 của 1.2). `ruff check` → sạch.

### Completion Notes List

- **Schema hàng đợi** (migration `0002`): `job` + `ingest_task` (`source_key` unique → idempotent AD-5); `video.framerate` chuyển nullable (detect ở 1.3). AC-1/AC-4 ✅.
- **pipeline/ingest.py**: `discover_videos` (lọc đuôi), `enqueue_batch` (dedupe theo source_key, tệp lỗi → `skipped` + reason, không dừng lô — AC-3/AC-5), `job_progress` (đếm theo trạng thái — AC-2), `claim_next_task` (Postgres `FOR UPDATE SKIP LOCKED`, fallback cho sqlite), `finalize_job` (orchestrator kết luận job — AD-18).
- **pipeline/workers.py**: `process_task` chỉ **đăng ký Video** (chưa enrich); lỗi task → `error`, không sập worker; `run_once`.
- **api/routes_ingest.py**: `POST /api/v1/ingest` (quét dir + enqueue) và `GET /api/v1/jobs/{job_id}` (tiến độ), envelope chuẩn, DI kiểu `Annotated`.
- **Test** (async sqlite): discover, enqueue+progress, dedupe idempotent, error-skip, worker đăng ký Video + orchestrator finalize, route đăng ký (qua OpenAPI).
- ⚠️ Như 1.1: chưa chạy live Postgres/`docker compose up` ở đây; logic DB verify bằng sqlite in-memory + SKIP-LOCKED để dành cho Postgres thật (CI/reviewer).

### File List

- **Mới**: `pipeline/ingest.py`, `pipeline/workers.py`, `api/routes_ingest.py`, `migrations/versions/0002_ingest_queue.py`, `tests/test_ingest.py`
- **Sửa**: `shared/models.py` (Job/IngestTask + framerate nullable), `shared/ids.py` (`new_id`), `migrations/versions/0001_base_schema.py` (framerate nullable), `api/main.py` (include ingest router, Annotated DI), `tests/conftest.py` (async_session fixture), `pyproject.toml` (pytest-asyncio, aiosqlite, asyncio_mode)

## Change Log

- 2026-07-03 — Story 1.2: hàng đợi ingest Postgres-backed + API nạp lô/tiến độ + worker đăng ký Video.

## Review Findings (code review 2026-07-03)

- [x] [Review][Decision→Patch] **Danh tính & phạm vi ingest**: ĐÃ patch — giới hạn ingest trong `MEDIA_ROOT` (`resolve_source_dir`, 400 nếu ngoài/thiếu), `source_key` = path tương-đối-`MEDIA_ROOT`, requeue task skipped/error [pipeline/ingest.py, api/routes_ingest.py]
- [x] [Review][Patch] `finalize_job` chỉ được gọi trong test — chưa wire vào runtime + thiếu worker driver loop → job kẹt `running` mãi (AD-18/AC-2/AC-4) [pipeline/ingest.py, workers.py]
- [x] [Review][Patch] `process_task` try/except bọc thiếu `flush` (flush ngoài try) → lỗi DB làm sập worker thay vì đánh dấu task `error` [pipeline/workers.py]
- [x] [Review][Patch] `process_task` không idempotent: re-claim đúc Video trùng (`Video.source_key` thiếu UNIQUE, không guard `task.video_id` đã set) [pipeline/workers.py, shared/models.py]
- [x] [Review][Patch] Task `skipped`/`error` chiếm khoá `source_key` vĩnh viễn → lỗi tạm thời thành bỏ-qua-vĩnh-viễn; dedupe nên loại trạng thái skipped/error [pipeline/ingest.py]
- [x] [Review][Patch→Defer] `enqueue_batch` an toàn cạnh tranh đa tiến trình: đã giảm va chạm bằng lookup+requeue trong-tiến-trình; DEFER phần `INSERT ON CONFLICT`/savepoint (dialect-specific) sang deferred-work.md [pipeline/ingest.py]
- [x] [Review][Patch] `source_dir` sai/không tồn tại → 200 `queued:0` job `done`, không báo lỗi cho thủ thư [pipeline/ingest.py, api/routes_ingest.py]
- [x] [Review][Patch] Task cùng batch có `created_at` bằng nhau (now() theo transaction) → thứ tự claim không xác định; thêm tiebreaker [pipeline/ingest.py]
- [x] [Review][Defer] Task kẹt `claimed` khi worker crash (thiếu lease/timeout/reclaim) → job không finalize — thuộc hardening vận hành (gần Story 1.7)
- [x] [Review][Defer] I/O đồng bộ chặn event loop (`rglob`, `_readable`, `extract`, `put`) → nghẽn request khi quét kho lớn — cần threadpool/executor
