# api/

API Gateway (FastAPI, `/api/v1`, envelope chuẩn — AD-13). Sở hữu user-state (AD-3). Story 1.1: chỉ health. Story sau: ingest/job API, search API, media proxy (AD-19).

Quản trị kho (UI "Quản lý kho"): `GET /videos`, `GET /jobs`, `GET /ingest/tasks` để liệt kê;
`POST /ingest/tasks/{task_id}/requeue`, `POST /jobs/{job_id}/requeue`,
`POST /ingest/requeue-failed` để đưa task lỗi/bỏ-qua về hàng đợi. Endpoint liệt kê chỉ trả
`name` = tên tệp, không lộ `source_key`/path thật (AD-19).

