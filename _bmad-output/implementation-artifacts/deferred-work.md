# Deferred Work

## Deferred from: code review (2026-07-03)

- **pgdata mount path** [deploy/docker-compose.yml] — mount `pgdata` ở `/var/lib/postgresql` (parent) thay vì `/var/lib/postgresql/data` (PGDATA chuẩn) → data thật rơi vào anonymous volume. Bạn đã sửa thủ công; khuyến nghị đổi về `/data`. *(Defer: hạ tầng, không chặn logic.)*
- **Task kẹt `claimed` khi worker crash** [pipeline/ingest.py] — thiếu lease/heartbeat/timeout/reclaim; task claimed mà worker chết sẽ kẹt, `finalize_job` không bao giờ đưa job về `done`. *(Defer: crash-recovery, thuộc hardening vận hành gần Story 1.7.)*
- **I/O đồng bộ chặn event loop** [api/routes_ingest.py, pipeline/detect.py] — `rglob`, `_readable`, `extract`, `storage.put` chạy trực tiếp trên event loop; quét kho lớn nghẽn mọi request. Cần `run_in_executor`/threadpool. *(Defer: tối ưu hiệu năng cho quy mô kho lớn.)*
- **An toàn cạnh tranh khi enqueue đa tiến trình** [pipeline/ingest.py] — dedupe hiện là lookup-trong-tiến-trình + 1 commit; hai tiến trình enqueue trùng `source_key` sẽ IntegrityError roll cả lô. Đã giảm va chạm bằng lookup+requeue, nhưng an toàn thật cần `INSERT ... ON CONFLICT DO NOTHING` (dialect-specific) + per-row savepoint. *(Defer: chỉ cần khi chạy nhiều tiến trình ingest song song.)*
- **scene_id/shot_id ổn định-qua-drift (AD-1 đầy đủ)** [shared/ids.py, pipeline/detect.py] — reconcile đã dọn row mồ côi, nhưng re-detect lệch ms vẫn re-mint id. "Id ổn định khi ranh giới trôi nhẹ" (vd anchor theo nội dung/ordinal + matching) là bài toán riêng. *(Defer: story riêng; hiếm gặp ở MVP vì detector tất định.)*
- **pHash chất lượng cao** [pipeline/detect.py] — aHash là placeholder: ngưỡng 5/64 gộp nhầm shot giống bố cục; frame màu đồng nhất đụng hash. Đổi sang dct-phash + tune ngưỡng cần frame thật + eval. *(Defer: sang story enrichment thị giác.)*
