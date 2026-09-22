# pipeline/

Chuỗi filter ingest idempotent (AD-5): detect → keyframe → enrich → describe → embed → index.
Chỉ chạy model thị giác trên Keyframe (AD-6). Thêm ở Epic 1 story 1.2+.

## Đã nối vào worker runtime

`worker_main` → `workers.drain()` → `workers.process_task()`:

1. đăng ký `Video` theo `source_key` (idempotent),
2. **detect**: `detect_backends.PySceneDetectDetector` tách scene/shot →
   `detect.persist_detection` ghi `Scene`/`Shot` + keyframe (dedupe pHash).

Các bước enrich / describe / embed-index **chưa** nối: module đã có và có test, nhưng chưa
call-site nào trong runtime gọi tới (cần model server Qwen3-VL/reranker — xem deploy/README).

## Tiêm adapter, không tự dựng

`pipeline/workers.py` giữ thuần logic hàng đợi: nhận `detector`/`extractor`/`storage` qua
tham số, không import OpenCV. Nơi DUY NHẤT dựng adapter thật là `pipeline/worker_main.py`.
Nhờ vậy test hàng đợi chạy trên sqlite với fake port, không cần video hay GPU
(`tests/test_workers_detect.py`).

Tắt detect: `DETECT_ON_INGEST=false` (chỉ nạp danh mục video, không decode).
Ngưỡng cắt cảnh: `DETECT_THRESHOLD` (mặc định 27.0 — thấp hơn ⇒ cắt nhiều cảnh hơn).
