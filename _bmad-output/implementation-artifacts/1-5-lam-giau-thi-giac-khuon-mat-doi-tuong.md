---
baseline_commit: 50640a18fc891af41369c3234a4b6662c352a3ee
---

# Story 1.5: Làm giàu thị giác — Khuôn mặt & Đối tượng

Status: done

## Story

As a **hệ thống ingest**,
I want **nhận diện khuôn mặt và đối tượng trên Keyframe**,
so that **Scene có tín hiệu người/vật để lọc và mô tả**.

## Acceptance Criteria

1. **Given** một Keyframe và một registry danh tính đã đăng ký, **When** stage face (InsightFace) chạy, **Then** khuôn mặt chỉ được gán tên khi confidence ≥ ngưỡng **và** đã đăng ký; ngoài ra ghi `person_id = None` ("không xác định", không bịa danh tính) — [Source: #AD-11].
2. **Given** stage object (YOLO) chạy trên cùng Keyframe, **Then** mỗi đối tượng phát hiện được lưu kèm confidence — [Source: FR-4].
3. **Given** một tên người mới hoặc đã tồn tại, **When** đăng ký/cập nhật danh tính (registry), **Then** person được tạo mới (nếu chưa có tên đó) hoặc cập nhật embedding tham chiếu (nếu đã có) — idempotent theo `name`.
4. **Given** chạy lại stage face/object trên cùng Scene, **Then** kết quả ghi vào cột/bảng riêng của stage này (`face_appearance`, `scene.objects`) — không đụng `transcript`/`ocr_text` hay field của stage khác — [Source: #AD-5].

## Tasks / Subtasks

- [x] **Task 1 — Schema** (AC: #1, #2, #3, #4): migration `0005` thêm:
  - [x] Bảng `person` (`person_id` PK, `name` unique, `reference_embedding` Text = JSON list[float], `created_at`).
  - [x] Bảng `face_appearance` (`appearance_id` PK, `scene_id` FK → `scene.scene_id`, `person_id` FK nullable → `person.person_id`, `confidence` Float, `created_at`) — một Scene có nhiều appearance (ERD `SCENE ||--o{ FACE_APPEARANCE`, `PERSON ||--o{ FACE_APPEARANCE`).
  - [x] Cột `scene.objects` (Text nullable = JSON list `[{label, confidence}]`) — cột riêng của stage object (AD-5), tách khỏi `transcript`/`ocr_text` (Story 1.4).
- [x] **Task 2 — Person registry** (AC: #3): `pipeline/registry.py` — `register_person(session, name, embedding) -> person_id`: upsert theo `name` (tạo mới nếu chưa có, cập nhật `reference_embedding` nếu đã có); id sinh ổn định qua `shared/ids.py` (thêm `person_id()` nếu cần) hoặc `new_id()`.
- [x] **Task 3 — Logic enrich thị giác** (AC: #1, #2, #4): `pipeline/enrich_vision.py` — `enrich_scene_vision(session, storage, scene_id, face_recognizer, object_detector, *, face_threshold=0.5) -> dict`:
  - [x] Duyệt Shot của Scene, lấy keyframe qua storage-port, khử keyframe trùng (theo `keyframe_key`, cùng pattern `enrich_scene_vietnamese`).
  - [x] Với mỗi keyframe: `face_recognizer.detect(image) -> list[FaceDetection(embedding)]`; so khớp cosine-similarity với mọi `person.reference_embedding` đã đăng ký; nếu `best_score >= face_threshold` → gán `person_id` + `confidence=best_score`; ngược lại → `person_id=None` (AD-11, không bịa).
  - [x] Với mỗi keyframe: `object_detector.detect(image) -> list[ObjectDetection(label, confidence)]`; gộp toàn bộ Scene vào `scene.objects` (JSON, không dedupe theo label — giữ mọi phát hiện kèm confidence).
  - [x] Idempotent overwrite: xoá toàn bộ `face_appearance` cũ của `scene_id` trước khi insert lại (AD-5 tinh thần — chỉ đè dữ liệu của chính stage này); ghi đè `scene.objects` (không cộng dồn).
- [x] **Task 4 — Adapter production** (guarded, chưa chạy môi trường dev): `pipeline/enrich_vision_backends.py` — `InsightFaceRecognizer` (buffalo_l, qua `storage-port` `local_path` — AD-23) + `YoloObjectDetector` (Ultralytics YOLO26) — theo pattern lazy-import + guard của `enrich_backends.py`/`detect_backends.py`.
- [x] **Task 5 — Test** (AC: #1-#4): `tests/test_enrich_vision.py` + `tests/test_registry.py` — fake face/object detector + sqlite:
  - [x] Face khớp registry + confidence ≥ ngưỡng → gán đúng `person_id`.
  - [x] Face confidence < ngưỡng hoặc không khớp ai → `person_id=None`.
  - [x] Object ghi kèm confidence trong `scene.objects`.
  - [x] `register_person` idempotent theo `name` (gọi 2 lần cùng tên → 1 person, embedding cập nhật).
  - [x] Chạy lại enrich không đụng `scene.transcript`/`scene.ocr_text` (AD-5) và không nhân đôi `face_appearance`.

### Review Findings

- [x] [Review][Patch] Cosine similarity silently truncates on embedding-dimension mismatch (`zip(a, b)` stops at the shorter vector instead of raising) [pipeline/enrich_vision.py:43-51]
- [x] [Review][Patch] `register_person` has an unhandled race on the unique `name` constraint — check-then-act with no catch for a concurrent duplicate insert [pipeline/registry.py:20-31]
- [x] [Review][Patch] `_best_match`/persons query has non-deterministic tie-breaking — no stable ordering when two registered persons tie for highest score [pipeline/enrich_vision.py:54-63,80]
- [x] [Review][Patch] Cosine similarity can return negative confidence, violating the architecture spine's "confidence/score = float 0–1" convention [pipeline/enrich_vision.py:43-51]
- [x] [Review][Patch] Test coverage gaps: multi-shot aggregation (only 1 shot seeded), exact-threshold boundary (`score == face_threshold`), empty-registry case, tie-break determinism [tests/test_enrich_vision.py]
- [x] [Review][Patch] Malformed `reference_embedding` JSON for any registered person crashes the whole scene's face-match (`json.loads` unguarded) [pipeline/enrich_vision.py:54-63]
- [x] [Review][Patch] `cv2.imdecode` returning `None` on corrupt/empty keyframe bytes isn't guarded before use (Story 1.3's `detect_backends.py` established the explicit-check convention) [pipeline/enrich_vision_backends.py]

## Dev Notes

- **AD-11**: khuôn mặt chỉ gán tên khi `confidence ≥ ngưỡng` **và** đã đăng ký trong registry; ngoài ra là "không xác định" — không được suy đoán/bịa danh tính dù confidence gần ngưỡng. Giá trị ngưỡng cụ thể không có trong PRD/epics → `face_threshold=0.5` là `[ASSUMPTION]`, để tham số hoá được (không hardcode sâu trong logic) cho dễ chỉnh khi có dữ liệu thật.
- **AD-6**: face/object chỉ chạy trên **Keyframe** của Shot (đã có từ Story 1.3), không chạy mọi frame; tái dùng keyframe đã khử gần-trùng.
- **AD-5**: mỗi stage chỉ ghi field-namespace của mình. Story này thêm bảng `face_appearance` (domain riêng, không phải cột JSONB dùng chung trên Scene) + cột `scene.objects` (JSON riêng của object stage) — không được đụng `transcript`/`ocr_text` của Story 1.4.
- **AD-23**: face/object model đọc ảnh keyframe qua `storage-port` (`get`/`local_path`), không ghép path filesystem trực tiếp.
- **Registry là câu hỏi mở của PRD** (`prd.md` dòng ~252: "quy trình đăng ký danh tính do ai làm, cập nhật thế nào?" — chưa chốt). MVP: `register_person` là hàm Python thuần (không có route API/UI ở story này — UX defer theo PRD §6.2); story sau (ngoài scope Epic 1) có thể bọc thành API nếu cần.
- **Không tự chế** similarity vector store: so khớp face bằng cosine similarity thuần Python trên `reference_embedding` (JSON list[float]) — **không** dùng pgvector ở story này (pgvector dành cho `scene_embedding`, Story 1.6); giữ đơn giản, tránh phụ thuộc sớm.
- Model thật (InsightFace buffalo_l, YOLO26) đi vào `enrich_vision_backends.py` theo đúng pattern guarded lazy-import của `enrich_backends.py` (Story 1.4) và `detect_backends.py` (Story 1.3) — build container không có `insightface`/`ultralytics` vẫn import module được, chỉ raise khi thật sự gọi.
- ⚠️ Cờ license (không phải việc của story này, ghi lại để không quên): YOLO26 = AGPL-3.0, InsightFace buffalo_l = non-commercial — rà/thay (RT-DETR/Apache) trước khi thương mại hoá.

### Project Structure Notes

- File mới nằm đúng `pipeline/` (filters ingest) theo source tree ở spine — song song với `enrich.py`/`enrich_backends.py` (Story 1.4) và `detect.py`/`detect_backends.py` (Story 1.3).
- `pipeline/registry.py` là module mới (không có tiền lệ) — vì Person là identity registry dùng chung cho face stage, tách khỏi logic enrich thuần để dễ tái dùng nếu sau này lộ ra API (Epic 3+).
- Migration mới = `0005`, nối tiếp `0004` (Story 1.4); không sửa migration cũ.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story-1.5]
- [Source: _bmad-output/planning-artifacts/architecture/architecture-scene-intelligence-2026-07-03/ARCHITECTURE-SPINE.md#AD-5,#AD-6,#AD-11,#AD-23]
- [Source: _bmad-output/planning-artifacts/prds/prd-scene-intelligence-2026-07-03/prd.md (dòng ~106, ~138, ~209, ~228, ~252)]
- [Source: _bmad-output/implementation-artifacts/1-4-lam-giau-tieng-viet-asr-ocr.md] (pattern enrich cột riêng + guarded adapter)
- [Source: pipeline/enrich.py, pipeline/enrich_backends.py, pipeline/detect.py, pipeline/detect_backends.py, shared/models.py, shared/ids.py, shared/storage.py, tests/test_enrich.py, tests/conftest.py]

## Dev Agent Record

### Agent Model Used

claude-sonnet-5 (BMad dev-story)

### Debug Log References

- `uv run pytest` → **39 passed** (35 + 4 mới). `uv run ruff check` trên file mới/sửa → sạch.
- Sau code review (7 patch áp dụng): `uv run pytest` → **47 passed** (39 + 8 mới). `uv run ruff check` → sạch.

### Completion Notes List

- **Schema** (migration `0005`): bảng `person` (`reference_embedding` JSON list[float]), bảng `face_appearance` (`scene_id`/`person_id` FK, `confidence`), cột `scene.objects` (JSON) — AC-1/2/4.
- **`pipeline/registry.py`**: `register_person` upsert theo `name` — tạo mới hoặc cập nhật `reference_embedding` (AC-3).
- **`pipeline/enrich_vision.py`**: `enrich_scene_vision` — duyệt keyframe các Shot (dedupe theo `keyframe_key`, cùng pattern Story 1.4), face-match bằng cosine similarity thuần Python (không pgvector) vs `person.reference_embedding`; gán `person_id` chỉ khi `score >= face_threshold`, ngược lại `None` (AD-11); object ghi kèm confidence vào `scene.objects`; idempotent — xoá `face_appearance` cũ trước khi insert lại, ghi đè `scene.objects`, không đụng `transcript`/`ocr_text` (AD-5).
- **Adapter production** (`enrich_vision_backends.py`): `InsightFaceRecognizer` (buffalo_l) + `YoloObjectDetector` (YOLO26) — guarded lazy-import theo pattern `enrich_backends.py`/`detect_backends.py`; decode ảnh bytes lấy từ storage-port ở caller, không tự đọc storage. Sanity-check import module thành công khi chưa cài `insightface`/`ultralytics`. CHƯA chạy môi trường này.
- **Test**: `tests/test_registry.py` (2 tests) + `tests/test_enrich_vision.py` (4 tests) — fake face/object detector + sqlite, phủ đủ AC-1 đến AC-4.
- ⚠️ Ngưỡng `face_threshold=0.5` là `[ASSUMPTION]` (không có số cụ thể trong PRD/epics) — tham số hoá để chỉnh sau khi có dữ liệu thật/eval (Epic 4).
- ⚠️ Cờ license (đã ghi ở Dev Notes, không phải việc story này): YOLO26 (AGPL-3.0), InsightFace buffalo_l (non-commercial) — rà/thay trước thương mại hoá.
- **Code review (7 patch áp dụng, xem Review Findings)**: `_cosine_similarity` raise khi lệch chiều embedding + kẹp similarity âm về 0 (đúng convention "confidence/score 0–1" của spine); `_best_match` bỏ qua registry entry hỏng (JSON lỗi/lệch chiều) thay vì crash cả Scene; persons query có `order_by(created_at, person_id)` để tie-break xác định qua các lần chạy; `register_person` dùng SAVEPOINT (`begin_nested`) bắt `IntegrityError` khi đua trên `name` unique thay vì raise; `enrich_vision_backends.py` raise rõ khi `cv2.imdecode` trả `None` (ảnh hỏng), theo đúng convention `detect_backends.py` (Story 1.3). Thêm 8 test: dimension-mismatch raise, negative-clamp, malformed-entry-skip, empty-registry, threshold-boundary (`score == threshold`), tie-break-deterministic-across-reruns, multi-shot-aggregation.

### File List

- **Mới**: `pipeline/registry.py`, `pipeline/enrich_vision.py`, `pipeline/enrich_vision_backends.py`, `migrations/versions/0005_face_object_enrich.py`, `tests/test_registry.py`, `tests/test_enrich_vision.py`
- **Sửa**: `shared/models.py` (thêm `Person`, `FaceAppearance`, `Scene.objects`)

## Change Log

- 2026-07-03 — Story 1.5: làm giàu thị giác (face + object), bảng `person`/`face_appearance`, cột `scene.objects`, registry đăng ký danh tính.
- 2026-07-03 — Code review: 7 patch áp dụng (dimension-mismatch guard, confidence 0-1 clamp, tie-break xác định, register_person chống race, malformed-registry guard, cv2.imdecode guard) + 8 test mới. 14 finding khác dismiss (khớp convention/precedent đã có hoặc đã tracked ở PRD/architecture).
