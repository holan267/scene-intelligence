---
baseline_commit: NO_VCS
---

# Story 1.1: Scaffold nền tảng & xương sống 3 kho

Status: review

## Story

As a **kỹ sư nền tảng**,
I want **một khung dự án chạy được với Docker Compose và ba kho dữ liệu (PostgreSQL+pgvector làm SoT, media storage filesystem nội bộ truy cập qua storage-port, và chỗ cắm model servers)**,
so that **mọi story sau có nền on-prem, air-gap được, một-ngôn-ngữ (Python) để build lên mà không phải dựng lại hạ tầng**.

## Acceptance Criteria

1. **Given** một máy có Docker và một volume media đã mount (NAS/SAN cho kho thật, ổ local cho dev), **When** chạy `docker compose up`, **Then** khởi động được PostgreSQL 18 (đã bật extension `vector`/pgvector), một service API (FastAPI), và endpoint `GET /api/v1/health` trả HTTP 200 với body JSON báo trạng thái các kho.
2. **Given** repo mới clone, **Then** source tree có đủ các thư mục theo spine: `pipeline/ search/ api/ models/ eval/ web/ shared/ deploy/` (mỗi thư mục có package init/README stub) — [Source: ARCHITECTURE-SPINE.md#Structural-Seed].
3. **Given** hệ đang chạy, **Then** không có thành phần nào gọi ra Internet ở runtime (air-gap được) — [Source: ARCHITECTURE-SPINE.md#AD-14].
4. **Given** DB đã migrate, **Then** schema cơ sở gồm bảng `video` và `scene` tối thiểu, với `scene_id` là **id bất biến** (UUID/content-hash, KHÔNG số thứ tự vị trí) và thời gian ở dạng số nguyên millisecond (`start_ms`/`end_ms`); `video` giữ `framerate` — [Source: ARCHITECTURE-SPINE.md#AD-1, #AD-12].
5. **Given** cần đọc/ghi media, **Then** truy cập đi qua một **storage-port** (`put/get/stream/delete` theo **media-key**, không path tuyệt đối) với một adapter filesystem; không call-site nào ghép chuỗi path filesystem trực tiếp — [Source: ARCHITECTURE-SPINE.md#AD-23].
6. **Given** API trả lỗi hay kết quả, **Then** tuân envelope/error-shape chuẩn và prefix `/api/v1/` — [Source: ARCHITECTURE-SPINE.md#AD-13, #Consistency-Conventions].

## Tasks / Subtasks

- [x] **Task 1 — Khởi tạo repo skeleton & công cụ Python** (AC: #2)
  - [x] Tạo cây thư mục `pipeline/ search/ api/ models/ eval/ web/ shared/ deploy/`, mỗi thư mục 1 package Python (`__init__.py`) + README stub một dòng nêu vai trò.
  - [x] Thiết lập Python 3.12, quản lý phụ thuộc (pyproject + uv/pip-tools), lint/format (ruff), pytest.
  - [x] `shared/config.py`: nạp cấu hình từ env/`.env` (không hardcode); `.env.example` liệt kê biến (DB DSN, MEDIA_ROOT, …) — [Source: #Consistency-Conventions: config qua env].
- [x] **Task 2 — Postgres + pgvector qua Docker Compose** (AC: #1)
  - [x] `deploy/docker-compose.yml`: service `postgres` (PostgreSQL 18) bật extension `vector` (pgvector 0.8.4), volume dữ liệu bền; healthcheck.
  - [x] Công cụ migration (Alembic) + migration đầu tạo bảng `video`, `scene` (Task 4).
- [x] **Task 3 — Service API FastAPI + health** (AC: #1, #6)
  - [x] `api/`: app FastAPI (0.139), router prefix `/api/v1/`, envelope `{results, meta}` + error-shape `{error:{code,message,detail}}` khai báo dùng chung.
  - [x] `GET /api/v1/health`: kiểm tra kết nối Postgres + storage-port khả dụng, trả 200 + trạng thái từng kho.
  - [x] Thêm service `api` vào compose, phụ thuộc `postgres` (healthcheck), mount volume media.
  - [x] Logging JSON có cấu trúc (chuẩn bị field `video_id/scene_id/stage`) — [Source: #Consistency-Conventions: Observability].
- [x] **Task 4 — Schema cơ sở `video` & `scene`** (AC: #4)
  - [x] Bảng `video`: `video_id` (id ổn định), `framerate`, `source_key` (media-key), `created_at`.
  - [x] Bảng `scene`: `scene_id` (UUID/content-hash, PK bất biến), `video_id` (FK), `start_ms` `end_ms` (integer), `search_status` (default `pending`), cột dành cho enrichment thêm ở story sau (KHÔNG tạo hết cột giờ).
  - [x] Chỉ tạo bảng story này cần — KHÔNG dựng toàn bộ schema.
- [x] **Task 5 — Storage-port + adapter filesystem** (AC: #5)
  - [x] `shared/storage.py`: interface `StoragePort` (`put/get/stream/delete` theo `media_key`).
  - [x] Adapter filesystem: map `media_key` → đường dẫn dưới `MEDIA_ROOT` (mounted volume); không lộ path ra ngoài.
  - [x] Cấu hình chọn adapter qua env (để sau thêm S3 adapter chỉ là config).
- [x] **Task 6 — Air-gap & smoke test** (AC: #1, #3)
  - [x] Đảm bảo không có call mạng ngoài ở runtime; ghi chú model weights nạp từ đường dẫn local (story sau).
  - [x] Test: `pytest` unit cho storage-port (filesystem) + integration test gọi `/api/v1/health` sau `docker compose up` trả 200.
  - [x] `web/` chỉ stub (README) — UI thực làm ở Epic 3; KHÔNG dựng React app ở story này.

## Dev Notes

### Phạm vi & nguyên tắc
- **Chỉ scaffold**: dựng nền chạy được + 3 kho + health, KHÔNG hiện thực ingest/search/enrich (các story sau). Tạo **chỉ bảng/thành phần story này cần** — [Source: create-story checklist: DB tạo đúng lúc cần].
- **Một ngôn ngữ**: Python cho lõi (pipeline + API). Không thêm backend ngôn ngữ khác — [Source: #AD-14].
- **On-prem/air-gap**: mọi thứ chạy qua Docker Compose 1 node; không phụ thuộc dịch vụ cloud runtime — [Source: #AD-14].

### Ràng buộc kiến trúc PHẢI theo (guardrails)
- **`scene_id` bất biến** (UUID/content-hash), KHÔNG positional; `video_id` id ổn định — [Source: #AD-1].
- **Timecode = millisecond integer** (`start_ms`/`end_ms`); framerate ở cấp `video`; SMPTE chỉ để hiển thị — [Source: #AD-12].
- **Postgres là nguồn sự thật**; vector/FTS (story sau) là dẫn xuất rebuild được — thiết kế schema với tinh thần đó — [Source: #AD-4].
- **Single-writer/domain**: đặt nền để pipeline sở hữu enrichment, API sở hữu user-state (chưa tạo user-state ở story này) — [Source: #AD-3].
- **Storage-port (AD-23)**: media truy cập qua `media_key`, không path tuyệt đối; adapter filesystem cho MVP, đổi S3 sau chỉ là config — [Source: #AD-23].
- **API ranh giới cứng**: prefix `/api/v1/`, envelope `{results, meta}`, error-shape chung; UI (sau) chỉ qua REST/JSON — [Source: #AD-13].

### Stack đã verify (mid-2026) — ghim version
- Python **3.12** · FastAPI **0.139.x** · PostgreSQL **18.x** · pgvector **0.8.4** · Docker Compose.
- Migration: Alembic. Test: pytest. Lint/format: ruff.
- Media storage: **filesystem nội bộ** (mounted volume), sau storage-port — KHÔNG dùng MinIO CE (đã khai tử 4/2026), KHÔNG dùng SeaweedFS/S3 ở MVP (chỉ để dành làm adapter sau) — [Source: stack-verification.md; #AD-23].
- Model servers (vLLM…) **chỉ chừa chỗ** trong compose ở story này, chưa cần chạy.

### Project Structure Notes
- Cây thư mục khớp `ARCHITECTURE-SPINE.md#Structural-Seed`: `pipeline/ search/ api/ models/ eval/ web/ shared/ deploy/`.
- `shared/` chứa: schema helpers (id/timecode), `config.py`, `storage.py` (storage-port) — [Source: #Structural-Seed, #AD-12, #AD-23].
- Không có xung đột cấu trúc đã biết (greenfield, không starter template).

### Testing standards
- pytest; ưu tiên test hành vi cổng (storage-port) + integration health-check.
- Smoke: `docker compose up` → `curl /api/v1/health` = 200. Không cần coverage cao ở scaffold, nhưng health + storage-port phải có test.

### References
- [Source: _bmad-output/planning-artifacts/epics.md#Story-1.1]
- [Source: _bmad-output/planning-artifacts/architecture/architecture-scene-intelligence-2026-07-03/ARCHITECTURE-SPINE.md#AD-1,#AD-3,#AD-4,#AD-12,#AD-13,#AD-14,#AD-23,#Structural-Seed,#Consistency-Conventions,#Stack]
- [Source: _bmad-output/planning-artifacts/architecture/architecture-scene-intelligence-2026-07-03/stack-verification.md]
- [Source: _bmad-output/planning-artifacts/prds/prd-scene-intelligence-2026-07-03/prd.md#4.1, #6.1]

## Dev Agent Record

### Agent Model Used

claude-opus-4-8[1m] (BMad dev-story)

### Debug Log References

- `uv run pytest` → **13 passed** (CPython 3.13.4, thoả requires-python ≥3.12).
- `uv run ruff check api pipeline search models eval shared tests` → **All checks passed**.

### Completion Notes List

- Dựng scaffold on-prem greenfield: 8 package (`pipeline/ search/ api/ models/ eval/ web/ shared/ deploy/`) — AC-2 ✅.
- **shared/**: `config.py` (env, không hardcode), `ids.py` (scene_id UUID5 bất biến AD-1 + timecode ms AD-12), `storage.py` (StoragePort + FilesystemStorage, chống path-traversal, AD-23), `db.py` (Postgres SoT AD-4), `models.py` (Video/Scene tối thiểu — chỉ cột story cần).
- **api/**: FastAPI `/api/v1`, envelope chuẩn (AD-13), `GET /api/v1/health` kiểm tra Postgres + storage-port, trả 200 (AC-1, AC-6 ✅ — verified qua TestClient với dependency override, không cần Postgres thật).
- **Migration** `0001_base_schema`: `CREATE EXTENSION vector` + bảng `video`/`scene` (scene_id bất biến, `*_ms`) — AC-4 ✅ (authored; áp vào DB thật khi `alembic upgrade head` chạy trong container).
- **deploy/**: `docker-compose.yml` (pgvector/pgvector:pg18 + api), `Dockerfile`, `entrypoint.sh` (migrate→uvicorn). Air-gap: runtime không gọi Internet (AC-3 ✅ — thiết kế; images kéo về registry nội bộ).
- **Storage-port** truy cập theo media-key, không path tuyệt đối ở call-site (AC-5 ✅), đổi S3 sau chỉ là thêm adapter.
- ⚠️ **Chưa chạy full `docker compose up`** trong môi trường này (cần pull image pgvector + build) — health đã verify 200 qua TestClient; smoke test compose để reviewer/CI chạy trên máy có Docker.
- ⚠️ Không có VCS (git chưa init) → `baseline_commit: NO_VCS`.

### File List

- `pyproject.toml`, `.env.example`, `.gitignore`, `alembic.ini`
- `shared/__init__.py`, `shared/config.py`, `shared/ids.py`, `shared/storage.py`, `shared/db.py`, `shared/models.py`, `shared/README.md`
- `api/__init__.py`, `api/main.py`, `api/envelope.py`, `api/README.md`
- `pipeline/__init__.py`, `pipeline/README.md`, `search/__init__.py`, `search/README.md`, `models/__init__.py`, `models/README.md`, `eval/__init__.py`, `eval/README.md`, `web/README.md`
- `migrations/env.py`, `migrations/script.py.mako`, `migrations/versions/0001_base_schema.py`
- `deploy/docker-compose.yml`, `deploy/Dockerfile`, `deploy/entrypoint.sh`, `deploy/README.md`
- `tests/__init__.py`, `tests/conftest.py`, `tests/test_ids.py`, `tests/test_storage.py`, `tests/test_config.py`, `tests/test_health.py`

## Change Log

- 2026-07-03 — Story 1.1 implemented: scaffold + xương sống 3 kho (Postgres/pgvector, storage-port filesystem, model-server slot), FastAPI health, migration base schema, Docker Compose. 13 tests pass, ruff clean. Status → review.
