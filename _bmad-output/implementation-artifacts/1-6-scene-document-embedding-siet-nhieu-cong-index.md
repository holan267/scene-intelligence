---
baseline_commit: 7255d79b473c448912a58fd156ff66515190bb3c
---

# Story 1.6: Scene Document, scene_embedding, siết nhiễu & cổng index

Status: done

## Story

As a **hệ thống ingest**,
I want **sinh Scene Document (Qwen3-VL), tạo một scene_embedding (BGE-M3), siết nhiễu, rồi mở cổng "indexed"**,
so that **Scene trở nên tìm-được với chất lượng cao**.

## Acceptance Criteria

1. **Given** một Scene đã có tín hiệu ASR/OCR/face/object, **When** stage describe chạy, **Then** sinh Scene Document (NL, tiếng Việt) ghi vào `scene.scene_document` (cột riêng — AD-5) — [Source: FR-5, #AD-9].
2. **Given** Scene đã có `scene_document`, **When** stage embed→index chạy, **Then** sinh **đúng một** `scene_embedding`/Scene (BGE-M3, vào pgvector) + một dòng dữ liệu cho FTS — [Source: #AD-7].
3. **Given** derived-artifact (`scene_embedding` row) vừa ghi, **Then** nó mang `doc_version` = checksum (sha256) của `scene_document` mà nó dựng từ — [Source: #AD-16].
4. **Given** tín hiệu vô-phân-biệt (OCR/nhãn lặp ở hầu hết Scene trong kho) hoặc confidence thấp, **Then** các tín hiệu này **không** được đưa vào ngữ cảnh dựng Scene Document dưới dạng khẳng định — [Source: FR-13].
5. **Given** Scene vừa ghi xong vector + FTS, **Then** `scene.search_status` chỉ chuyển sang `"indexed"` (nguyên tử, sau khi ghi xong derived-store) — nếu bước ghi vector/FTS lỗi, `search_status` không đổi — [Source: #AD-17].
6. **Given** dữ liệu SoT (Postgres) không đổi, **When** xoá rồi chạy lại describe→embed→index, **Then** `scene_embedding`/`scene_document` dựng lại cho kết quả tương đương (không có gì chỉ-tồn-tại-trong-vector-store) — [Source: #AD-4].

## Tasks / Subtasks

- [x] **Task 1 — Schema + dependency** (AC: #1, #2, #3): migration `0006`:
  - [x] Thêm dependency `pgvector` (PyPI, MIT) vào `pyproject.toml` — **đã duyệt qua story này**, không cần hỏi lại khi dev. Đã kiểm chứng thực nghiệm: `pgvector.sqlalchemy.Vector` round-trip được qua sqlite (fixture test hiện tại dùng `Base.metadata.create_all` trên sqlite) — an toàn để khai báo thẳng trong `shared/models.py` như cột ORM bình thường, không cần metadata/Base riêng.
  - [x] Cột `scene.scene_document` (Text, nullable) — Scene Document NL, SoT (AD-4), ghi bởi stage describe (cột riêng — AD-5).
  - [x] Bảng `scene_embedding` (1 dòng/Scene — AD-7): `scene_id` (PK, FK → `scene.scene_id`), `embedding` (`pgvector.sqlalchemy.Vector(1024)` — BGE-M3 dense dim `[ASSUMPTION: 1024, xác nhận lại khi chạy model thật]`), `fts_text` (Text, nullable — text nguồn để Epic 2/Story 2.2 chạy `to_tsvector`/tạo GIN index; **không** khai báo cột `TSVECTOR` ở story này — đã kiểm chứng thực nghiệm `sqlalchemy.dialects.postgresql.TSVECTOR` **raise `CompileError` trên sqlite**, sẽ làm vỡ toàn bộ fixture test hiện tại vì `conftest.py` chạy `Base.metadata.create_all` trên sqlite cho mọi test file), `doc_version` (String(64), nullable — sha256 hex), `created_at`.
  - [x] pgvector extension đã tạo ở migration `0001` (`CREATE EXTENSION IF NOT EXISTS vector`) — không cần lặp lại.
- [x] **Task 2 — Siết nhiễu theo corpus** (AC: #4): `pipeline/noise.py` — `corpus_stopwords(session, *, ratio_threshold=0.6) -> set[str]`: quét toàn kho — với mỗi giá trị `scene.ocr_text` (chuỗi, không tách từ — theo đúng nghĩa "chuỗi OCR lặp" của FR-13) và mỗi `label` trong `scene.objects` (JSON) của mọi Scene, tính tỷ lệ `số Scene chứa tín hiệu này / tổng số Scene`; nếu tỷ lệ ≥ `ratio_threshold` → thêm vào tập stopword trả về (logo/ticker lặp toàn kho). `ratio_threshold=0.6` là `[ASSUMPTION]` (không có số cụ thể trong PRD).
- [x] **Task 3 — Build hints + sinh Scene Document** (AC: #1, #4): `pipeline/describe.py`:
  - [x] `SceneDescriber` Protocol: `describe(self, keyframe_images: list[bytes], hints: dict) -> str`.
  - [x] `build_hints(scene, face_appearances, persons, corpus_stopwords, *, confidence_threshold=0.5) -> dict` (hàm thuần, test không cần model — bỏ tham số `shots` khỏi thiết kế ban đầu vì không cần cho nội dung hints, ảnh keyframe đã tách riêng ở `describe_scene`): gộp `transcript`; `ocr_text` **chỉ nếu KHÔNG nằm trong `corpus_stopwords`**; object `label` **chỉ nếu** `confidence >= confidence_threshold` **và** label không nằm trong `corpus_stopwords`; tên người **chỉ** từ `face_appearance.person_id is not None` (đã lọc "không xác định" từ Story 1.5, AD-11) resolve qua `Person.name`. `confidence_threshold=0.5` là `[ASSUMPTION]` — cùng giá trị mặc định với `face_threshold` ở Story 1.5 cho nhất quán.
  - [x] `describe_scene(session, storage, scene_id, describer, corpus_stopwords, *, confidence_threshold=0.5) -> dict`: nạp Scene + Shot + FaceAppearance + Person liên quan, lấy keyframe qua storage-port (dedupe theo `keyframe_key`, cùng pattern Story 1.4/1.5), gọi `build_hints` rồi `describer.describe(keyframe_images, hints)`, ghi kết quả vào `scene.scene_document` (cột riêng — AD-5, không đụng `transcript`/`ocr_text`/`objects`).
- [x] **Task 4 — Embed + Index** (AC: #2, #3, #5, #6): `pipeline/embed_index.py`:
  - [x] `TextEmbedder` Protocol: `embed(self, text: str) -> list[float]`.
  - [x] `doc_version(scene_document: str) -> str`: `sha256(scene_document.encode()).hexdigest()`.
  - [x] `index_scene(session, scene_id, embedder) -> dict`: raise nếu `scene.scene_document is None` (describe chưa chạy); tính `doc_version`, `embedding = embedder.embed(scene_document)`; **idempotent overwrite** `scene_embedding` row (update tại chỗ nếu đã tồn tại, insert nếu chưa — 1 dòng/Scene, AD-7) với `fts_text=scene_document`; **chỉ sau khi** dòng `scene_embedding` ghi xong (flush thành công) mới set `scene.search_status = "indexed"` (AD-17) — nếu `embedder.embed()` raise, hàm raise trước khi chạm `search_status`, giữ nguyên giá trị cũ.
  - [x] Rebuildability (AD-4): không cần cơ chế riêng — `index_scene` tất định từ `scene.scene_document` (SoT) nên chạy lại (sau khi xoá `scene_embedding`) tái tạo dữ liệu tương đương; đã test trực tiếp bằng cách xoá row rồi gọi lại; không xây thêm CLI rebuild ở story này (ngoài scope AC).
- [x] **Task 5 — Adapter production** (guarded, chưa chạy môi trường dev): `pipeline/describe_backends.py` (`Qwen3VLDescriber`) + `pipeline/embed_backends.py` (`BgeM3Embedder`) — gọi qua **Model Server HTTP endpoint** (vLLM OpenAI-compatible, AD-14), không load model trong tiến trình pipeline (khác pattern in-process của InsightFace/YOLO ở Story 1.5, đúng với kiến trúc "Model Servers" tách biệt trong spine). Thêm 2 setting `describe_model_url`/`embed_model_url` vào `shared/config.py`. Chuyển `httpx` từ `dependency-groups.dev` sang `[project.dependencies]` chính thức (adapter production cần dùng thật, không chỉ test).
- [x] **Task 6 — Test** (AC: #1-#6): `tests/test_noise.py` + `tests/test_describe.py` + `tests/test_embed_index.py` — fake describer/embedder + sqlite:
  - [x] `corpus_stopwords`: chuỗi OCR/label xuất hiện ≥ ratio_threshold Scene → vào tập stopword; xuất hiện ít → không.
  - [x] `build_hints`: OCR trong stopword bị loại; object confidence thấp bị loại; object trong stopword bị loại; chỉ face đã xác định (`person_id is not None`) được đưa vào, resolve đúng tên.
  - [x] `describe_scene` ghi `scene.scene_document`, không đụng `transcript`/`ocr_text`/`objects` (AD-5).
  - [x] `doc_version` tất định (cùng input → cùng checksum; đổi `scene_document` → đổi checksum).
  - [x] `index_scene`: ghi đúng 1 dòng `scene_embedding`/Scene, `search_status` chuyển `"indexed"` **chỉ sau khi** ghi xong; nếu embedder raise → `search_status` giữ nguyên (không đổi) và không có dòng `scene_embedding` mồ côi.
  - [x] `index_scene` raise khi `scene.scene_document is None` (chưa describe).
  - [x] Rebuild: xoá `scene_embedding` rồi chạy lại `index_scene` → dữ liệu tương đương (AD-4).

### Review Findings

- [x] [Review][Patch] `build_hints`/`corpus_stopwords` crash on malformed `Scene.objects` JSON or an object dict missing `label`/`confidence` — one bad row aborts the whole describe call / whole corpus scan [pipeline/describe.py:28-30, pipeline/noise.py:21]
- [x] [Review][Patch] Embedding dimension/shape from the model server response is never validated — a mismatch only surfaces as an opaque pgvector error at flush time instead of a clear domain error [pipeline/embed_backends.py, pipeline/embed_index.py]
- [x] [Review][Patch] HTTP backends only catch `httpx.HTTPError`, not response-shape errors — a 200 response with an unexpected/empty body raises unhandled `KeyError`/`IndexError`/`TypeError` instead of the intended wrapped `RuntimeError` [pipeline/describe_backends.py, pipeline/embed_backends.py]
- [x] [Review][Patch] No guard against an empty/whitespace-only `scene.scene_document` in `index_scene` (only checks `is None`) — a degenerate empty description gets embedded and flipped to `"indexed"` silently [pipeline/embed_index.py:31]
- [x] [Review][Patch] Face names in `build_hints` are not deduplicated — the same identified person appearing in multiple Shots repeats redundantly in the hints (inconsistent with FR-13 noise-suppression intent, unlike objects) [pipeline/describe.py]
- [x] [Review][Patch] `try/except ImportError` around `import httpx` in both backend adapters is dead/misleading code now that `httpx` is a hard `[project.dependencies]` entry, not an optional lib [pipeline/describe_backends.py, pipeline/embed_backends.py]
- [x] [Review][Patch] Shot query in `describe_scene` has no `ORDER BY` — keyframe order (and thus the multi-image sequence given to Qwen3-VL) is not guaranteed stable across runs, weakening AC-6's rebuild-equivalence claim [pipeline/describe.py]
- [x] [Review][Patch] `scene_embedding.doc_version`/`fts_text` are schema-nullable even though `index_scene` always writes them together with `embedding` — AC-3's "always present" invariant isn't enforced at the DB level [migrations/versions/0006_scene_document_embedding.py, shared/models.py]

## Dev Notes

- **AD-7**: đúng **một** `scene_embedding`/Scene (BGE-M3, từ `scene_document`) cho tìm kiếm text — **không** phải visual embedding (SigLIP2, Story 3.3, collection riêng, ngoài scope story này).
- **AD-16**: `doc_version` = sha256 của `scene_document` — Search Service (Epic 2) sẽ so `doc_version` với checksum hiện tại của `scene.scene_document` để loại Scene lệch phiên bản; **story này chỉ ghi đúng `doc_version`, không tự kiểm tra staleness** (đó là việc của Story 2.x khi đọc).
- **AD-17**: thứ tự ghi trong `index_scene` — ghi `scene_embedding` xong (flush) rồi mới set `search_status="indexed"`; đây là trong cùng một transaction nên tính nguyên tử ở mức DB đã có sẵn qua transaction boundary — điểm mấu chốt cần đúng là **thứ tự lệnh trong code** (không set `indexed` trước khi chắc chắn ghi xong).
- **AD-4**: `scene_embedding` là dẫn xuất, dựng lại được 100% từ `scene.scene_document` (SoT) — không lưu gì ở `scene_embedding` mà Postgres không tái tạo lại được từ `Scene`.
- **AD-9**: Qwen3-VL (VLM tiếng Việt) sinh `scene_document`; BGE-M3 (đa ngữ, phủ tiếng Việt) sinh embedding — cả hai đã có trong stack, không đổi model English-only.
- **AD-6**: `describer.describe()` nhận `keyframe_images` (list, đã dedupe theo `keyframe_key` — cùng pattern Story 1.4/1.5), không chạy trên mọi frame.
- **AD-5**: stage describe chỉ ghi `scene.scene_document`; stage embed/index chỉ ghi bảng `scene_embedding` + `scene.search_status` — không đụng `transcript`/`ocr_text`/`objects`/`face_appearance` của các stage trước.
- **FR-13 — siết nhiễu, quyết định thiết kế quan trọng**: lọc nhiễu xảy ra ở bước **build_hints** (trước khi đưa vào ngữ cảnh cho Qwen3-VL) — nghĩa là tín hiệu nhiễu/confidence-thấp **không bao giờ được đưa cho model như một khẳng định**, chứ không phải lọc hậu-kỳ trên văn bản model đã sinh ra. Đơn vị "chuỗi lặp" là **toàn bộ giá trị `ocr_text`** của Scene (không tách từ) và **label** đối tượng — khớp đúng nghĩa "chuỗi OCR/nhãn lặp" trong FR-13 (không phải per-word IDF).
- **⚠️ Rủi ro kỹ thuật đã kiểm chứng thực nghiệm trước khi viết story này** (tránh disaster khi dev):
  - `pgvector.sqlalchemy.Vector(n)` **round-trip OK qua sqlite** (`Base.metadata.create_all` + insert + select đã test thủ công) → khai báo thẳng làm cột ORM bình thường trong `shared/models.py`, dùng chung `Base`/fixture `async_session` hiện tại, không cần setup riêng.
  - `sqlalchemy.dialects.postgresql.TSVECTOR` **raise `CompileError` trên sqlite** (đã test thủ công, `create_all` fail ngay) → **KHÔNG** dùng type này trong ORM model ở story này (sẽ vỡ toàn bộ test suite hiện tại vì mọi test file dùng chung `Base.metadata.create_all` trên sqlite qua `tests/conftest.py`). Dùng cột `Text` (`fts_text`) thay thế; việc tạo `tsvector`/GIN index thật là việc của Story 2.2 (đọc từ `fts_text` lúc đó), không phải của story này.
- **Đăng ký dependency mới**: `pgvector` (PyPI, MIT license) — cần thêm vào `pyproject.toml` `[project.dependencies]`. Đã duyệt qua story này (không phải quyết định tự ý của dev agent).
- Model thật (Qwen3-VL, BGE-M3) đi vào `describe_backends.py`/`embed_backends.py` theo đúng pattern guarded lazy-import của các adapter trước (Story 1.3-1.5) — CHƯA chạy môi trường này.

### Project Structure Notes

- File mới nằm đúng `pipeline/` — song song `enrich.py`, `enrich_vision.py`, `detect.py` các story trước.
- `pipeline/noise.py` là module mới (thống kê corpus-wide, không gắn với 1 Scene cụ thể) — tách khỏi `describe.py` vì phạm vi tính toán khác nhau (toàn kho vs 1 Scene).
- Migration mới = `0006`, nối tiếp `0005` (Story 1.5).
- `pyproject.toml` cần thêm `pgvector` vào `dependencies` (không phải `dependency-groups.dev` — dùng ở production, không chỉ test).

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story-1.6]
- [Source: _bmad-output/planning-artifacts/architecture/architecture-scene-intelligence-2026-07-03/ARCHITECTURE-SPINE.md#AD-4,#AD-5,#AD-6,#AD-7,#AD-9,#AD-16,#AD-17]
- [Source: _bmad-output/planning-artifacts/architecture/architecture-scene-intelligence-2026-07-03/stack-verification.md] (BGE-M3, Qwen3-VL, pgvector 0.8.4)
- [Source: _bmad-output/planning-artifacts/prds/prd-scene-intelligence-2026-07-03/prd.md#FR-13 (dòng ~185-194)]
- [Source: _bmad-output/implementation-artifacts/1-5-lam-giau-thi-giac-khuon-mat-doi-tuong.md] (pattern enrich cột riêng, guarded adapter, dedupe keyframe)
- [Source: pipeline/enrich.py, pipeline/enrich_vision.py, pipeline/registry.py, shared/models.py, shared/ids.py, shared/storage.py, tests/test_enrich_vision.py, tests/conftest.py]
- Kiểm chứng thực nghiệm thực hiện trong phiên tạo story này: `pgvector.sqlalchemy.Vector` OK trên sqlite; `sqlalchemy.dialects.postgresql.TSVECTOR` raise `CompileError` trên sqlite.

## Dev Agent Record

### Agent Model Used

claude-sonnet-5 (BMad dev-story)

### Debug Log References

- Kiểm chứng thực nghiệm trước khi code: `pgvector.sqlalchemy.Vector` round-trip OK qua sqlite; `sqlalchemy.dialects.postgresql.TSVECTOR` raise `CompileError` trên sqlite (xem Dev Notes).
- `uv run pytest` → **62 passed** (47 + 15 mới: 3 noise + 6 describe + 6 embed_index). `uv run ruff check` trên file mới/sửa → sạch.
- Sau code review (8 patch áp dụng): `uv run pytest` → **67 passed** (62 + 5 mới). `uv run ruff check` → sạch.

### Completion Notes List

- **Dependency**: thêm `pgvector>=0.3` (mới) vào `[project.dependencies]`; chuyển `httpx` từ `dependency-groups.dev` sang dependency chính thức (adapter production gọi Model Server qua HTTP thật, không chỉ dùng cho test).
- **Schema** (migration `0006`): cột `scene.scene_document` (Text); bảng `scene_embedding` (`embedding` = `Vector(1024)`, `fts_text` = Text thuần — **không** TSVECTOR, xem lý do kiểm chứng ở Dev Notes — `doc_version` = sha256 hex).
- **`pipeline/noise.py`**: `corpus_stopwords` — quét `scene.ocr_text` + label trong `scene.objects` toàn kho, trả tập chuỗi có tỷ lệ Scene chứa ≥ `ratio_threshold` (AC-4).
- **`pipeline/describe.py`**: `build_hints` (hàm thuần) siết nhiễu TRƯỚC khi đưa vào ngữ cảnh cho VLM — loại OCR/label trong `corpus_stopwords`, loại object confidence thấp, chỉ đưa tên người đã xác định (`person_id is not None`). `describe_scene` gộp keyframe (dedupe) + hints, gọi describer, ghi `scene.scene_document` (cột riêng, AD-5) — bỏ tham số `shots` khỏi signature ban đầu trong story vì không cần cho nội dung hints.
- **`pipeline/embed_index.py`**: `index_scene` — tính `doc_version` (sha256), gọi `embedder.embed()` TRƯỚC khi chạm `search_status`; ghi/update `scene_embedding` (1 dòng/Scene, idempotent); chỉ set `search_status="indexed"` sau khi flush thành công (AD-17). Rebuild-equivalence test bằng xoá row rồi chạy lại (AD-4).
- **Adapter production**: `Qwen3VLDescriber`/`BgeM3Embedder` gọi **Model Server qua HTTP** (vLLM OpenAI-compatible endpoint, AD-14) — khác pattern in-process load của InsightFace/YOLO (Story 1.5) vì Qwen3-VL/BGE-M3 chạy trên Model Server riêng theo kiến trúc spine. Thêm setting `describe_model_url`/`embed_model_url`. CHƯA chạy môi trường này (chưa có server thật).
- ⚠️ `SCENE_EMBEDDING_DIM=1024` (BGE-M3 dense dim) là `[ASSUMPTION]` — xác nhận lại khi chạy model thật; nếu sai cần migration đổi `Vector(n)`.
- ⚠️ `ratio_threshold=0.6` (siết nhiễu) và `confidence_threshold=0.5` (build_hints) là `[ASSUMPTION]` — không có số cụ thể trong PRD/epics, tham số hoá để chỉnh sau khi có dữ liệu thật/eval (Epic 4).
- **Code review (8 patch áp dụng, xem Review Findings)**: guard JSON hỏng/thiếu key trong `build_hints`/`corpus_stopwords` (bỏ qua entry lỗi thay vì crash); validate chiều embedding + bọc lỗi hình dạng response HTTP (KeyError/IndexError → `RuntimeError` rõ nghĩa) trong `describe_backends.py`/`embed_backends.py`; guard `scene_document` rỗng/toàn khoảng trắng trong `index_scene`; khử trùng lặp tên người trong `build_hints` (tách hàm `_filter_objects`/`_identified_face_names` để giảm cognitive complexity); bỏ guard `ImportError` chết (httpx đã là dependency chính); thêm `.order_by(Shot.start_ms)` cho keyframe ổn định; `doc_version`/`fts_text` chuyển `nullable=False` (migration + model). Thêm 5 test mới.

### File List

- **Mới**: `pipeline/noise.py`, `pipeline/describe.py`, `pipeline/describe_backends.py`, `pipeline/embed_index.py`, `pipeline/embed_backends.py`, `migrations/versions/0006_scene_document_embedding.py`, `tests/test_noise.py`, `tests/test_describe.py`, `tests/test_embed_index.py`
- **Sửa**: `shared/models.py` (thêm `Scene.scene_document`, bảng `SceneEmbedding`, `SCENE_EMBEDDING_DIM`), `shared/config.py` (thêm `describe_model_url`, `embed_model_url`), `pyproject.toml` (thêm `pgvector`, chuyển `httpx` sang dependency chính)

## Change Log

- 2026-07-03 — Story 1.6: Scene Document (Qwen3-VL) + scene_embedding (BGE-M3, pgvector) + siết nhiễu corpus (FR-13) + cổng index nguyên tử (AD-17).
- 2026-07-03 — Code review: 8 patch áp dụng (guard JSON hỏng, validate embedding dim, bọc lỗi response HTTP, guard scene_document rỗng, dedup tên người, bỏ guard chết, order_by keyframe, NOT NULL doc_version/fts_text) + 5 test mới. 21 finding khác dismiss (khớp convention/precedent đã có hoặc đã tracked ở PRD/architecture).
