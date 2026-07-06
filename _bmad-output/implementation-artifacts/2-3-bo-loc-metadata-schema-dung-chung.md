---
baseline_commit: 0cb9db220c44412c3ea57954990fb4ba116ac934
---

# Story 2.3: Bộ lọc metadata theo schema dùng chung

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a **biên tập viên**,
I want **thu hẹp kết quả theo độ dài Scene và có mặt người (ai nếu đã đăng ký)**,
so that **tôi tới đúng loại cảnh nhanh hơn**.

## Scope Decision (đã xác nhận với Lan)

FR-7 liệt kê 4 loại bộ lọc tối thiểu: cỡ cảnh (cận/trung/toàn), có mặt người, độ dài Scene, "không dính logo/bug đài" — chính PRD đã đánh dấu `[ASSUMPTION: tập bộ lọc tối thiểu; có thể mở rộng theo phản hồi phòng biên tập]`. Hiện trạng codebase:

- **Độ dài** (`end_ms - start_ms`) và **có mặt người** (`face_appearance`, Story 1.5) đã có tín hiệu ghi sẵn từ Epic 1 → **implement đầy đủ trong story này**.
- **Cỡ cảnh** chỉ tồn tại dưới dạng cụm từ trong prose "Bối cảnh" của `scene_document` (Qwen3-VL, Story 1.6) — KHÔNG phải trường có cấu trúc.
- **"Không dính logo"** chưa có bất kỳ model/stage phát hiện logo nào trong stack (`stack-verification.md` không nhắc tới).

Quyết định scope (Lan xác nhận qua AskUserQuestion): **MVP hẹp** — implement schema dùng chung (AD-21) + cơ chế lọc đầy đủ cho 2 thuộc tính ĐÃ có tín hiệu (độ dài, người). `shot_size`/`has_logo` KHÔNG khai báo trong `SceneFilters` ở story này (khai báo field mà không ai ghi dữ liệu → filter luôn rỗng, tệ hơn không có) — ghi rõ là công việc deferred (thêm stage ingest mới, ngoài phạm vi story), note vào `deferred-work.md` ở Task 1. Đây đúng tinh thần AD-21 "thêm bộ lọc mới = sửa schema chung" — schema mở rộng được, nhưng KHÔNG mở rộng bằng field rỗng.

## Acceptance Criteria

1. **Given** một truy vấn kèm bộ lọc `min_duration_ms`/`max_duration_ms`, **When** gọi `POST /api/v1/search`, **Then** chỉ Scene có `end_ms - start_ms` nằm trong khoảng cho trước được trả về — áp dụng ở CẢ hai nhánh ANN và FTS (trước khi RRF merge) — [Source: FR-7, AD-8].
2. **Given** bộ lọc `has_person=true`, **When** search chạy, **Then** chỉ Scene có ít nhất một `face_appearance` (bất kể đã xác định danh tính hay "không xác định" — AD-11) được trả; **Given** bộ lọc `person_id=<id>` cụ thể (người đã đăng ký), **Then** chỉ Scene có `face_appearance.person_id` khớp đúng người đó được trả — [Source: FR-7, AD-11].
3. **Given** phễu 4 tầng cố định (AD-8), **When** search có bộ lọc, **Then** filter áp dụng ở **tầng SQL filter đầu tiên** — trong CÙNG câu SELECT với `search_status == "indexed"` (AD-17) ở cả `fetch_ann_candidates` và `fetch_fts_candidates`, TRƯỚC `ORDER BY`/`LIMIT pool_size` — không có đường nào vòng qua filter để lọt vào pool trước rồi mới lọc sau — [Source: AD-8, AD-21].
4. **Given** bộ lọc kết hợp với truy vấn NL trong CÙNG một lần gọi `POST /api/v1/search` (`query` + `filters` cùng request body), **When** search chạy, **Then** kết quả vừa khớp ngữ nghĩa/từ khoá vừa thoả mãn TẤT CẢ điều kiện lọc đã cho (AND, không phải OR) — [Source: FR-7].
5. **Given** tập thuộc tính lọc khai báo trong MỘT schema dùng chung `shared/filters.py` (`SceneFilters` + `apply_scene_filters`), **When** `search/candidates.py`, `search/fts_candidates.py`, và `api/routes_search.py` cần áp dụng/khai báo bộ lọc, **Then** cả ba đều import và dùng lại đúng `SceneFilters`/`apply_scene_filters` — không định nghĩa field lọc rời hoặc trùng lặp logic filter ở search hay route — [Source: AD-21].
6. **Given** `max_duration_ms < min_duration_ms` (hoặc giá trị âm), **When** khởi tạo `SceneFilters`, **Then** validation raise lỗi ngay tại schema (Pydantic), không lọt xuống tầng SQL để trả kết quả sai lặng lẽ — [Source: AD-21].

