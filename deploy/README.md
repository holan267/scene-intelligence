# deploy/

Triển khai on-prem 1 node (AD-14). `docker compose up` khởi động Postgres 18+pgvector và API (tự chạy `alembic upgrade head` rồi uvicorn).

- `MEDIA_ROOT`/volume `media`: đổi sang đường **NAS/SAN** thật khi triển khai kho lớn (AD-23); ổ local chỉ hợp dev.
- Air-gap: image kéo sẵn về registry nội bộ; runtime không gọi Internet.

```bash
cd deploy && docker compose up --build
curl http://localhost:8000/api/v1/health
```
