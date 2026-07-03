---
baseline_commit: 1b2735b
---

# Story 1.3: Tách Scene → Shot → Keyframe

Status: done

## Story

As a **hệ thống ingest**,
I want **tách mỗi Video thành Scene → Shot → Keyframe và tạo keyframe đại diện**,
so that **các bước làm giàu (story sau) chỉ chạy trên khung đại diện và mỗi kết quả trỏ đúng timecode**.

## Acceptance Criteria

1. **Given** một Video đã đăng ký, **When** stage detect chạy, **Then** sinh Scene có `start_ms`/`end_ms` thuộc đúng Video, gắn `scene_id` bất biến, và cập nhật `framerate` của Video — [Source: #AD-1, #AD-12].
2. **Given** mỗi Scene, **Then** sinh các Shot và một Keyframe đại diện/Shot; model thị giác (story sau) chỉ chạy trên Keyframe — [Source: #AD-6].
3. **Given** các Keyframe gần-trùng, **Then** khử trùng bằng **perceptual-hash** (tái dùng keyframe đã lưu thay vì lưu lại) — [Source: #AD-6].
4. **Given** chạy lại detect với cùng ranh giới, **Then** ánh xạ vào `scene_id`/`shot_id` cũ, KHÔNG tạo bản trùng (idempotent) — [Source: #AD-1].
5. **Given** ghi keyframe/thumbnail, **Then** video gốc KHÔNG bị sửa (chỉ thêm dẫn xuất qua storage-port theo media-key) — [Source: #AD-11, #AD-23].

## Tasks / Subtasks

- [x] **Task 1 — Schema Shot/Keyframe** (AC: #1, #2): migration `0003` bảng `shot` (scene_id, timecode ms, keyframe_key, phash).
- [x] **Task 2 — Perceptual hash** (AC: #3): `average_hash` (aHash) + `hamming`.
- [x] **Task 3 — Logic persist** (AC: #1–5): `persist_detection` — cập nhật framerate, upsert Scene/Shot theo id tất định (idempotent AD-1), extract keyframe, dedupe theo phash, lưu qua storage-port dưới `<'{'}video_id{'}'}/keyframes/…`.
- [x] **Task 4 — Adapter production** (AC: #1–3): `SceneDetector`/`KeyframeExtractor` protocol + adapter PySceneDetect/OpenCV (guarded import; chưa chạy trong môi trường này).
- [x] **Task 5 — Test** (AC: tất cả): fake detector/extractor + sqlite: tạo scene/shot, framerate, dedupe keyframe, re-detect idempotent, keyframe lưu qua storage.

## Dev Notes

- **AD-1**: `scene_id`/`shot_id` = UUID5 tất định từ (video_id/scene_id, start_ms, end_ms) → re-detect ranh giới cũ ánh xạ về id cũ; upsert không nhân đôi.
- **AD-6**: chỉ 1 Keyframe/Shot; dedupe phash trước khi (story sau) chạy model thị giác → tiết kiệm GPU.
- **AD-11/AD-23**: chỉ ghi dẫn xuất (keyframe) qua storage-port theo media-key; video gốc bất biến.
- Decode video thật (PySceneDetect + OpenCV) sống trong adapter (`detect_backends.py`) — cần cài `scenedetect`/`opencv-python` + wheel air-gap; test dùng fake để không phụ thuộc video/GPU.
- [Source: ARCHITECTURE-SPINE.md#AD-1,#AD-6,#AD-11,#AD-12,#AD-23; epics.md#Story-1.3]

## Dev Agent Record

### Agent Model Used

claude-opus-4-8[1m] (BMad dev-story)

### Debug Log References

- `uv run pytest` → **24 passed** (19 + 5 mới). `ruff check` → sạch.

### Completion Notes List

- **Schema** (migration `0003`): bảng `shot` (scene_id, timecode ms, `keyframe_key`, `phash`). AC-1/AC-2 ✅.
- **Perceptual-hash**: `average_hash` (aHash) + `hamming` (dùng `int.bit_count`). AC-3.
- **persist_detection**: cập nhật `framerate`; **upsert Scene/Shot theo id tất định** (scene_id/shot_id UUID5) → re-detect idempotent (AC-4 ✅); extract keyframe → **dedupe phash** (tái dùng keyframe đã lưu, AC-3 ✅); lưu keyframe qua **storage-port** dưới `<video_id>/keyframes/…` (dẫn xuất, video gốc bất biến — AC-5 ✅).
- **Adapter production** (`detect_backends.py`): `PySceneDetectDetector` + `OpenCVKeyframeExtractor` — lazy/guarded import (cần `scenedetect`/`opencv-python`; **chưa chạy** trong môi trường này, để dành CI/máy có video+GPU).
- **Test** (fake detector/extractor + sqlite + FilesystemStorage): hash/hamming, tạo scene/shot + framerate, dedupe keyframe (2 giống → 1 lưu + 1 dedupe), keyframe lưu qua storage, re-detect idempotent (không nhân đôi row).

### File List

- **Mới**: `pipeline/detect.py`, `pipeline/detect_backends.py`, `migrations/versions/0003_shots.py`, `tests/test_detect.py`
- **Sửa**: `shared/models.py` (bảng `Shot`), `shared/ids.py` (`shot_id` + namespace)

## Change Log

- 2026-07-03 — Story 1.3: detect Scene→Shot→Keyframe + perceptual-hash dedupe + idempotent persist.

## Review Findings (code review 2026-07-03)

- [x] [Review][Decision→Patch+Defer] **Danh tính scene/shot vs re-detect (AD-1)**: ĐÃ patch bước **reconcile** (`_reconcile` xoá scene/shot+keyframe mồ côi khi re-detect) + validate span. **DEFER** phần "id ổn định-qua-drift" sang story riêng (deferred-work.md) [shared/ids.py, pipeline/detect.py]
- [x] [Review][Decision→Patch] `detect_backends` bỏ qua storage-port → ĐÃ thêm `StoragePort.local_path` và adapter dùng nó (AD-23) [pipeline/detect_backends.py, shared/storage.py]
- [x] [Review][Decision→Defer] **Chất lượng pHash**: giữ aHash làm placeholder MVP (đã ghi rõ); DEFER dct-phash + tune ngưỡng sang story enrichment (deferred-work.md) [pipeline/detect.py]
- [x] [Review][Patch] Shot deduped lưu `phash` của chính nó nhưng `keyframe_key` của shot khác → 2 cột lệch ảnh [pipeline/detect.py]
- [x] [Review][Patch] Re-detect ghi lại MỌI keyframe vào storage mỗi lần chạy (idempotent chỉ ở DB, không ở storage) [pipeline/detect.py]
- [x] [Review][Patch] Thiếu validate `start_ms < end_ms` / không âm cho scene/shot [shared/ids.py, pipeline/detect.py]
- [x] [Review][Patch] `phash String(32)` tràn nếu extractor trả >128 pixel (cột cứng theo độ rộng hash) [shared/models.py]