## Tasks / Subtasks

- [x] **Task 1 — `shared/filters.py` (module mới): schema `SceneFilters`** (AC: #5, #6):
  - [x] `class SceneFilters(BaseModel)`: `min_duration_ms: int | None = Field(default=None, ge=0)`, `max_duration_ms: int | None = Field(default=None, ge=0)`, `has_person: bool | None = None`, `person_id: str | None = None`.
  - [x] `@model_validator(mode="after")`: nếu cả `min_duration_ms` và `max_duration_ms` đều có giá trị và `max_duration_ms < min_duration_ms` → raise `ValueError` (AC #6).
  - [x] Docstring trích dẫn AD-21 nguyên văn + ghi rõ: đây là **schema dùng chung duy nhất** cho thuộc tính lọc Scene — `search/candidates.py`, `search/fts_candidates.py`, `api/routes_search.py` PHẢI import type này, KHÔNG tự khai báo field lọc rời (AC #5). Nêu rõ phạm vi: chỉ 2/4 filter tối thiểu của FR-7 (độ dài + người); `shot_size` (cận/trung/toàn) và "không dính logo" CHƯA có tín hiệu ingest (chỉ prose trong `scene_document`, Story 1.6; chưa có model logo detector nào trong stack) — cố tình KHÔNG khai báo field rỗng ở đây, xem entry deferred-work bên dưới.
  - [x] Thêm entry mới vào `_bmad-output/implementation-artifacts/deferred-work.md` (mục "Deferred from: story creation 2.3"): `shot_size`/`has_logo` filter (FR-7) cần stage ingest mới (structured shot-size extraction từ Qwen3-VL hoặc model riêng; logo/bug-đài detector chưa chọn) — ngoài phạm vi story này, cần story riêng ở Epic 1/2 khi có yêu cầu cụ thể từ phòng biên tập.

- [x] **Task 2 — `shared/filters.py`: `apply_scene_filters` (hàm thuần SQLAlchemy Core, AC: #1, #2, #3)**:
  - [x] `def apply_scene_filters(stmt: Select, filters: SceneFilters | None) -> Select` — nhận một `Select` đã `.join`/`.where` sẵn trên `Scene` (bất kể ANN hay FTS), trả về `Select` đã thêm `.where(...)` theo field nào có giá trị trong `filters` (bỏ qua field `None`). `filters is None` → trả nguyên `stmt` không đổi.
  - [x] Độ dài: `(Scene.end_ms - Scene.start_ms)` so với `min_duration_ms`/`max_duration_ms` — chỉ thêm cận nào có giá trị (`>=` cho min, `<=` cho max, cả hai nếu có cả hai).
  - [x] `has_person=True` → `exists(select(FaceAppearance.appearance_id).where(FaceAppearance.scene_id == Scene.scene_id))`; `has_person=False` → phủ định (`~exists(...)`) — Scene không có bất kỳ `face_appearance` nào (kể cả "không xác định", vì bảng `face_appearance` ghi MỌI khuôn mặt phát hiện được, `person_id` mới là cột nullable cho danh tính — AD-11).
  - [x] `person_id=<id>` → `exists(select(FaceAppearance.appearance_id).where(FaceAppearance.scene_id == Scene.scene_id, FaceAppearance.person_id == filters.person_id))` — khớp đúng người đã đăng ký, độc lập với `has_person` (dùng kết hợp được cả hai, dù thường dư — `person_id` tự ngụ ý `has_person=True`).
  - [x] Hàm thuần trên SQLAlchemy Core (không dùng hàm riêng dialect nào như `cosine_distance`/`to_tsvector`) → dialect-độc-lập, unit-test được qua sqlite fixture (Task 4), KHÁC với `fetch_ann_candidates`/`fetch_fts_candidates` (Postgres-only).

- [x] **Task 3 — Wire `apply_scene_filters` vào cả hai nhánh candidate fetch** (AC: #1, #2, #3):
  - [x] `search/candidates.py::fetch_ann_candidates`: thêm tham số `filters: SceneFilters | None = None`; gọi `q = apply_scene_filters(q, filters)` NGAY SAU `.where(Scene.search_status == "indexed")`, TRƯỚC `.order_by("ann_distance").limit(pool_size)` — filter phải cắt bớt trước khi `LIMIT` giới hạn pool (AC #3, đúng thứ tự phễu AD-8).
  - [x] `search/fts_candidates.py::fetch_fts_candidates`: thêm tham số `filters: SceneFilters | None = None`; áp `apply_scene_filters` vào subquery `limited` (biến `.where(Scene.search_status == "indexed", tsvector.op("@@")(tsquery))` thành `.where(...)` rồi gọi `apply_scene_filters` trên statement TRƯỚC `.order_by(rank_expr.desc()).limit(pool_size).subquery()`) — GIỮ NGUYÊN kỷ luật subquery-trước-`ts_headline` từ code review Story 2.2 (KHÔNG áp filter ở tầng ngoài, nơi `ts_headline` đã tính).
  - [x] Cập nhật docstring hai hàm nhắc `filters` tham số tuỳ chọn, mặc định `None` = không lọc (backward-compatible với lời gọi hiện có).
  - [x] Verify thứ tự filter TRƯỚC `ORDER BY`/`LIMIT` (AC #3) bằng compiled-SQL statement (dialect `postgresql`, không cần Postgres sống) — cùng kỹ thuật code review Story 2.2 đã dùng để verify `ts_headline` nằm sau `LIMIT`; ở đây verify ngược lại: predicate filter (vd `end_ms - start_ms <= :max`) PHẢI xuất hiện trong mệnh đề `WHERE` TRƯỚC `LIMIT`/`ORDER BY` trong SQL đã compile, không phải lọc ở tầng ngoài sau khi đã cắt pool. Đã verify thủ công: ANN — filter nằm trong `WHERE` trước `LIMIT`; FTS — filter nằm TRONG subquery `anon_1` trước `LIMIT`, `ts_headline` vẫn ở tầng ngoài (đúng cấu trúc Story 2.2).

- [x] **Task 4 — Test filter logic thuần** (AC: #1, #2, #3, #6): `tests/test_filters.py` (mới), dùng fixture `async_session` (sqlite in-memory, `Base.metadata.create_all` đã có sẵn `Scene`/`FaceAppearance`/`Person`):
  - [x] `SceneFilters` validation: `max_duration_ms < min_duration_ms` raise `ValidationError`; tất cả field mặc định `None` (không lọc gì); âm (`ge=0`) bị từ chối cho cả `min_duration_ms`/`max_duration_ms`.
  - [x] `apply_scene_filters` với `filters=None` → trả stmt không đổi (so sánh kết quả execute giống hệt không-filter).
  - [x] Insert 1 `Video` + nhiều `Scene` với `start_ms`/`end_ms` khác nhau (độ dài đa dạng: 500ms, 2000ms, 10000ms) + một số `Scene` có `face_appearance` (một số kèm `person_id` trỏ `Person` đã tạo, một số `person_id=None` = "không xác định") + một số Scene không có `face_appearance` nào.
  - [x] Test `min_duration_ms` riêng, `max_duration_ms` riêng, cả hai cùng lúc (khoảng đóng cả hai đầu) — đúng tập `scene_id` mong đợi.
  - [x] Test `has_person=True` → đúng tập Scene có ≥1 `face_appearance` (kể cả `person_id=None`); `has_person=False` → đúng tập Scene KHÔNG có `face_appearance` nào.
  - [x] Test `person_id=<id cụ thể>` → chỉ Scene có `face_appearance.person_id` khớp; Scene có face "không xác định" (`person_id=None`) KHÔNG lọt dù có mặt người.
  - [x] Test kết hợp `min_duration_ms` + `has_person=True` cùng lúc → giao (AND) đúng, không phải hợp (OR).

- [x] **Task 5 — `search/service.py::search()`: xuyên tham số `filters`** (AC: #1-#5):
  - [x] Thêm tham số `filters: SceneFilters | None = None` vào chữ ký `search(...)`.
  - [x] Truyền `filters=filters` vào CẢ `fetch_ann_candidates(...)` và `fetch_fts_candidates(...)` — cùng một `SceneFilters`, không tách filter riêng cho từng nhánh (AC #4: kết hợp NL + filter trong cùng lần tìm, áp dụng nhất quán cả hai nhánh trước khi RRF).

- [x] **Task 6 — `api/routes_search.py`: nhận `filters` qua request body** (AC: #4, #5):
  - [x] `SearchRequest` thêm field `filters: SceneFilters | None = None` — **import trực tiếp `SceneFilters` từ `shared/filters.py`**, KHÔNG khai báo lại field lọc rời trong `SearchRequest` (AC #5; Pydantic nested model tự động validate khi FastAPI parse body).
  - [x] `search_endpoint` truyền `filters=req.filters` vào lời gọi `search(...)` hiện có (thêm vào cạnh `k=settings.rrf_k`) — không đổi logic mapping lỗi 502 hiện có.

- [x] **Task 7 — Test wiring end-to-end (thuần, monkeypatch fetcher — không cần Postgres thật)** (AC: #4, #5):
  - [x] `tests/test_search_service.py`: cập nhật `_patch_fetchers`/fake `_fake_ann`/`_fake_fts` để nhận thêm tham số `filters` (giữ nguyên hành vi trả `ann`/`fts` cho trước); thêm test mới verify `search(..., filters=SceneFilters(min_duration_ms=1000))` được CHUYỂN TIẾP nguyên vẹn tới cả hai fake fetcher (assert fake nhận đúng object `filters` truyền vào, qua `nonlocal`/list capture) — không test lại logic SQL (đã test ở Task 4).
  - [x] `tests/test_search_route.py`: test `SearchRequest(query="q", filters=SceneFilters(has_person=True))` parse hợp lệ; test `SearchRequest(query="q", filters={"max_duration_ms": -1})` raise `ValidationError` (kế thừa validation từ `SceneFilters`, không cần logic riêng ở route); test `search_endpoint` (monkeypatch `search`) nhận đúng `filters=req.filters` trong kwargs gọi xuống.

### Review Findings

- [x] [Review][Patch] `SceneFilters` không có `extra="forbid"` — client gửi field không tồn tại (vd chính `shot_size`/`has_logo` mà story cố tình chưa hỗ trợ) bị Pydantic âm thầm bỏ qua thay vì báo lỗi, khiến client tưởng filter có tác dụng [shared/filters.py:379-395] — **Fixed**: thêm `model_config = ConfigDict(extra="forbid")`.
- [x] [Review][Patch] Verify AC #3 (filter predicate nằm TRƯỚC `ORDER BY`/`LIMIT` ở cả `fetch_ann_candidates` và `fetch_fts_candidates`) hiện chỉ là compiled-SQL kiểm tra thủ công trong phiên dev + ghi lại bằng lời trong Dev Agent Record, KHÔNG có test tự động khoá lại invariant này trong repo — regression tương lai (vd ai đó dời `apply_scene_filters` xuống sau `.limit()`) sẽ không bị bất kỳ test nào bắt được [search/candidates.py:40-42, search/fts_candidates.py:49-68] — **Fixed**: `tests/test_candidates_filter_order.py` (mới) — fake session bắt statement thật, compile (dialect postgresql) và assert vị trí predicate trước `LIMIT` cho cả hai nhánh.
- [x] [Review][Patch] `has_person=False` kết hợp `person_id=<id>` trong cùng request là tự mâu thuẫn (NOT EXISTS mọi face_appearance VÀ EXISTS đúng person_id) → luôn ra kết quả rỗng, không có validation nào cảnh báo — client không biết mình gửi filter vô nghĩa [shared/filters.py:415-431] — **Fixed**: `model_validator` mới `_has_person_false_not_with_person_id` raise `ValueError`.
- [x] [Review][Patch] `person_id` là `str | None` không có ràng buộc độ dài — chuỗi rỗng `""` lọt qua validation, tạo ra "không tìm thấy" âm thầm giống hệt gõ sai id, không có tín hiệu lỗi rõ ràng cho client [shared/filters.py:385] — **Fixed**: `Field(default=None, min_length=1)`.
- [x] [Review][Patch] Không có test cho trường hợp `person_id` trỏ tới một `Person` không tồn tại trong bảng `person` — Dev Notes khẳng định hành vi (EXISTS trả `False`, không crash) nhưng chưa có test nào seed một `person_id` không tồn tại để xác nhận [tests/test_filters.py] — **Fixed**: `test_apply_scene_filters_person_id_nonexistent_returns_empty`.
- [x] [Review][Defer] Diff không cập nhật OpenAPI example/response schema documentation cho field `SearchRequest.filters` mới (nested model + validator) — client API bên ngoài không có ví dụ payload cho tính năng lọc mới [api/routes_search.py] — deferred, tài liệu/DX, không ảnh hưởng hành vi runtime.
- [x] [Review][Defer] Không có test/guard cho dữ liệu `Scene` hỏng (`end_ms < start_ms`, ra `duration` âm) khi áp `min_duration_ms`/`max_duration_ms` — về lý thuyết `duration` âm vẫn xử lý đúng theo ngữ nghĩa so sánh số (loại khỏi mọi `min_duration_ms >= 0`), nhưng chưa từng verify tường minh [shared/filters.py] — deferred, giả định bất biến `end_ms >= start_ms` là trách nhiệm của stage `detect` (Story 1.3, Epic 1), ngoài phạm vi story này.

## Dev Notes

- **Đây là quyết định scope đã xác nhận với Lan (xem mục Scope Decision ở trên)** — KHÔNG tự ý mở rộng sang `shot_size`/`has_logo` dù epics.md/PRD có nhắc tới. Nếu trong lúc dev thấy "tiện thể" thêm field rỗng cho 2 filter đó, ĐỪNG làm — filter khai báo mà luôn `None`/luôn rỗng ở tầng data còn tệ hơn không khai báo (client tưởng filter hoạt động).
- **`apply_scene_filters` là điểm khác biệt quan trọng với `fetch_ann_candidates`/`fetch_fts_candidates`**: hai hàm đó là Postgres-only (`cosine_distance`, `to_tsvector`/`phraseto_tsquery`) và đã có sẵn `# pragma: no cover` — nhưng `apply_scene_filters` KHÔNG dùng hàm riêng dialect nào (chỉ phép trừ nguyên + `EXISTS` chuẩn SQL), nên đây là chỗ hiếm hoi trong `search/` có thể unit-test **logic SQL thật** (không phải fake `list[dict]`) qua sqlite fixture `async_session` có sẵn ở `tests/conftest.py`. Tận dụng điều này ở Task 4 — không cần fake/mock, insert data thật rồi execute.
- **Thứ tự áp filter bên trong `fetch_fts_candidates` phải giữ nguyên kỷ luật subquery từ code review Story 2.2**: filter (cùng `search_status`) áp ở statement TRƯỚC KHI `.subquery()` + trước `ts_headline` ở tầng ngoài — nếu vô tình áp filter sau khi đã `.subquery()`/ở tầng ngoài, Postgres vẫn ra kết quả ĐÚNG (WHERE ngoài lọc sau) nhưng SAI về hiệu năng (mất lý do tồn tại của subquery: cắt trước khi `ts_headline` tính) và sai về AC #3 ("tầng SQL filter đầu tiên", trước `ORDER BY`/`LIMIT`, không phải lọc sau khi đã cắt pool).
- **`has_person=False`** không nằm trong FR-7 gốc (chỉ nói "có mặt người" — hàm ý positive filter) nhưng thêm hỗ trợ symmetric miễn phí vì cùng cấu trúc `EXISTS`/`NOT EXISTS` — không phải scope creep đáng kể, nhưng nếu muốn tối giản triệt để có thể bỏ nhánh `False` (KHÔNG BẮT BUỘC, tuỳ đánh giá lúc dev; nếu bỏ thì `has_person: bool | None` chỉ còn ý nghĩa khi `True`).
- **Không đụng `pipeline/`** — giống Story 2.1/2.2, story này chỉ đọc dữ liệu Epic 1 đã ghi sẵn (`Scene.start_ms/end_ms` từ Story 1.3, `FaceAppearance` từ Story 1.5), giữ ranh giới CQRS-lite (AD-2). Có 1 ngoại lệ nhỏ: `deferred-work.md` là tài liệu, không phải code ingest.
- **`SceneFilters` dùng Pydantic `BaseModel`** (không phải `pydantic_settings.BaseSettings` như `shared/config.py`) — đây là request-shape validate-once-per-call, không phải config nạp từ env; import `from pydantic import BaseModel, Field, model_validator`.
- **Field `person_id` không validate tồn tại trong bảng `person`** ở tầng schema (`SceneFilters` không chạm DB) — nếu `person_id` không tồn tại, `EXISTS` đơn giản trả `False` cho mọi Scene → kết quả rỗng, không crash. Đây là hành vi chấp nhận được cho MVP (không phải bug), tương tự cách `fetch_fts_candidates` xử lý tsquery rỗng ở Story 2.2.

### Project Structure Notes

- **File mới**: `shared/filters.py` (`SceneFilters` + `apply_scene_filters`), `tests/test_filters.py`.
- **File sửa**: `search/candidates.py` (`fetch_ann_candidates` thêm `filters`), `search/fts_candidates.py` (`fetch_fts_candidates` thêm `filters`), `search/service.py` (`search()` thêm `filters`), `api/routes_search.py` (`SearchRequest.filters` + truyền xuống), `tests/test_search_service.py`, `tests/test_search_route.py`, `_bmad-output/implementation-artifacts/deferred-work.md` (entry mới cho `shot_size`/`has_logo`).
- **Không sửa `shared/models.py`** — cả `min_duration_ms`/`max_duration_ms` (dẫn xuất từ `start_ms`/`end_ms` có sẵn) và `has_person`/`person_id` (dẫn xuất từ bảng `face_appearance` có sẵn) đều KHÔNG cần cột mới; đây là lý do MVP hẹp khả thi ngay trong story này mà không đụng ingest.
- Không có migration mới (không thêm cột/index DB) — nếu sau này cần tối ưu hiệu năng `EXISTS` trên bảng `face_appearance` lớn, đó là việc riêng (đã có index `scene_id` sẵn từ Story 1.5, xem `shared/models.py` `FaceAppearance.scene_id` cột `index=True`).

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story-2.3]
- [Source: _bmad-output/planning-artifacts/architecture/architecture-scene-intelligence-2026-07-03/ARCHITECTURE-SPINE.md#AD-21] (dòng 159-162: "Tập thuộc tính lọc là một schema dùng chung" — ingest ghi, search/UI đọc cùng, thêm bộ lọc = sửa schema chung) + #AD-8 (dòng 94-97: phễu 4 tầng, filter tầng đầu) + #AD-11 (dòng 109-112: face chỉ gán tên khi confidence đủ + đã đăng ký, ngoài ra "không xác định") + #AD-17 (dòng 139-142: cổng `indexed`)
- [Source: _bmad-output/planning-artifacts/prds/prd-scene-intelligence-2026-07-03/prd.md#FR-7] (dòng 134-139: "Có ít nhất các bộ lọc: cỡ cảnh, có mặt người, độ dài Scene, không dính logo `[ASSUMPTION: tập bộ lọc tối thiểu; có thể mở rộng]`")
- [Source: _bmad-output/implementation-artifacts/2-2-full-text-hop-nhat-hybrid-rrf.md] (pattern subquery-trước-`ts_headline` ở `fetch_fts_candidates` phải giữ nguyên khi thêm filter; `search/service.py` orchestration tuần tự trên cùng session)
- [Source: shared/models.py#L35-54,69-82] (`Scene.start_ms/end_ms`, `FaceAppearance.scene_id/person_id` — cột đã có sẵn từ Story 1.3/1.5, không cần migration)
- [Source: search/candidates.py, search/fts_candidates.py, search/service.py, api/routes_search.py, shared/config.py, tests/conftest.py, tests/test_search_service.py, tests/test_search_route.py]

## Dev Agent Record

### Agent Model Used

claude-sonnet-5 (BMad dev-story)

### Debug Log References

- `uv run pytest tests/test_filters.py -q` (Task 1, RED trước khi tạo `shared/filters.py`) → `ModuleNotFoundError: No module named 'shared.filters'` — xác nhận đúng thất bại trước khi implement.
- `uv run pytest tests/test_filters.py -q` (sau khi tạo `shared/filters.py`) → **5 passed** (schema validation).
- `uv run pytest tests/test_filters.py -q` (sau khi thêm `apply_scene_filters` + test tích hợp sqlite) → **13 passed**.
- Verify AC #3 (filter TRƯỚC `ORDER BY`/`LIMIT`) bằng compiled-SQL (dialect `postgresql`, không cần Postgres sống), cùng kỹ thuật code review Story 2.2: (1) nhánh ANN — predicate `scene.end_ms - scene.start_ms <= %(param_1)s` nằm trong `WHERE` trước `LIMIT`; (2) nhánh FTS — predicate nằm TRONG subquery `anon_1` trước `LIMIT`, `ts_headline` vẫn ở tầng ngoài (không bị filter ảnh hưởng thứ tự tính) — cả hai đúng thiết kế.
- `uv run pytest -q` (toàn bộ suite sau khi wire Task 3/5/6/7) → **134 passed** (128 trước + 6 mới: 2 `test_search_service.py` (forward/default filters) + 4 `test_search_route.py` (nested filters parse/reject + endpoint forward), không tính 13 test `test_filters.py` đã cộng dồn trước đó).
- `uv run ruff check search/ api/ shared/ tests/` → sạch.
- `fetch_ann_candidates`/`fetch_fts_candidates` với `filters` thật (Postgres): **chưa chạy môi trường Postgres thật** trong phiên dev này (không có hạ tầng thật truy cập được) — cùng tiền lệ Story 2.1/2.2; verify bằng compiled-SQL (trên) thay cho chạy thật.
- **Code review (5 patch áp dụng)**: `uv run pytest tests/test_filters.py -q` (RED trước khi sửa `shared/filters.py`) → 3 test mới fail (`DID NOT RAISE ValidationError`) — xác nhận đúng thất bại trước khi thêm `extra="forbid"` + validator mới + `min_length=1`. Sau khi sửa: **18 passed**. `tests/test_candidates_filter_order.py` (mới) lần đầu chạy fail do naive substring match trên "end_ms" khớp nhầm cột SELECT thay vì predicate — sửa thành tìm đúng biểu thức `"end_ms - scene.start_ms"` → **2 passed**. `uv run pytest -q` (toàn bộ) → **141 passed** (134 + 7 mới: 5 `test_filters.py` + 2 `test_candidates_filter_order.py`). `uv run ruff check` → sạch.

### Completion Notes List

- **Task 1**: `shared/filters.py::SceneFilters` — schema dùng chung (AD-21), 2 field triển khai (`min_duration_ms`/`max_duration_ms`, `has_person`/`person_id`), `model_validator` chặn `max < min`. Entry deferred mới cho `shot_size`/`has_logo` ghi vào `deferred-work.md`.
- **Task 2**: `shared/filters.py::apply_scene_filters` — hàm thuần SQLAlchemy Core (không dùng hàm riêng dialect), độ dài qua phép trừ nguyên, có-mặt-người/person cụ thể qua `EXISTS`/`~EXISTS` trên `FaceAppearance`.
- **Task 3**: Wire vào `fetch_ann_candidates` (WHERE trước ORDER BY/LIMIT) và `fetch_fts_candidates` (filter trong subquery `limited`, giữ nguyên kỷ luật subquery-trước-`ts_headline` từ Story 2.2). Verify thứ tự bằng compiled-SQL.
- **Task 4**: `tests/test_filters.py` (mới, 13 test) — validation schema + `apply_scene_filters` tích hợp qua sqlite `async_session` (duration range, has_person true/false, person_id cụ thể loại "không xác định", kết hợp AND).
- **Task 5**: `search/service.py::search()` — tham số `filters` xuyên tới cả hai fetcher, cùng một object.
- **Task 6**: `api/routes_search.py::SearchRequest.filters` — import trực tiếp `SceneFilters`, không khai báo rời; `search_endpoint` truyền `filters=req.filters`.
- **Task 7**: `tests/test_search_service.py` (+2 test forward/default), `tests/test_search_route.py` (+4 test nested-filters parse/reject/endpoint-forward).
- AC #1-#6 đều thoả: #1/#2/#6 test thuần qua sqlite (Task 4); #3 verify compiled-SQL (Postgres dialect); #4 kết hợp NL+filter qua cùng request body (`SearchRequest`) + AND-semantics test (Task 4); #5 wiring test xác nhận reuse đúng `SceneFilters` (Task 7, không định nghĩa field rời).
- Không đụng `pipeline/`, không migration mới, không sửa `shared/models.py` — đúng phạm vi MVP hẹp đã xác nhận.
- **Code review (5 patch áp dụng)**: (1) `extra="forbid"` trên `SceneFilters` — chặn field lạ (vd `shot_size`) bị âm thầm bỏ qua; (2) `tests/test_candidates_filter_order.py` mới — khoá invariant AC #3 (filter trước `LIMIT`) bằng test tự động thay vì chỉ verify thủ công; (3) validator mới chặn `has_person=False` + `person_id` cùng lúc (tự mâu thuẫn); (4) `person_id` thêm `min_length=1` chặn chuỗi rỗng; (5) test mới cho `person_id` không tồn tại. 2 finding defer (tài liệu OpenAPI + dữ liệu `end_ms < start_ms` hỏng) ghi vào `deferred-work.md`. 8 finding dismiss (nitpick không ảnh hưởng hành vi/đã có rationale trong Dev Notes).

### File List

- **Mới**: `shared/filters.py`, `tests/test_filters.py`, `tests/test_candidates_filter_order.py`
- **Sửa**: `search/candidates.py` (`fetch_ann_candidates` thêm `filters`), `search/fts_candidates.py` (`fetch_fts_candidates` thêm `filters`), `search/service.py` (`search()` thêm `filters`), `api/routes_search.py` (`SearchRequest.filters` + truyền xuống), `tests/test_search_service.py`, `tests/test_search_route.py`, `_bmad-output/implementation-artifacts/deferred-work.md` (entry mới `shot_size`/`has_logo` + 2 entry code review), `_bmad-output/implementation-artifacts/sprint-status.yaml` (status)

## Change Log

- 2026-07-06 — Story 2.3 tạo bởi create-story workflow (Amelia). Scope hẹp lại còn 2/4 filter FR-7 (độ dài + người) sau khi xác nhận với Lan qua AskUserQuestion — `shot_size`/`has_logo` deferred (chưa có tín hiệu ingest).
- 2026-07-06 — Story 2.3: `shared/filters.py` (`SceneFilters` + `apply_scene_filters`, AD-21) — schema dùng chung cho lọc độ dài + có-mặt-người, dùng lại ở `search/candidates.py`, `search/fts_candidates.py`, `api/routes_search.py`. 134/134 test pass (19 mới: 13 `test_filters.py` + 2 `test_search_service.py` + 4 `test_search_route.py`), ruff clean. Deferred `shot_size`/`has_logo` ghi vào `deferred-work.md`.
- 2026-07-06 — Code review: 5 patch áp dụng (`extra="forbid"` trên `SceneFilters`; test tự động khoá AC #3 filter-trước-LIMIT; chặn `has_person=False`+`person_id` mâu thuẫn; `person_id` `min_length=1`; test `person_id` không tồn tại) + 2 finding defer (tài liệu OpenAPI, dữ liệu Scene hỏng `end_ms<start_ms`) + 8 dismiss. 141/141 test pass, ruff clean.
