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

## Dọn dữ liệu ingest

`python -m pipeline.clean` xoá dữ liệu **dẫn xuất** để nạp lại từ đầu: `scene_embedding` →
`face_appearance` → `shot` → `scene` → `video` → `ingest_task` → `job`, kèm keyframe dưới
`<video_id>/keyframes/`. File video gốc trong `MEDIA_ROOT` **không** bị đụng — nạp lại bằng
`POST /ingest` là dựng lại được toàn bộ (AD-4: Postgres là SoT).

```sh
python -m pipeline.clean --dry-run              # xem trước, không xoá gì
python -m pipeline.clean --yes                  # dọn sạch, không hỏi
python -m pipeline.clean --source-key news/a.mp4  # chỉ 1 video (hoặc --video-id)
python -m pipeline.clean --keep-keyframes       # chỉ xoá dòng DB, giữ file keyframe
```

Xoá `ingest_task` là phần bắt buộc: dedupe trong `enqueue_batch` bỏ qua task `done`, nên
task còn sót sẽ chặn lượt nạp lại.
