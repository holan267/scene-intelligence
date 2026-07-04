---
baseline_commit: aa0cef5256af18d28514a887fe347abf6eb6726c
---

# Story 2.2: Full-text + hợp nhất Hybrid (RRF)

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a **biên tập viên**,
I want **tìm chính xác cụm từ trong lời thoại/OCR và được hợp nhất với kết quả ngữ nghĩa**,
so that **cả tên riêng lẫn ý nghĩa đều tìm ra**.

## Acceptance Criteria

1. **Given** một Scene `indexed` có `scene_embedding.fts_text` chứa một cụm từ chính xác (vd tên riêng, "World Cup"), **When** gọi `POST /api/v1/search` với query chứa đúng cụm đó, **Then** hệ Postgres FTS (`to_tsvector`/`phraseto_tsquery`, config `simple`) trả đúng Scene có cụm đó — [Source: FR-8, #AD-8].
2. **Given** phễu 4 tầng cố định (AD-8), **When** search chạy, **Then** thứ tự luôn là: SQL filter (`search_status=indexed`) → **song song khái niệm** (ANN ∥ FTS) → **RRF merge ở mức Scene** (một candidate/Scene, #AD-7) → rerank có điều kiện (kế thừa Story 2.1) — không có đường nào vòng qua RRF — [Source: FR-6/7/8, #AD-8].
3. **Given** một Scene chỉ khớp qua FTS (không lọt top-`pool_size` ANN) HOẶC chỉ khớp qua ANN (không khớp cụm từ khoá), **Then** Scene đó vẫn xuất hiện trong candidate đã hợp nhất — RRF cộng điểm theo rank ở MỖI nhánh mà Scene có mặt, không đòi hỏi khớp cả hai nhánh — [Source: #AD-8].
4. **Given** một Scene được FTS khớp, **Then** trường `highlights` trong envelope chứa đoạn trích đã đánh dấu cụm khớp (`ts_headline`); Scene chỉ khớp qua ANN (không qua FTS) vẫn trả `highlights: []` — [Source: #AD-13].
5. **Given** cổng hiển thị/freshness đã có từ Story 2.1 (AD-16/17), **Then** RRF hợp nhất KHÔNG được làm lọt Scene chưa `search_status=indexed` hoặc lệch `doc_version` — bộ lọc freshness áp dụng SAU khi hợp nhất, TRƯỚC rerank (đúng thứ tự phễu) — [Source: #AD-16, #AD-17].

## Tasks / Subtasks

- [x] **Task 1 — Migration `0009`: GIN functional index cho FTS** (AC: #1): `migrations/versions/0009_scene_embedding_fts_index.py`, nối tiếp `0008`:
  - [x] `CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_scene_embedding_fts ON scene_embedding USING gin (to_tsvector('simple', fts_text))` — **functional/expression index**, không phải cột generated mới. Cùng pattern `autocommit_block()` như migration `0008` (`CREATE INDEX CONCURRENTLY` không chạy được trong transaction block).
  - [x] `downgrade()`: `DROP INDEX CONCURRENTLY IF EXISTS ix_scene_embedding_fts` (cùng `autocommit_block()`).
  - [x] **KHÔNG thêm cột mới ở `shared/models.py`** — đây là index trên biểu thức (`to_tsvector('simple', fts_text)`), không phải cột vật lý; không đụng ORM/`Base.metadata` (giữ nguyên lý do Story 2.1 tránh vỡ `Base.metadata.create_all` trên sqlite fixture). Query ở Task 3 phải dùng ĐÚNG biểu thức `to_tsvector('simple', fts_text)` (cùng tham số config `'simple'`) để Postgres planner khớp được với index này.
  - [x] `[ASSUMPTION]` config `'simple'` (tokenize + lowercase, KHÔNG stemming) — Postgres không có text-search dictionary tiếng Việt built-in; `'simple'` phù hợp với AC "tìm **chính xác** cụm từ" và tránh vi phạm AD-9 (không lỡ dùng dictionary `'english'` stem sai ngôn ngữ trên text tiếng Việt).

- [x] **Task 2 — Setting mới** (AC: #2): `shared/config.py`, cùng nhóm comment với `search_pool_size`/`rerank_skip_gap` (Story 2.1):
  - [x] `rrf_k: int = Field(default=60, gt=0)` — hằng số Reciprocal Rank Fusion (Cormack et al. 2009, giá trị 60 là chuẩn phổ biến trong tài liệu IR, không phải số tuỳ tiện — nhưng vẫn tham số hoá để tinh chỉnh sau ở Epic 4).
  - [x] **KHÔNG thêm `fts_pool_size` riêng** — dùng chung `search_pool_size` hiện có (Story 2.1) cho cả nhánh ANN và FTS, giữ ít bề mặt cấu hình.

- [x] **Task 3 — `search/fts_candidates.py`** (module mới, AC: #1, #4, #5): `async def fetch_fts_candidates(session: AsyncSession, query: str, *, pool_size: int) -> list[dict]`:
  - [x] Cùng cấu trúc `search/candidates.py::fetch_ann_candidates`: `SELECT Scene.scene_id, Scene.video_id, Scene.start_ms, Scene.end_ms, Scene.scene_document, SceneEmbedding.doc_version, ts_rank_cd(to_tsvector('simple', fts_text), phraseto_tsquery('simple', :query)).label("fts_rank_score"), ts_headline('simple', fts_text, phraseto_tsquery('simple', :query), 'StartSel=**,StopSel=**').label("fts_snippet")` JOIN `scene_embedding`, `WHERE Scene.search_status == "indexed" AND to_tsvector('simple', fts_text) @@ phraseto_tsquery('simple', :query)`, `ORDER BY fts_rank_score DESC`, `LIMIT pool_size`.
  - [x] Dùng `phraseto_tsquery` (KHÔNG `plainto_tsquery`/`websearch_to_tsquery`) — giữ đúng thứ tự liền kề của cụm từ (AC "cụm từ", vd "World Cup" phải khớp theo đúng thứ tự, không phải AND rời rạc hai từ).
  - [x] Trả `list[dict]` gồm `fts_snippet` (chuỗi `ts_headline`, markers `**...**` — không phải HTML `<b>`, vì UI thật chưa tồn tại tới Epic 3, `[ASSUMPTION]` điều chỉnh khi có yêu cầu UI cụ thể).
  - [x] **CHỈ chạy đúng trên Postgres thật — KHÔNG unit-test được qua sqlite** (`to_tsvector`/`phraseto_tsquery`/`ts_headline` là hàm riêng Postgres, cùng lý do `.cosine_distance()` ở Story 2.1). Đánh dấu `# pragma: no cover - phụ thuộc Postgres thật`, xác minh thủ công khi có Postgres.
  - [x] Query rỗng sau tokenize (chỉ toàn stopword/ký tự đặc biệt) → `phraseto_tsquery` trả tsquery rỗng; `@@` với tsquery rỗng luôn `False` → không candidate nào, KHÔNG crash. Đây là hành vi Postgres chuẩn — KHÔNG tự thêm guard/try-except thừa cho trường hợp này.

- [x] **Task 4 — `search/fuse.py`** (module mới, hàm thuần — AC: #2, #3): `def reciprocal_rank_fusion(ann_candidates: list[dict], fts_candidates: list[dict], *, k: int) -> list[dict]`:
  - [x] Hai list đầu vào ĐÃ sắp giảm dần theo mức liên quan của từng nhánh (đến từ `fetch_ann_candidates`/`fetch_fts_candidates` vốn có `ORDER BY`) — rank 1-based theo vị trí trong list.
  - [x] Merge theo `scene_id`: `rrf_score = Σ 1/(k + rank)` cộng dồn qua MỌI list mà `scene_id` xuất hiện (Scene chỉ ở 1 nhánh chỉ nhận đóng góp từ nhánh đó).
  - [x] Giữ nguyên field gốc (`video_id`, `start_ms`, `end_ms`, `scene_document`, `doc_version` — giống hệt giữa 2 nhánh vì cùng đọc `Scene`/`SceneEmbedding`, không mâu thuẫn). Set `fts_snippet` từ bản ghi FTS nếu `scene_id` có mặt ở nhánh FTS, ngược lại `None`.
  - [x] Trả về `list[dict]` đã sort giảm dần theo `rrf_score`.
  - [x] Hàm thuần, KHÔNG chạm DB — unit-test đầy đủ bằng fake `list[dict]` ở Task 8.

- [x] **Task 5 — `search/rank.py`: đổi cơ sở gap-check/score từ `ann_distance` sang `rrf_score`** (AC: #2, #4):
  - [x] Đổi `normalize_ann_score(distance)` → `normalize_rrf_score(rrf_score: float, *, k: int) -> float`: `max(0.0, min(1.0, rrf_score / (2.0 / (k + 1))))` — chuẩn hoá theo max lý thuyết (`2/(k+1)`, khi Scene đứng #1 ở CẢ hai nhánh). Giữ nguyên guard NaN/inf → `0.0` (Review fix Story 2.1).
  - [x] `maybe_rerank(candidates, reranker, query, *, gap_threshold, k)`: thêm tham số `k`, thay MỌI chỗ dùng `c["ann_distance"]` bằng `normalize_rrf_score(c["rrf_score"], k=k)` — giữ nguyên logic gap-skip/rerank/resort hiện có, chỉ đổi field/hàm chuẩn hoá đầu vào.
  - [x] `build_envelope`: `highlights = [c["fts_snippet"]] if c.get("fts_snippet") else []` (thay cho `[]` cố định). `highlights` là mảng 0 hoặc 1 phần tử — KHÔNG tách `ts_headline` thành nhiều phần tử mảng riêng, giữ đơn giản, vẫn khớp hợp đồng mảng AD-13.
  - [x] `filter_fresh_candidates`: KHÔNG đổi — vẫn hoạt động trên `scene_document`/`doc_version`, độc lập nguồn ANN/FTS/RRF.

- [x] **Task 6 — `search/service.py`: orchestration** (AC: #1-#5): cập nhật `search(session, embedder, reranker, query, *, limit, pool_size, gap_threshold, k)`:
  - [x] `query_vec = await embedder.embed(query)` → `ann = await fetch_ann_candidates(session, query_vec, pool_size=pool_size)` → `fts = await fetch_fts_candidates(session, query, pool_size=pool_size)` → `fused = reciprocal_rank_fusion(ann, fts, k=k)` → `fresh = filter_fresh_candidates(fused)` → `ranked = await maybe_rerank(fresh, reranker, query, gap_threshold=gap_threshold, k=k)` → `return build_envelope(ranked, limit=limit)`.
  - [x] **Chạy TUẦN TỰ trên cùng `AsyncSession`** — KHÔNG `asyncio.gather` hai query trên cùng session (SQLAlchemy `AsyncSession` không an toàn khi 2 coroutine dùng chung 1 session/connection đồng thời, sẽ lỗi/undefined behavior). "Song song" ở AD-8 mô tả tầng khái niệm (hai cơ chế truy hồi độc lập được hợp nhất bởi RRF), KHÔNG bắt buộc concurrency runtime thật ở kiến trúc một-session-một-request hiện có. Đây là quyết định có chủ đích — KHÔNG tự ý "tối ưu" bằng `asyncio.gather`/2 session riêng, ngoài phạm vi story này.

- [x] **Task 7 — `api/routes_search.py`: truyền `settings.rrf_k`** (AC: #1-#5): `search_endpoint` gọi `search(..., k=settings.rrf_k)` thêm vào lời gọi hiện có — không đổi gì khác trong route (validation `SearchRequest`, mapping `RuntimeError` → 502 giữ nguyên).

- [x] **Task 8 — Test** (AC: #1-#5, trừ Task 1/3 là hạ tầng/Postgres-only không unit-test qua sqlite được):
  - [x] `tests/test_search_fuse.py` (mới): `reciprocal_rank_fusion` — Scene chỉ ở ANN giữ nguyên field + `fts_snippet is None`; Scene chỉ ở FTS giữ nguyên field + `fts_snippet` đúng; Scene ở CẢ hai cộng đúng công thức `1/(k+rank_ann) + 1/(k+rank_fts)`; output sort giảm dần theo `rrf_score`; test với ≥2 giá trị `k` khác nhau để khoá đúng công thức (không hardcode `k=60` trong hàm).
  - [x] `tests/test_search_rank.py` (cập nhật): đổi toàn bộ candidate fixture từ `ann_distance` sang `rrf_score`; test `normalize_rrf_score` clamp 0-1 đúng công thức (`max=2/(k+1)`) + NaN/inf → 0 (giữ 2 test hiện có, đổi tên hàm); 3 test `maybe_rerank` hiện có cập nhật sang `rrf_score` + tham số `k`; `build_envelope` thêm case `highlights == [snippet]` khi `fts_snippet` có giá trị, giữ case `highlights == []` khi không có (hoặc `None`).
  - [x] `tests/test_search_service.py` (cập nhật): `monkeypatch` cả `fetch_ann_candidates` VÀ `fetch_fts_candidates`; thêm test case Scene chỉ có ở FTS list (ANN trả rỗng) vẫn lọt kết quả cuối; test case Scene ở cả 2 list được cộng điểm và lên thứ hạng đúng; cập nhật lời gọi `service_module.search(...)` thêm `k=...`.
  - [x] `tests/test_search_route.py`: không cần đổi logic — verify vẫn pass nguyên vẹn (route không lộ `k` qua request body, chỉ đọc từ `settings`).
  - [x] `tests/test_config.py`: thêm test default (`60`) + `Field(gt=0)` validation cho `rrf_k` (cùng pattern `test_zero_or_negative_rejected` có sẵn từ Story 1.7/2.1).

### Review Findings

- [x] [Review][Patch] `rerank_skip_gap=0.15` (kế thừa nguyên từ Story 2.1, tune cho `normalize_ann_score`/cosine-distance) không còn ý nghĩa dưới thang điểm `normalize_rrf_score` mới — khoảng cách điểm giữa 2 rank liền kề của MỘT nhánh quá nhỏ (k=60: rank1≈0.5, rank2≈0.492, gap≈0.008) nên ngưỡng cũ cần lệch ~28 rank mới đạt, khiến rerank chạy gần như MỌI truy vấn, vô hiệu hoá âm thầm tối ưu "bỏ rerank khi #1 áp đảo" (AD-8) [shared/config.py] — **Fixed**: hạ `rerank_skip_gap` mặc định xuống `0.05` (tương đương #1 dẫn trước #2 ~8 rank cùng nhánh, hoặc #1 khớp cả 2 nhánh trong khi #2 chỉ khớp 1) + comment giải thích công thức, vẫn `[ASSUMPTION]` chờ tinh chỉnh ở Epic 4.
- [x] [Review][Patch] `ts_headline` (hàm re-tokenize tốn kém) được tính ở CÙNG tầng SELECT với `WHERE`/`ORDER BY`/`LIMIT` — Postgres phải materialize `ts_headline` cho MỌI dòng khớp `WHERE` trước khi `Sort`/`Limit` kịp cắt còn `pool_size`, biến chi phí O(pool_size) thành O(số dòng khớp) cho cụm từ phổ biến [search/fts_candidates.py] — **Fixed**: tách thành subquery con (`WHERE`+`ORDER BY`+`LIMIT` trước), chỉ tính `ts_headline` ở tầng ngoài trên đúng `pool_size` dòng còn lại — đúng khuyến nghị Postgres docs (Text Search § Highlighting Results). Verify bằng compile SQLAlchemy statement (dialect postgresql): subquery `anon_1` áp `LIMIT` trước khi `ts_headline` chạm `anon_1.fts_text` ở tầng ngoài.
- [x] [Review][Defer] Khi một Scene khớp CẢ hai nhánh, `reciprocal_rank_fusion` chỉ cập nhật `rrf_score`/`fts_snippet` từ nhánh FTS, không refresh `scene_document`/`doc_version` — nếu pipeline re-embed đúng lúc giữa 2 query tuần tự (ANN rồi FTS, cùng session, READ COMMITTED), candidate hợp nhất có thể mang `scene_document` cũ (từ nhánh ANN) + `fts_snippet` mới (từ nhánh FTS) [search/fuse.py, search/service.py] — deferred, tác động thấp (`scene_document` không trả ra client qua envelope; chỉ ảnh hưởng text đưa vào rerank + độ mới của snippet), race hẹp cỡ mili-giây.
- [x] [Review][Defer] `embedder.embed(query)` (httpx, không chạm session) chờ xong hoàn toàn trước khi `fetch_fts_candidates` mới bắt đầu, dù hai việc độc lập tài nguyên — có thể `asyncio.gather` để giảm latency, nhưng cần xử lý cẩn thận cancel/exception (nếu `embed()` raise trong khi `fetch_fts_candidates` còn chạy trên session) [search/service.py] — deferred, tối ưu hiệu năng cần thiết kế thêm.
- [x] [Review][Defer] `fetch_fts_candidates` trùng lặp pattern SELECT-columns/JOIN/filter `search_status=="indexed"` (AD-17)/row-mapping với `fetch_ann_candidates`, không có helper dùng chung — rủi ro lệch quy tắc AD-17 giữa 2 nhánh nếu chính sách đổi sau này (không phải rủi ro crash — đã verify downstream không đọc field riêng từng nhánh) [search/fts_candidates.py, search/candidates.py] — deferred, cleanup/maintainability.
- [x] [Review][Defer] Comment cũ ở `search/query_embed.py` còn nhắc tên hàm `normalize_ann_score` (đã đổi thành `normalize_rrf_score`); field chết (`ann_distance`/`fts_rank_score`) trôi qua `reciprocal_rank_fusion` không ai đọc sau merge [search/query_embed.py, search/fuse.py] — deferred, cleanup cosmetic, không ảnh hưởng runtime.

## Dev Notes

- **`fts_text` hiện = `scene_document`, KHÔNG PHẢI transcript/OCR nối trực tiếp** — Story 1.6 (`pipeline/embed_index.py`) ghi `fts_text = scene.scene_document` và để lại comment tường minh ở `shared/models.py:103-105`: *"KHÔNG dùng TSVECTOR... Story 2.2 sẽ tsvector-hoá cột này."* Đây LÀ quyết định kiến trúc có chủ đích của story này (tsvector-hoá `fts_text` qua functional index, Task 1), KHÔNG PHẢI lỗi cần "sửa" bằng cách tự ý đổi sang query trực tiếp `Scene.transcript`/`Scene.ocr_text`. Dù PRD FR-8/epics AC diễn đạt "transcript/OCR", `scene_document` (Qwen3-VL, Story 1.6) đã bao gồm "Tóm tắt lời nói 1-2 câu" + "Chữ trên hình - chọn lọc" (xem `addendum.md` §3) nên tên riêng/cụm đặc trưng thường vẫn còn trong đó — kỷ luật "một-văn-bản-gộp" (AD-4/AD-7) ưu tiên hơn khớp-đúng-100%-verbatim. Rủi ro đã biết: nếu Qwen3-VL tóm tắt bỏ mất một cụm hiếm có trong transcript gốc nhưng không vào `scene_document`, FTS sẽ miss cụm đó — đây là hạn chế thiết kế kế thừa từ Story 1.6, KHÔNG phải bug của story này.
- **Postgres FTS không có dictionary tiếng Việt built-in** — dùng config `'simple'` (tokenize + lowercase, không stemming) cho MỌI lời gọi `to_tsvector`/`phraseto_tsquery`/`ts_headline`/`ts_rank_cd` — phải nhất quán 100% giữa migration (Task 1) và query (Task 3), nếu lệch config thì Postgres KHÔNG dùng được functional index (full scan). `'simple'` phù hợp với AC "chính xác cụm từ" hơn `'english'` (stemmer sai ngôn ngữ, vi phạm AD-9).
- **`normalize_rrf_score` thay thế HOÀN TOÀN `normalize_ann_score`** — sau story này, MỌI truy vấn search đều đi qua cả hai nhánh ANN+FTS rồi RRF (AD-8: "mọi truy vấn đi qua đúng thứ tự... không có đường search nào vòng qua phễu này"), không còn đường ANN-only thuần tuý cần chuẩn hoá riêng theo cosine distance. Đổi tên/logic hàm là refactor CÓ CHỦ ĐÍCH bắt buộc bởi AD-8, không phải dọn dẹp tuỳ tiện — cập nhật toàn bộ test đi theo (Task 8).
- **Sequential ANN→FTS trên cùng session** (không `asyncio.gather`) — giải thích chi tiết ở Task 6. Nếu dev agent thấy cơ hội "tối ưu song song thật", đó là tối ưu hiệu năng ngoài phạm vi story này (ghi vào `deferred-work.md` nếu muốn theo dõi, đừng tự ý implement — cần thiết kế connection/session pooling riêng).
- **Functional GIN index, không phải cột generated** — không đụng `shared/models.py`/`Base.metadata` (cùng lý do HNSW index Story 2.1 tránh vỡ `create_all` trên sqlite fixture `tests/conftest.py`). Query phải dùng đúng biểu thức trong index để được Postgres planner sử dụng.
- **`fetch_fts_candidates`/migration `0009` không unit-test được qua sqlite** — cùng đúng tiền lệ `fetch_ann_candidates` (Story 2.1): `# pragma: no cover - phụ thuộc Postgres thật`, xác minh thủ công khi có Postgres. Đừng cố viết test cho hàm này qua sqlite fixture — sẽ luôn crash (hàm Postgres-only), không phải bug của story này.
- **`highlights` markers `**...**` (không phải HTML)** — `ts_headline` mặc định dùng `<b>`/`</b>`; story này chọn markers dạng markdown-style tường minh qua tham số `StartSel=**,StopSel=**` vì chưa có UI thật (Epic 3 chưa tồn tại) để xác nhận format mong muốn — `[ASSUMPTION]`, điều chỉnh khi UI thực có yêu cầu cụ thể.
- **`rrf_k=60`** — hằng số kinh điển trong tài liệu IR (Cormack, Clarke, Buettcher 2009, "Reciprocal Rank Fusion outperforms Condorcet and Individual Rank Learning Methods"), không phải số tuỳ tiện như `search_pool_size`/`rerank_skip_gap`, nhưng vẫn tham số hoá (`Field(gt=0)`) để tinh chỉnh sau khi có Eval set (Epic 4) — cùng pattern các tham số `[ASSUMPTION]` khác đã có.
- **Không đụng `pipeline/`** — story này chỉ đọc dữ liệu (`Scene`/`SceneEmbedding`) đã được Epic 1 ghi sẵn, giữ đúng ranh giới CQRS-lite (AD-2), giống Story 2.1.
- **Deferred từ code review Story 2.1 vẫn còn nguyên** (`_bmad-output/implementation-artifacts/deferred-work.md`) — đặc biệt "Pool ANN cạn không có tín hiệu/widen-retry": sau story này áp dụng tương tự cho pool FTS (`search_pool_size` dùng chung); KHÔNG mở rộng phạm vi story này để fix — vẫn defer.

### Project Structure Notes

- **File mới**: `search/fts_candidates.py`, `search/fuse.py`, `migrations/versions/0009_scene_embedding_fts_index.py`, `tests/test_search_fuse.py`.
- **File sửa**: `search/rank.py` (normalize + maybe_rerank + build_envelope), `search/service.py` (orchestration + tham số `k`), `api/routes_search.py` (truyền `k`), `shared/config.py` (`rrf_k`), `tests/test_search_rank.py`, `tests/test_search_service.py`, `tests/test_config.py`.
- **Không sửa `shared/models.py`** — `SceneEmbedding.fts_text` đã tồn tại từ Story 1.6; FTS dùng functional index (Task 1), không cần cột tsvector generated riêng.
- Migration mới = `0009`, nối tiếp `0008` (Story 2.1).

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story-2.2]
- [Source: _bmad-output/planning-artifacts/architecture/architecture-scene-intelligence-2026-07-03/ARCHITECTURE-SPINE.md#AD-2,#AD-4,#AD-7,#AD-8,#AD-9,#AD-13,#AD-16,#AD-17] (dòng ~64-67 AD-2, ~74-77 AD-4, ~89-92 AD-7 "RRF gộp ở mức Scene", ~94-97 AD-8 "phễu 4 tầng cố định", ~99-102 AD-9, ~119-122 AD-13, ~134-142 AD-16/17, dòng 255-267 source tree, dòng 288-300 Deferred: BM25 chuyên/OpenSearch KHÔNG thuộc phạm vi MVP — dùng Postgres FTS)
- [Source: _bmad-output/planning-artifacts/prds/prd-scene-intelligence-2026-07-03/prd.md#FR-8] (dòng 141-145: "Tìm từ khoá chính xác" — tên riêng/cụm từ trong transcript/OCR)
- [Source: _bmad-output/planning-artifacts/prds/prd-scene-intelligence-2026-07-03/addendum.md#5] (dòng 63-73: phễu 4 tầng "① SQL filter → ② ANN(HNSW) top200 ∥ BM25 top200 → ③ merge RRF → ④ rerank")
- [Source: _bmad-output/implementation-artifacts/2-1-tim-ngu-nghia-rerank-envelope-jump-to-moment.md] (pattern `candidates.py` Postgres-only + `rank.py` hàm thuần; `normalize_ann_score`/`maybe_rerank`/`build_envelope` là nền tảng story này sửa trên đó; adapter HTTP async; migration `CONCURRENTLY`/`autocommit_block()`; mapping `RuntimeError`→502)
- [Source: shared/models.py#L100-115] (`SceneEmbedding.fts_text` — comment "Story 2.2 sẽ tsvector-hoá cột này")
- [Source: search/candidates.py, search/rank.py, search/service.py, search/query_embed.py, search/rerank.py, api/routes_search.py, shared/config.py, migrations/versions/0006_scene_document_embedding.py, migrations/versions/0008_scene_embedding_ann_index.py, tests/conftest.py, tests/test_search_rank.py, tests/test_search_service.py, tests/test_search_route.py, tests/test_config.py]

## Dev Agent Record

### Agent Model Used

claude-sonnet-5 (BMad dev-story)

### Debug Log References

- `uv run pytest` → **115 passed** (105 trước + 10 mới: 5 `test_search_fuse.py` + 2 `test_search_rank.py` (highlights) + 1 `test_config.py` (rrf_k) + 2 `test_search_service.py` (fts-only scene, both-lists ranking); 8 test `test_search_rank.py`/`test_search_service.py` hiện có cập nhật field (`ann_distance`→`rrf_score`) không đổi số lượng.
- `uv run ruff check search/ api/ shared/ tests/ migrations/` → sạch.
- Migration `0009` module load-test (parse/syntax) qua `importlib` — chưa chạy `alembic upgrade head` thật (không có hạ tầng Postgres thật trong phiên này); `uv run alembic history` xác nhận chain `0008 -> 0009 (head)` liền mạch.
- `search/fts_candidates.py`: **chưa chạy môi trường Postgres thật** trong phiên dev này (không có hạ tầng thật truy cập được) — review kỹ bằng mắt theo đúng convention `search/candidates.py` đã có (Story 2.1), đánh dấu `# pragma: no cover - phụ thuộc Postgres thật`.
- **Code review (2 patch áp dụng, xem Review Findings)**: `uv run pytest` → **115 passed** (không đổi số lượng, chỉ đổi giá trị assertion `rerank_skip_gap`). `uv run ruff check` → sạch. Fix #2 (subquery `ts_headline`) verify bằng compile SQLAlchemy statement thật (dialect postgresql, không cần Postgres sống) — xác nhận `LIMIT` áp dụng ở subquery con TRƯỚC khi `ts_headline` chạm `fts_text` ở tầng ngoài. 3 finding defer ghi vào `deferred-work.md`.

### Completion Notes List

- **Task 1**: Migration `0009` — GIN functional index `to_tsvector('simple', fts_text)` trên `scene_embedding`, raw SQL qua `op.execute` trong `autocommit_block()` (cùng pattern `CONCURRENTLY`/`IF NOT EXISTS` như migration `0008`) — không đụng ORM/`Base.metadata`.
- **Task 2**: `rrf_k: int = Field(default=60, gt=0)` thêm vào `shared/config.py`, cùng nhóm với `search_pool_size`/`rerank_skip_gap`.
- **Task 3**: `search/fts_candidates.py::fetch_fts_candidates` — `phraseto_tsquery`/`to_tsvector`/`ts_rank_cd`/`ts_headline` config `'simple'`, filter `search_status="indexed"`, trả `fts_rank_score` + `fts_snippet` (markers `**...**`). Postgres-only, `# pragma: no cover`.
- **Task 4**: `search/fuse.py::reciprocal_rank_fusion` — hàm thuần, merge candidate ANN+FTS theo `scene_id`, `rrf_score = Σ 1/(k+rank)` qua mỗi nhánh có mặt, giữ `fts_snippet` khi có.
- **Task 5**: `search/rank.py` — `normalize_ann_score` → `normalize_rrf_score(rrf_score, *, k)` (chuẩn hoá theo max lý thuyết `2/(k+1)`, giữ guard NaN/inf→0.0); `maybe_rerank` thêm tham số `k`, dùng `rrf_score` thay `ann_distance`; `build_envelope` trả `highlights=[fts_snippet]` khi có, `[]` khi không.
- **Task 6**: `search/service.py::search()` — thêm tham số `k`; orchestration `embed → fetch_ann_candidates + fetch_fts_candidates (tuần tự, cùng session) → reciprocal_rank_fusion → filter_fresh_candidates → maybe_rerank → build_envelope`.
- **Task 7**: `api/routes_search.py` — truyền `k=settings.rrf_k` vào lời gọi `search()`.
- **Task 8**: `tests/test_search_fuse.py` (mới, 5 test), `tests/test_search_rank.py` (cập nhật fixture + 2 test highlights mới), `tests/test_search_service.py` (cập nhật + 2 test mới: fts-only scene, both-lists ranking), `tests/test_config.py` (+1 test `rrf_k`). `tests/test_search_route.py` không đổi, vẫn pass nguyên vẹn.
- ⚠️ Config `'simple'` cho toàn bộ hàm FTS Postgres (`to_tsvector`/`phraseto_tsquery`/`ts_headline`/`ts_rank_cd`) — `[ASSUMPTION]` vì Postgres không có dictionary tiếng Việt built-in; phải nhất quán 100% với migration `0009` để dùng được functional index (nếu lệch config, Postgres full-scan thay vì dùng index — không lỗi chức năng nhưng mất hiệu năng).
- ⚠️ `highlights` markers `**...**` (không phải HTML `<b>`) — `[ASSUMPTION]`, điều chỉnh khi UI thật (Epic 3) có yêu cầu cụ thể.
- **Code review (2 patch áp dụng)**: (1) `rerank_skip_gap` mặc định `0.15`→`0.05` (`shared/config.py`) — ngưỡng cũ tune cho `normalize_ann_score`/cosine-distance không còn ý nghĩa dưới thang điểm `normalize_rrf_score`, khiến rerank chạy gần như mọi truy vấn thay vì bỏ qua khi #1 áp đảo (AD-8); (2) `search/fts_candidates.py::fetch_fts_candidates` tách thành subquery con (`WHERE`+`ORDER BY`+`LIMIT` trước) để `ts_headline` chỉ tính trên `pool_size` dòng đã cắt, không phải mọi dòng khớp `WHERE`. 3 finding defer ghi vào `deferred-work.md` (stale-merge race khi Scene khớp cả 2 nhánh + re-embed đúng lúc, thiếu `asyncio.gather(embed, fts)`, trùng lặp pattern `fetch_fts_candidates`/`fetch_ann_candidates`); 1 finding dismiss cosmetic (comment cũ + field chết, ghi trực tiếp vào deferred-work vì gần như miễn phí để sửa sau); 1 finding refuted (nghi ngờ GIN index không dùng được do config truyền dạng bind-param — verify thực nghiệm với Postgres thật + `EXPLAIN` xác nhận vẫn dùng đúng Bitmap Index Scan).
- ⚠️ Chưa xác minh thực nghiệm với Postgres thật: `to_tsvector`/`phraseto_tsquery`/`ts_headline`/`ts_rank_cd` hoạt động đúng cú pháp chuẩn theo tài liệu Postgres, nhưng chưa chạy được trên môi trường thật trong phiên này (không có hạ tầng — giống đúng tiền lệ NFR-1/Story 1.7, ANN/Story 2.1).
- AC #1-#5 đều thoả theo thiết kế + test thuần (`fuse`/`rank`/`service`); AC #1 (FTS khớp đúng cụm) và phần Postgres-only của AC #4/#5 (freshness filter áp dụng đúng SAU khi hợp nhất) được test qua `test_search_service.py` với fake fetcher — logic filter/hợp nhất đã verify, phần SQL FTS thật (`fetch_fts_candidates`) cần xác minh thủ công với Postgres.

### File List

- **Mới**: `migrations/versions/0009_scene_embedding_fts_index.py`, `search/fts_candidates.py`, `search/fuse.py`, `tests/test_search_fuse.py`
- **Sửa**: `shared/config.py` (`rrf_k`, code review: `rerank_skip_gap` mặc định), `search/rank.py` (`normalize_rrf_score`/`maybe_rerank`/`build_envelope`), `search/service.py` (orchestration + tham số `k`), `api/routes_search.py` (truyền `k`), `search/fts_candidates.py` (code review: subquery cho `ts_headline`), `tests/test_search_rank.py`, `tests/test_search_service.py`, `tests/test_config.py` (code review: assertion `rerank_skip_gap`), `_bmad-output/implementation-artifacts/deferred-work.md` (3 mục defer từ code review), `_bmad-output/implementation-artifacts/sprint-status.yaml` (status)

## Change Log

- 2026-07-04 — Story 2.2: `search/fts_candidates.py` (Postgres FTS `to_tsvector`/`phraseto_tsquery`/`ts_rank_cd`/`ts_headline`, config `'simple'`) + `search/fuse.py::reciprocal_rank_fusion` (hợp nhất ANN+FTS mức Scene, AD-7/AD-8) + migration `0009` (GIN functional index). Refactor `search/rank.py` (`normalize_ann_score`→`normalize_rrf_score`, `maybe_rerank`/`build_envelope` dùng `rrf_score`/`fts_snippet`) và `search/service.py` (orchestration ANN→FTS tuần tự → RRF → freshness → rerank → envelope) bắt buộc bởi phễu 4 tầng cố định AD-8. 115/115 test pass (10 mới), ruff clean.
- 2026-07-04 — Code review: 2 patch áp dụng (`rerank_skip_gap` mặc định 0.15→0.05 — ngưỡng cũ không còn ý nghĩa dưới thang điểm RRF, vô hiệu hoá âm thầm tối ưu bỏ-rerank AD-8; `fetch_fts_candidates` tách subquery để `ts_headline` chỉ tính trên `pool_size` dòng đã cắt thay vì mọi dòng khớp `WHERE`) + 3 finding defer (stale-merge race 2 nhánh, thiếu `asyncio.gather(embed, fts)`, trùng lặp pattern `fetch_fts_candidates`/`fetch_ann_candidates`). 115/115 test pass, ruff clean.
