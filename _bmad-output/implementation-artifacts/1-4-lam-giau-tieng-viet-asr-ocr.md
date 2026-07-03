---
baseline_commit: f1d539a
---

# Story 1.4: Làm giàu tiếng Việt — ASR + OCR

Status: review

## Story

As a **hệ thống ingest**,
I want **chuyển lời thoại thành văn bản (ASR) và đọc chữ trên hình (OCR) bằng model tiếng Việt**,
so that **mỗi Scene có transcript + OCR chất lượng cao cho tìm kiếm**.

## Acceptance Criteria

1. **Given** một Scene có audio và Keyframe, **When** stage ASR (PhoWhisper) và OCR (VietOCR) chạy, **Then** transcript tiếng Việt và text OCR được ghi vào **cột riêng** của Scene (`transcript`, `ocr_text`) — [Source: #AD-5].
2. **Given** đường NL, **Then** chỉ dùng model **hỗ trợ tiếng Việt** (cấm English-only) — [Source: #AD-9].
3. **Given** chạy lại ASR/OCR, **Then** chỉ đè cột của chính nó, không đụng field stage khác (idempotent) — [Source: #AD-5].
4. **Given** WER ASR trên tập kiểm thử bản tin, **Then** đạt ngưỡng mục tiêu `[ASSUMPTION: ≤15%]` — [Source: NFR-5] *(đo bằng eval thật — defer).*

## Tasks / Subtasks

- [x] **Task 1 — Schema**: migration `0004` thêm cột `scene.transcript`, `scene.ocr_text` (Text nullable).
- [x] **Task 2 — Guard AD-9**: protocol `Transcriber`/`OcrReader` có thuộc tính `language`; enrich từ chối model English-only.
- [x] **Task 3 — Logic enrich**: `enrich_scene_vietnamese` — ASR trên audio scene + OCR trên keyframe các shot; ghi cột riêng; idempotent overwrite.
- [x] **Task 4 — Adapter production**: `PhoWhisperTranscriber` (faster-whisper/CTranslate2) + `VietOcrReader` (EasyOCR+VietOCR) guarded.
- [x] **Task 5 — Test**: fake VI transcriber/ocr + sqlite: ghi cột đúng, idempotent, guard chặn English-only.

## Dev Notes

- **AD-9**: `language` ∈ {`vi`, `multilingual`} mới được vào đường NL; enrich raise nếu English-only.
- **AD-5**: chỉ ghi `transcript`/`ocr_text` (cột riêng), không read-modify-write field stage khác.
- OCR chạy trên **keyframe** của các Shot (AD-6), lấy ảnh qua **storage-port**.
- Model thật (PhoWhisper, VietOCR) trong `enrich_backends.py` — guarded, cần `faster-whisper`/`easyocr`/`vietocr`; CHƯA chạy môi trường này.
- [Source: ARCHITECTURE-SPINE.md#AD-5,#AD-6,#AD-9,#AD-23; epics.md#Story-1.4]

## Dev Agent Record

### Agent Model Used

claude-opus-4-8[1m] (BMad dev-story)

### Debug Log References

- `uv run pytest` → **33 passed** (30 + 3 mới). `ruff check` → sạch.

### Completion Notes List

- **Schema** (migration `0004`): cột `scene.transcript`, `scene.ocr_text` (Text nullable) — AC-1.
- **Guard AD-9**: `_assert_vietnamese` — `Transcriber`/`OcrReader` phải có `language ∈ {vi, multilingual}`; enrich raise nếu English-only (AC-2).
- **enrich_scene_vietnamese**: ASR trên audio scene + OCR trên **keyframe các shot** (lấy ảnh qua storage-port, khử keyframe trùng), ghi **cột riêng** `transcript`/`ocr_text` (AD-5), idempotent overwrite (AC-3).
- **Adapter production** (`enrich_backends.py`): `PhoWhisperTranscriber` (faster-whisper/CTranslate2, `language="vi"`) + `VietOcrReader` (EasyOCR+VietOCR) — guarded, media qua `local_path` (AD-23); CHƯA chạy môi trường này.
- **Test**: fake VI transcriber/ocr + sqlite: ghi cột đúng, idempotent overwrite (đè không cộng dồn), guard chặn English-only.
- ⚠️ NFR-5 (WER ≤15%) đo bằng eval thật với PhoWhisper — defer sang Epic 4.

### File List

- **Mới**: `pipeline/enrich.py`, `pipeline/enrich_backends.py`, `migrations/versions/0004_scene_vi_enrich.py`, `tests/test_enrich.py`
- **Sửa**: `shared/models.py` (Scene.transcript, Scene.ocr_text + import Text)

## Change Log

- 2026-07-03 — Story 1.4: ASR+OCR tiếng Việt, ghi cột transcript/ocr_text, guard AD-9.
