---
baseline_commit: c361477dd5bdbe832e15f11707ff6cf73a5013c8
---

# Story 2.1: Tìm ngữ nghĩa + rerank, trả envelope jump-to-moment

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a **biên tập viên**,
I want **gõ một câu đời thường và nhận về các Scene liên quan nhất, mỗi cái trỏ đúng timecode**,
so that **tôi tìm được cảnh mà không cần từ khoá khớp lời thoại**.

## Acceptance Criteria

1. **Given** Scene đã `search_status="indexed"` (Story 1.6), **When** gọi `POST /api/v1/search` với `{"query": "<câu NL>", "limit": <int>}`, **Then** hệ nhúng câu truy vấn (BGE-M3 — cùng model dựng `scene_embedding` ở Story 1.6), chạy ANN trên `scene_embedding` (pgvector), rerank **có điều kiện** (bge-reranker-v2-m3), và trả envelope `{results:[{scene_id, video_id, start_ms, end_ms, score, thumbnail_url, highlights}], meta}` — [Source: FR-6, #AD-8, #AD-13].
2. **Given** một Scene có `scene_document` (Story 1.6) mô tả nội dung thị giác không xuất hiện trong `transcript`/`ocr_text`, **When** truy vấn NL mô tả đúng nội dung thị giác đó, **Then** Scene này vẫn được trả về (khớp qua embedding ngữ nghĩa, không cần khớp từ khoá) — [Source: FR-6].
3. **Given** một Scene chưa `search_status="indexed"` HOẶC `scene_embedding.doc_version` lệch với checksum hiện tại của `scene.scene_document`, **Then** Scene này KHÔNG xuất hiện trong kết quả tìm kiếm — [Source: #AD-16, #AD-17].
4. **Given** danh sách candidate sau ANN đã sắp theo điểm, **When** điểm chuẩn hoá #1 vượt điểm #2 một khoảng đủ lớn (`rerank_skip_gap`), **Then** bỏ qua bước rerank (trả thẳng theo điểm ANN chuẩn hoá); **ngược lại** gọi rerank (bge-reranker-v2-m3) trên pool candidate và sắp lại theo điểm rerank — [Source: #AD-8].
5. p95 độ trễ mục tiêu `[ASSUMPTION: ≤2s]` — thiết kế để đạt được (embed câu truy vấn 1 lần + ANN có index + rerank có điều kiện chỉ trên pool nhỏ), nhưng **xác nhận ngưỡng thật cần model server thật chạy** (embedder/reranker vẫn ở trạng thái guarded, chưa kết nối môi trường dev — giống đúng precedent NFR-1 ở Story 1.7), ngoài phạm vi test tự động của story này — [Source: NFR-3].

## Tasks / Subtasks

- [x] **Task 1 — Tách `doc_version` thành helper dùng chung** (AC: #3): `shared/versioning.py` (mới):
  - [x] Chuyển hàm `doc_version(scene_document: str) -> str` (sha256 hex) từ `pipeline/embed_index.py` sang `shared/versioning.py` — **giữ nguyên hành vi/signature 100%**, không đổi logic.
  - [x] `pipeline/embed_index.py`: xoá định nghĩa cục bộ, `from shared.versioning import doc_version` — không đổi gì khác trong file, test hiện có (`tests/test_embed_index.py`) phải pass nguyên vẹn không sửa.
  - [x] **Lý do bắt buộc** (đọc kỹ Dev Notes AD-2): `search/` **không được phép** import từ `pipeline/` (ranh giới ingest/search tách biệt). `search/` cần cùng logic freshness-check (so `scene_embedding.doc_version` với checksum hiện tại của `scene.scene_document`) mà Story 1.6 đã viết trong `pipeline/embed_index.py` — chỗ dùng chung hợp lệ duy nhất là `shared/`.

- [x] **Task 2 — Migration `0008`: ANN index cho `scene_embedding`** (AC: #1, #5): `migrations/versions/0008_scene_embedding_ann_index.py`, nối tiếp `0007`:
  - [x] `op.execute("CREATE INDEX ix_scene_embedding_ann ON scene_embedding USING hnsw (embedding vector_cosine_ops)")` — HNSW, cùng operator class `vector_cosine_ops` khớp với `.cosine_distance()` sẽ dùng ở Task 6. `[ASSUMPTION]`: HNSW (không phải IVFFlat) — kiến trúc/stack-verification không chốt loại index cụ thể, HNSW là lựa chọn mặc định hợp lý cho pgvector 0.8.x ở quy mô MVP.
  - [x] `downgrade()`: `op.execute("DROP INDEX IF EXISTS ix_scene_embedding_ann")`.
  - [x] **Raw SQL qua `op.execute`, KHÔNG khai báo `Index(...)` ở `shared/models.py`** — cùng lý do Story 1.6 tránh `TSVECTOR` trong ORM: fixture test dùng `Base.metadata.create_all` trên sqlite (`tests/conftest.py`), và một `Index` với `postgresql_using="hnsw"` sẽ cố chạy trên sqlite khi `create_all` thực thi, làm vỡ toàn bộ test suite. Index chỉ tồn tại qua migration, không qua ORM metadata.

- [x] **Task 3 — Settings mới** (AC: #1, #4): `shared/config.py`, theo đúng pattern field có default + `Field()` validation (học từ code review Story 1.7):
  - [x] `rerank_model_url: str = "http://localhost:8003"` — Model Server mới (bge-reranker-v2-m3, vLLM/OpenAI-compatible, AD-14), theo đúng nhóm comment với `describe_model_url`/`embed_model_url`.
  - [x] `search_pool_size: int = Field(default=20, gt=0)` — `[ASSUMPTION]` số candidate ANN lấy về trước khi lọc freshness + rerank (đủ lớn để rerank có ý nghĩa, đủ nhỏ để nhanh).
  - [x] `rerank_skip_gap: float = Field(default=0.15, ge=0.0, le=1.0)` — `[ASSUMPTION]` ngưỡng khoảng cách điểm chuẩn hoá #1 vs #2 để bỏ qua rerank (AC #4).

- [x] **Task 4 — `search/query_embed.py`** (module mới, AC: #1): `QueryEmbedder` Protocol (`embed(self, text: str) -> list[float]`) + `BgeM3QueryEmbedder` adapter — **file mới trong `search/`, KHÔNG import `pipeline/embed_backends.py`** (ranh giới AD-2, xem Dev Notes). Cùng pattern HTTP y hệt `pipeline/embed_backends.py::BgeM3Embedder` (POST `{embed_model_url}/v1/embeddings`, `model: "BGE-M3"`, bọc lỗi `httpx.HTTPError`→`RuntimeError`, bọc lỗi hình dạng response, validate chiều = `SCENE_EMBEDDING_DIM` từ `shared.models`) — **dùng chung `settings.embed_model_url`** (cùng Model Server BGE-M3 thật với ingest, chỉ khác text đầu vào là câu truy vấn thay vì `scene_document`; chia sẻ **config** là hợp lệ, chỉ cấm chia sẻ **import code** giữa `pipeline/`↔`search/`). Đánh dấu `# pragma: no cover - phụ thuộc production` như các adapter trước.

- [x] **Task 5 — `search/rerank.py`** (module mới, AC: #4): `Reranker` Protocol (`rerank(self, query: str, passages: list[str]) -> list[float]` — trả điểm liên quan song song với `passages`, đã chuẩn hoá 0–1 `[ASSUMPTION: sigmoid trên logit thô, theo thực hành phổ biến của bge-reranker-v2-m3]`) + `BgeRerankerV2M3` adapter — cùng pattern HTTP với `pipeline/describe_backends.py`/`pipeline/embed_backends.py` (POST tới `{rerank_model_url}/...`, bọc lỗi 2 tầng y hệt, `# pragma: no cover - phụ thuộc production`). Endpoint path/payload cụ thể của Model Server bge-reranker-v2-m3 chưa xác nhận thực nghiệm (server thật chưa chạy) — implement theo OpenAI-compatible rerank convention phổ biến nhất, ghi rõ `[ASSUMPTION]` để điều chỉnh khi có server thật.

- [x] **Task 6 — `search/candidates.py`** (module mới, AC: #1, #2, #3): `async def fetch_ann_candidates(session: AsyncSession, query_embedding: list[float], *, pool_size: int) -> list[dict]`:
  - [x] Query: `SELECT Scene.scene_id, Scene.video_id, Scene.start_ms, Scene.end_ms, Scene.scene_document, SceneEmbedding.doc_version` JOIN `scene_embedding` theo `scene_id`, `WHERE Scene.search_status == "indexed"`, `ORDER BY SceneEmbedding.embedding.cosine_distance(query_embedding)`, `LIMIT pool_size`. Trả `list[dict]` gồm thêm `ann_distance` (giá trị cosine_distance thô, dùng ở Task 7).
  - [x] **CHỈ chạy đúng trên Postgres thật — KHÔNG unit-test được qua sqlite fixture** (xem "⚠️ Rủi ro kỹ thuật đã kiểm chứng thực nghiệm" ở Dev Notes — đã verify thực nghiệm trong phiên tạo story này: `.cosine_distance()` sinh SQL `embedding <=> ?`, sqlite ném `OperationalError: near ">": syntax error`). Đánh dấu `# pragma: no cover - phụ thuộc Postgres/pgvector thật`, xác minh thủ công khi có Postgres.
  - [x] Đây là **ranh giới duy nhất** chạm DB trực tiếp bằng cosine distance — mọi logic còn lại (lọc freshness, quyết định rerank, dựng envelope) phải là hàm thuần ở Task 7 để unit-test được đầy đủ bằng fake data.

- [x] **Task 7 — `search/rank.py`** (module mới, hàm thuần — AC: #1, #3, #4): 
  - [x] `filter_fresh_candidates(candidates: list[dict]) -> list[dict]`: giữ lại candidate có `doc_version(c["scene_document"]) == c["doc_version"]` (dùng `shared.versioning.doc_version` từ Task 1); loại candidate lệch phiên bản (AC #3, AD-16).
  - [x] `normalize_ann_score(distance: float) -> float`: `max(0.0, min(1.0, 1.0 - distance))` — cosine_distance → điểm 0–1 (0=không liên quan, 1=giống hệt). `[ASSUMPTION]` công thức chuẩn hoá — kiến trúc chỉ định nghĩa `score` là "điểm rerank chuẩn hoá" cho trường hợp CÓ rerank; công thức này chỉ áp dụng khi rerank bị bỏ qua.
  - [x] `maybe_rerank(candidates: list[dict], reranker: Reranker, query: str, *, gap_threshold: float) -> list[dict]`: sort candidates theo `normalize_ann_score(ann_distance)` giảm dần; nếu `len(candidates) < 2` hoặc `score[0] - score[1] >= gap_threshold` → gán `score = normalize_ann_score(...)` cho từng candidate, giữ nguyên thứ tự (AC #4, nhánh bỏ rerank); ngược lại gọi `reranker.rerank(query, [c["scene_document"] for c in candidates])`, gán kết quả vào `score`, sort lại giảm dần theo `score` (AC #4, nhánh rerank).
  - [x] `build_envelope(ranked: list[dict], *, limit: int) -> tuple[list[dict], dict]`: trả `(results, meta)` — `results` = `ranked[:limit]` map sang `{"scene_id", "video_id", "start_ms", "end_ms", "score", "thumbnail_url": f"/api/v1/scenes/{scene_id}/thumbnail", "highlights": []}`; `meta = {"next_cursor": None, "count": len(results)}`. **`highlights: []` cố định ở story này** (siêu dữ liệu khớp từ khoá là việc của Story 2.2 full-text — chưa có nguồn để highlight ở đường thuần ngữ nghĩa); **`thumbnail_url` chỉ là chuỗi URL theo convention resource-URL** (`/api/v1/scenes/<scene_id>`, AD-13) — **KHÔNG** tra `Shot.keyframe_key`/dựng ảnh thật, vì endpoint phục vụ thumbnail thật (đọc storage qua auth, AD-19) là phạm vi Story 3.1 (Epic 3), chưa tồn tại. Đây là quyết định phạm vi có chủ đích — xem Dev Notes.
  - [x] Toàn bộ 4 hàm trên là **hàm thuần, không chạm DB/HTTP** — unit-test đầy đủ bằng dict/fake giả lập ở Task 10.

- [x] **Task 8 — `search/service.py`** (module mới, orchestration — AC: #1-#4): `async def search(session: AsyncSession, embedder: QueryEmbedder, reranker: Reranker, query: str, *, limit: int, pool_size: int, gap_threshold: float) -> tuple[list[dict], dict]`: `query_vec = embedder.embed(query)` → `candidates = await fetch_ann_candidates(session, query_vec, pool_size=pool_size)` → `fresh = filter_fresh_candidates(candidates)` → `ranked = maybe_rerank(fresh, reranker, query, gap_threshold=gap_threshold)` → `return build_envelope(ranked, limit=limit)`. Đây là hàm duy nhất `api/routes_search.py` gọi.

- [x] **Task 9 — `api/routes_search.py`** (mới, AC: #1): cùng pattern `api/routes_ingest.py`:
  - [x] `router = APIRouter(prefix="/api/v1")`; `class SearchRequest(BaseModel): query: str; limit: int = 10`.
  - [x] `POST /search`: dựng `BgeM3QueryEmbedder(settings)` + `BgeRerankerV2M3(settings)`, gọi `search(session, embedder, reranker, req.query, limit=req.limit, pool_size=settings.search_pool_size, gap_threshold=settings.rerank_skip_gap)`, trả `ok(results=results, meta=meta)` (`api/envelope.py`, cùng convention `/jobs/{job_id}`/`/metrics`).
  - [x] `api/main.py`: `from api.routes_search import router as search_router`; `app.include_router(search_router)`.

- [x] **Task 10 — Test** (AC: #1-#4, trừ Task 2/4/5/6 là hạ tầng/HTTP/Postgres-only không unit-test qua sqlite được):
  - [x] `tests/test_versioning.py` (hoặc gộp vào `tests/test_embed_index.py`): `doc_version()` sau khi chuyển sang `shared/versioning.py` vẫn tất định, cùng hành vi cũ; `tests/test_embed_index.py` hiện có phải pass **không sửa** (chỉ đổi nơi định nghĩa, không đổi hành vi).
  - [x] `tests/test_search_rank.py`: `filter_fresh_candidates` loại đúng candidate lệch `doc_version`, giữ candidate khớp; `normalize_ann_score` clamp đúng 0–1 (distance âm/vượt 2 vẫn trong khoảng); `maybe_rerank` — gap đủ lớn → bỏ qua rerank (fake reranker KHÔNG được gọi, assert bằng call-counter); gap nhỏ → gọi rerank, sort lại đúng theo điểm rerank trả về (dùng `FakeReranker` cùng pattern `FakeEmbedder` ở `tests/test_embed_index.py` — constructor nhận điểm trả về cố định + `raise_error` toggle); `< 2` candidate → không gọi rerank; `build_envelope` — đúng shape `{scene_id, video_id, start_ms, end_ms, score, thumbnail_url, highlights}`, `thumbnail_url` đúng convention `/api/v1/scenes/<id>/thumbnail`, `highlights == []`, `meta == {"next_cursor": None, "count": ...}`, cắt đúng `limit`.
  - [x] `tests/test_search_service.py`: `search()` end-to-end với `async_session` (sqlite) — **KHÔNG gọi `fetch_ann_candidates` thật** (mock/monkeypatch hàm này trả `list[dict]` giả lập trực tiếp, vì hàm đó cần Postgres thật — xem Task 6) + `FakeEmbedder`/`FakeReranker` — verify orchestration đúng thứ tự (embed → fetch → filter → rank → envelope), verify candidate lệch `doc_version`/không `indexed` (giả lập ở input fake, filter đã enforce ở Task 7 nên chỉ cần test qua `filter_fresh_candidates` trực tiếp — không cần dựng lại ở service test) không lọt vào kết quả cuối.
  - [x] `tests/test_search_route.py` (hoặc thêm vào `tests/test_metrics.py`-style file mới): test route registration qua `openapi()["paths"]` (cùng pattern `test_ingest_routes_registered`/`test_metrics_route_registered` — **không** gọi route thật qua `client` fixture vì cần Postgres/model server thật, đúng tiền lệ Story 1.7).
  - [x] `tests/test_config.py`: thêm test default + `Field` validation cho `search_pool_size`/`rerank_skip_gap` (cùng pattern `test_zero_or_negative_rejected` đã có từ code review Story 1.7 — `rerank_skip_gap` ngoài `[0,1]` phải bị từ chối).

### Review Findings

- [x] [Review][Patch] `filter_fresh_candidates`/`doc_version()` crash (`AttributeError`) nếu một Scene `indexed` có `scene_document=None` (cột nullable, không có ràng buộc NOT NULL/CHECK ở DB) [search/rank.py, shared/versioning.py] — **Fixed**: `filter_fresh_candidates` loại candidate `scene_document is None` như lệch phiên bản thay vì crash.
- [x] [Review][Patch] Embedding NaN/inf từ model server bị `normalize_ann_score` biến thành điểm "hoàn hảo" 1.0 một cách âm thầm (Python `min`/`max` short-circuit trên NaN) thay vì bị từ chối [search/query_embed.py, search/rank.py] — **Fixed**: `normalize_ann_score` trả `0.0` cho NaN/inf; `BgeM3QueryEmbedder.embed` từ chối embedding chứa giá trị không hữu hạn.
- [x] [Review][Patch] `RuntimeError` từ embedder/reranker (lỗi HTTP/model server) không được bắt ở `api/routes_search.py` — lộ 500 thô thay vì envelope lỗi chuẩn `err()` đã có sẵn trong codebase [api/routes_search.py] — **Fixed**: bắt `RuntimeError` → `HTTPException(502)` (đi qua exception handler chung `err()` có sẵn ở `api/main.py`, cùng pattern `routes_ingest.py`).
- [x] [Review][Patch] `SearchRequest.limit`/`query` không có validation — `limit` âm gây bug slice Python (`ranked[:-1]`), `query` rỗng/toàn khoảng trắng vẫn được nhúng và tìm [api/routes_search.py] — **Fixed**: `limit: Field(ge=1, le=100)`; `query` qua `field_validator` strip + từ chối rỗng.
- [x] [Review][Patch] Migration `0008` tạo index HNSW không có `CONCURRENTLY`/`IF NOT EXISTS` — khoá exclusive chặn ghi ingest suốt thời gian build; `upgrade()`/`downgrade()` không nhất quán idempotency (upgrade fail cứng nếu index đã tồn tại, downgrade no-op êm) [migrations/versions/0008_scene_embedding_ann_index.py] — **Fixed**: `CREATE/DROP INDEX CONCURRENTLY IF EXISTS/IF NOT EXISTS` trong `op.get_context().autocommit_block()`.
- [x] [Review][Patch] Gọi `httpx.post` đồng bộ (blocking) bên trong đường async `search()` — mỗi request search chặn toàn bộ event loop (kể cả `/health`) trong lúc chờ embed/rerank [search/query_embed.py, search/rerank.py, search/rank.py, search/service.py] — **Fixed**: chuyển `BgeM3QueryEmbedder.embed`/`BgeRerankerV2M3.rerank` sang `httpx.AsyncClient` + `await`; `QueryEmbedder`/`Reranker` Protocol, `maybe_rerank`, `search()` cập nhật thành `async`; Fake test class cập nhật tương ứng.
- [x] [Review][Defer] Pool ANN cạn (do `search_pool_size` cố định hoặc bị `filter_fresh_candidates` lọc bớt) trả về ít hơn `limit` yêu cầu, không có tín hiệu/widen-retry báo cho caller [search/service.py, search/candidates.py] — deferred, pre-existing thiết kế pool cố định
- [x] [Review][Defer] Không có HTTP client dùng chung/tái sử dụng connection — mỗi request dựng adapter mới; async-client patch cải thiện một phần nhưng chưa giải quyết pooling [search/query_embed.py, search/rerank.py, api/routes_search.py] — deferred, tối ưu hiệu năng
- [x] [Review][Defer] Không có health-check khởi động cho `rerank_model_url` — cùng khoảng trống có sẵn từ `describe_model_url`/`embed_model_url` (Story 1.6), không phải gap mới của story này [shared/config.py, api/main.py] — deferred, pre-existing
- [x] [Review][Defer] `zip(..., strict=True)` trong `maybe_rerank` sẽ raise `ValueError` không xử lý nếu một implementation `Reranker` khác (không phải `BgeRerankerV2M3`, vốn đã tự validate độ dài) trả sai số điểm [search/rank.py] — deferred, giả thuyết trên implementation chưa tồn tại
- [x] [Review][Defer] `search_pool_size=20`/`rerank_skip_gap=0.15` là `[ASSUMPTION]` chưa có eval/observability để tinh chỉnh — cùng pattern các tham số `[ASSUMPTION]` khác đã có (Story 1.6/1.7), chờ Epic 4 [shared/config.py] — deferred, pre-existing pattern

## Dev Notes

- **⚠️ Rủi ro kỹ thuật đã kiểm chứng thực nghiệm trước khi viết story này** (tránh disaster khi dev — đúng tiền lệ Story 1.6):
  - Đã test thủ công trong phiên tạo story: `SceneEmbedding.embedding.cosine_distance(vec)` sinh SQL Postgres `embedding <=> ?` — chạy **OK trên Postgres thật** (đây là cú pháp pgvector chuẩn) nhưng **CRASH trên sqlite** (`OperationalError: near ">": syntax error`) vì sqlite không hiểu operator `<=>`. Điều này **khác** với việc lưu trữ `Vector` column (đã verify OK trên sqlite từ Story 1.6) — vấn đề chỉ ở việc **query/sort theo khoảng cách**, không phải ở việc lưu.
  - **Hệ quả thiết kế bắt buộc**: `search/candidates.py::fetch_ann_candidates` (Task 6) là ranh giới DUY NHẤT chạm cosine-distance-query — hàm này **không** unit-test được qua fixture sqlite hiện có (`tests/conftest.py::async_session`), phải đánh dấu `# pragma: no cover` và xác minh thủ công với Postgres thật (giống các adapter HTTP `# pragma: no cover - phụ thuộc production` đã có). **Toàn bộ logic còn lại phải là hàm thuần** (Task 7: `filter_fresh_candidates`/`normalize_ann_score`/`maybe_rerank`/`build_envelope`) nhận `list[dict]` sẵn — unit-test đầy đủ bằng fake data, không đụng DB. Đừng cố viết test cho `fetch_ann_candidates` qua sqlite — sẽ luôn crash, không phải bug của story này.
- **AD-2 (CQRS-lite: ingest/search tách biệt) — ràng buộc cấu trúc quan trọng nhất của story này**: "ingest và search là hai tiến trình/triển khai tách biệt... không gọi hàm chéo trong tiến trình." `search/` **KHÔNG được import bất kỳ thứ gì từ `pipeline/`** (kể cả những thứ tưởng vô hại như `BgeM3Embedder`/`doc_version`). Đây là lý do Task 1 tách `doc_version` ra `shared/` (thay vì `search/` import thẳng `pipeline/embed_index.py::doc_version`), và Task 4 viết `BgeM3QueryEmbedder` **mới** trong `search/query_embed.py` thay vì import `pipeline/embed_backends.py::BgeM3Embedder` dù logic HTTP gần như giống hệt — chia sẻ **config** (`settings.embed_model_url`) là hợp lệ, chia sẻ **code/import** giữa hai module thì không. Nếu dev agent thấy trùng lặp code HTTP-client giữa `pipeline/embed_backends.py` và `search/query_embed.py`, đó là **chủ đích**, không phải thiếu DRY cần "dọn dẹp" — đừng gộp lại.
- **`thumbnail_url` — quyết định phạm vi có chủ đích**: AD-13 (envelope) yêu cầu field này tồn tại; AD-19 yêu cầu thumbnail thật chỉ phục vụ qua API-auth (stream/proxy từ storage). Story 3.1 (Epic 3, chưa tồn tại) mới là nơi implement endpoint phục vụ thumbnail thật (đọc `Shot.keyframe_key` qua storage-port). Story 2.1 chỉ trả **chuỗi URL** đúng convention resource-URL (`/api/v1/scenes/<scene_id>/thumbnail`) — endpoint đó **chưa được implement**, gọi sẽ 404 cho tới khi Story 3.1 xong. Đây KHÔNG phải một lỗi/thiếu sót cần dev agent tự ý "tiện thể" build thêm — ngoài phạm vi AC của story này, để dành đúng cho Story 3.1.
- **`highlights: []` cố định** — siêu dữ liệu khớp từ khoá (đoạn transcript/OCR chứa cụm truy vấn) chỉ có ý nghĩa khi có tìm kiếm từ khoá/FTS (Story 2.2, BM25/Postgres FTS). Đường ngữ nghĩa thuần (Story 2.1) không có "vị trí khớp từ khoá" để highlight — trả mảng rỗng đúng theo hợp đồng AD-13 (field tồn tại, giá trị rỗng là hợp lệ), Story 2.2 sẽ điền dữ liệu thật vào field này.
- **`score` — hai nguồn khác nhau tuỳ nhánh AC #4**: khi CÓ rerank, `score` = điểm trả về từ `Reranker.rerank()` (đã chuẩn hoá 0-1 theo `[ASSUMPTION]` sigmoid ở Task 5 — khớp đúng nghĩa kiến trúc "score = điểm rerank chuẩn hoá"). Khi BỎ rerank (gap đủ lớn), `score` = `normalize_ann_score(distance)` = `1 - cosine_distance` clamp [0,1] — một xấp xỉ hợp lý nhưng **không** phải "điểm rerank" theo đúng nghĩa đen kiến trúc định nghĩa; đây là `[ASSUMPTION]` cần thiết vì AD-8 tự nó cho phép bỏ rerank có điều kiện nên phải có giá trị `score` thay thế nào đó.
- **`search_pool_size`/`rerank_skip_gap` là tham số hoá, không hardcode** — cả hai đều `[ASSUMPTION]` (không có số cụ thể trong PRD/epics, giống `ratio_threshold`/`confidence_threshold` ở Story 1.6), để chỉnh sau khi có dữ liệu thật/eval (Epic 4).
- **NFR-3 (p95 ≤2s) không đo được bằng test tự động ở story này** — cùng lý do NFR-1 ở Story 1.7: model server thật (BGE-M3 cho query, bge-reranker-v2-m3) chưa kết nối môi trường dev, adapter vẫn guarded. Thiết kế (embed 1 lần + ANN có HNSW index + rerank có điều kiện chỉ trên `search_pool_size` candidate, không phải toàn kho) hướng tới đạt ngưỡng, nhưng xác nhận thật cần môi trường GPU/model-server thật, ngoài phạm vi story.
- **Không đụng `pipeline/`, `pipeline/workers.py`, hay bất kỳ story Epic 1 nào** — story này chỉ đọc dữ liệu (Scene/SceneEmbedding) đã được Epic 1 ghi sẵn, hoàn toàn read-only, đúng ranh giới CQRS-lite (AD-2).
- **Reranker Model Server endpoint/payload là `[ASSUMPTION]`** — chưa có server thật để verify thực nghiệm (khác Story 1.6 nơi format `/v1/embeddings` OpenAI-compatible đã có tiền lệ rõ từ `embed_backends.py`). Ghi rõ giả định trong code + docstring để điều chỉnh nhanh khi có Model Server bge-reranker-v2-m3 thật.

### Project Structure Notes

- **Lần đầu tạo thư mục `search/`** — đúng theo source tree đã định trong Architecture Spine (`search/ # Search Service: phễu 4 tầng (AD-8)`). File mới: `search/__init__.py` (rỗng), `search/query_embed.py`, `search/rerank.py`, `search/candidates.py`, `search/rank.py`, `search/service.py`.
- `shared/versioning.py` — file mới, tách từ `pipeline/embed_index.py` (Task 1).
- `api/routes_search.py` — router mới, song song `api/routes_ingest.py`/`api/routes_metrics.py`.
- Migration mới = `0008`, nối tiếp `0007` (Story 1.7).
- Không tạo `models/` (thư mục được nhắc trong source tree kiến trúc cho "nạp/serve model dùng chung") ở story này — Story 1.4-1.6 đã đặt adapter HTTP trong `pipeline/*_backends.py` (lệch nhẹ so với source tree lý tưởng), và story này tiếp tục đặt adapter phía search trong `search/*.py` (không phải `models/`) để tôn trọng ranh giới AD-2 (search không import pipeline) mà không cần refactor lại code Story 1.4-1.6 đã test kỹ — xem đánh đổi trong Dev Notes AD-2 ở trên. Không tự ý tạo `models/` hay di chuyển code cũ.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story-2.1]
- [Source: _bmad-output/planning-artifacts/architecture/architecture-scene-intelligence-2026-07-03/ARCHITECTURE-SPINE.md#AD-2,#AD-7,#AD-8,#AD-9,#AD-13,#AD-16,#AD-17,#AD-19,#AD-23] (dòng ~64-67 AD-2, ~90-92 AD-7, ~94-97 AD-8, ~99-102 AD-9, ~119-122 AD-13, ~134-137 AD-16, ~139-142 AD-17, ~149-152 AD-19, dòng 179-182 Consistency Conventions, dòng 255-267 source tree, dòng 278 capability map, dòng 288-300 Deferred: Qdrant/OpenSearch/query-understanding-LLM/sub-scene-chunking đều KHÔNG thuộc phạm vi story này)
- [Source: _bmad-output/planning-artifacts/architecture/architecture-scene-intelligence-2026-07-03/stack-verification.md] (bge-reranker-v2-m3, BGE-M3 "ăn khớp" reranker, pgvector 0.8.4 — không có index type/params cụ thể, story tự quyết HNSW)
- [Source: _bmad-output/planning-artifacts/prds/prd-scene-intelligence-2026-07-03/prd.md#FR-6, #NFR-3]
- [Source: _bmad-output/implementation-artifacts/1-6-scene-document-embedding-siet-nhieu-cong-index.md] (pattern `TextEmbedder` Protocol, `doc_version`/`index_scene`, adapter HTTP guarded, rủi ro kỹ thuật kiểm chứng thực nghiệm trước khi code)
- [Source: _bmad-output/implementation-artifacts/1-7-van-hanh-metrics-backup-tinh-ben.md] (precedent: NFR đo bằng thực nghiệm ngoài phạm vi test tự động khi model server chưa kết nối; `Field(gt=0)` validation cho setting số; test route qua `openapi()["paths"]` thay vì gọi thật cần hạ tầng thật)
- [Source: pipeline/embed_index.py, pipeline/embed_backends.py, pipeline/describe_backends.py, shared/models.py, shared/config.py, api/main.py, api/routes_ingest.py, api/routes_metrics.py, api/envelope.py, migrations/versions/0001_base_schema.py, migrations/versions/0006_scene_document_embedding.py, migrations/versions/0007_ingest_task_lease_metrics.py, tests/conftest.py, tests/test_embed_index.py, tests/test_config.py]
- Kiểm chứng thực nghiệm thực hiện trong phiên tạo story này: `pgvector.sqlalchemy.Vector.cosine_distance()` sinh SQL `embedding <=> ?` — hoạt động đúng theo cú pháp pgvector chuẩn nhưng raise `OperationalError` trên sqlite (`near ">": syntax error`).

## Dev Agent Record

### Agent Model Used

claude-sonnet-5 (BMad dev-story)

### Debug Log References

- `uv run pytest` → **97 passed** (83 trước + 14 mới: 1 `test_versioning.py` + 6 `test_search_rank.py` + 2 `test_search_service.py` + 1 `test_search_route.py` + 4 `test_config.py`).
- `uv run ruff check search/ pipeline/ api/ shared/ tests/ migrations/` → sạch.
- Kiểm chứng thực nghiệm lại `SceneEmbedding.embedding.cosine_distance()` (đã làm khi tạo story, xác nhận lại khi dev): sinh SQL `embedding <=> ?`, raise `OperationalError` trên sqlite. Đã tách `search/candidates.py::fetch_ann_candidates` làm ranh giới Postgres-only duy nhất (`# pragma: no cover`), toàn bộ logic còn lại (`search/rank.py`) là hàm thuần test được qua fake data.
- `search/candidates.py`, `search/query_embed.py`, `search/rerank.py`: **chưa chạy môi trường Postgres/Model Server thật** trong phiên dev này (không có hạ tầng thật truy cập được) — review kỹ bằng mắt theo đúng convention adapter đã có (`pipeline/embed_backends.py`/`describe_backends.py`), migration `0008` cũng chưa chạy `alembic upgrade head` thật.
- **Code review (6 patch áp dụng, xem Review Findings)**: `uv run pytest` → **105 passed** (97 + 8 mới). `uv run ruff check` → sạch. Migration `0008` module load-test (parse/syntax) qua `importlib` — chưa chạy `alembic upgrade head` thật với Postgres (vẫn thiếu hạ tầng thật trong phiên này).

### Completion Notes List

- **Task 1**: `doc_version()` tách sang `shared/versioning.py`, `pipeline/embed_index.py` import lại — hành vi/test không đổi (`tests/test_embed_index.py` pass nguyên vẹn).
- **Task 2**: Migration `0008` — index HNSW `vector_cosine_ops` trên `scene_embedding.embedding`, raw SQL qua `op.execute` (không khai báo `Index()` ở ORM — tránh vỡ `create_all` trên sqlite).
- **Task 3**: 3 setting mới (`rerank_model_url`, `search_pool_size` với `Field(gt=0)`, `rerank_skip_gap` với `Field(ge=0.0, le=1.0)`).
- **Task 4/5**: `search/query_embed.py::BgeM3QueryEmbedder` + `search/rerank.py::BgeRerankerV2M3` — adapter HTTP mới, cố ý KHÔNG import `pipeline/embed_backends.py` (ranh giới AD-2). Cả hai `# pragma: no cover - phụ thuộc production`.
- **Task 6**: `search/candidates.py::fetch_ann_candidates` — JOIN Scene+SceneEmbedding, filter `search_status="indexed"`, order theo `.cosine_distance()`. Chỉ chạy đúng Postgres thật, `# pragma: no cover`.
- **Task 7**: `search/rank.py` — 4 hàm thuần (`filter_fresh_candidates`, `normalize_ann_score`, `maybe_rerank`, `build_envelope`), unit-test đầy đủ.
- **Task 8**: `search/service.py::search()` orchestration embed→fetch→filter→rank→envelope.
- **Task 9**: `api/routes_search.py` (`POST /api/v1/search`) + đăng ký `search_router` trong `api/main.py`.
- **Task 10**: 5 file test mới/sửa (`test_versioning.py`, `test_search_rank.py`, `test_search_service.py`, `test_search_route.py`, `test_config.py` bổ sung) — 97/97 pass.
- ⚠️ `rerank_model_url` endpoint/payload (`/v1/rerank`, `{"model", "query", "documents"}` → `{"results": [{"index", "relevance_score"}]}`) là `[ASSUMPTION]` — chưa có Model Server bge-reranker-v2-m3 thật để verify, điều chỉnh khi có server thật (giống ghi chú Story 1.6 cho Qwen3-VL/BGE-M3 lúc đó).
- ⚠️ `search_pool_size=20`, `rerank_skip_gap=0.15` là `[ASSUMPTION]` — không có số cụ thể trong PRD/epics.
- AC #2 (truy vấn mô tả thị giác trả đúng Scene dù transcript không chứa từ khoá) là hệ quả tự nhiên của cơ chế embedding ngữ nghĩa (BGE-M3 nhúng `scene_document` đã gồm mô tả thị giác từ Story 1.6) — không có unit test riêng cho AC này vì cần embedding thật để verify ngữ nghĩa; cơ chế đã đúng theo thiết kế (embed query → ANN so khớp `scene_embedding` xây từ `scene_document`, không so khớp `transcript`/`ocr_text`).
- AC #5 (NFR-3 p95 ≤2s): không đo được bằng test tự động (model server chưa kết nối) — đã ghi rõ trong story, đúng precedent NFR-1 Story 1.7.
- **Code review (6 patch áp dụng)**: (1) `filter_fresh_candidates` loại `scene_document=None` thay vì crash; (2) `normalize_ann_score` trả `0.0` cho NaN/inf + `BgeM3QueryEmbedder` từ chối embedding không hữu hạn; (3) `api/routes_search.py` bắt `RuntimeError` từ embedder/reranker → `HTTPException(502)`; (4) `SearchRequest.limit` (`Field(ge=1, le=100)`) + `query` (`field_validator` strip/từ chối rỗng); (5) migration `0008` dùng `CREATE/DROP INDEX CONCURRENTLY IF [NOT] EXISTS` trong `autocommit_block()`; (6) chuyển `BgeM3QueryEmbedder`/`BgeRerankerV2M3` sang `httpx.AsyncClient` (không còn chặn event loop), `QueryEmbedder`/`Reranker` Protocol + `maybe_rerank`/`search()` thành `async`. 5 finding defer ghi vào `deferred-work.md` (pool ANN cạn không tín hiệu, thiếu HTTP client dùng chung, thiếu health-check `rerank_model_url`, `zip(strict=True)` giả thuyết, `[ASSUMPTION]` chưa eval). 5 finding dismiss (đã là quyết định phạm vi tường minh trong story hoặc thiết kế hợp lý không phải lỗi).

### File List

- **Mới**: `shared/versioning.py`, `migrations/versions/0008_scene_embedding_ann_index.py`, `search/query_embed.py`, `search/rerank.py`, `search/candidates.py`, `search/rank.py`, `search/service.py`, `api/routes_search.py`, `tests/test_versioning.py`, `tests/test_search_rank.py`, `tests/test_search_service.py`, `tests/test_search_route.py`
- **Sửa**: `pipeline/embed_index.py` (import `doc_version` từ `shared.versioning`), `shared/config.py` (`rerank_model_url`, `search_pool_size`, `rerank_skip_gap`), `api/main.py` (đăng ký `search_router`), `tests/test_config.py` (test settings mới), `_bmad-output/implementation-artifacts/deferred-work.md` (5 mục defer từ code review)

## Change Log

- 2026-07-03 — Story 2.1: `POST /api/v1/search` (Search Service đầu tiên, phễu ANN + rerank có điều kiện) — nhúng câu truy vấn (BGE-M3), ANN qua pgvector (HNSW index mới), lọc `search_status="indexed"` + freshness `doc_version` (AD-16/17), rerank có điều kiện (bge-reranker-v2-m3, bỏ khi #1 bỏ xa #2), envelope `{results, meta}` (AD-13). Tách `doc_version` sang `shared/versioning.py` để tôn trọng ranh giới CQRS-lite ingest/search (AD-2). 97/97 test pass, ruff clean.
- 2026-07-04 — Code review: 6 patch áp dụng (crash `scene_document=None`, NaN/inf embedding → điểm giả, lỗi model server lộ 500 thô, thiếu validation `limit`/`query`, migration index chặn ghi, HTTP đồng bộ chặn event loop) + 8 test mới. 105/105 test pass, ruff clean. 5 finding defer, 5 dismiss.
