# deploy/

Triển khai on-prem 1 node (AD-14). `docker compose up` khởi động Postgres 18+pgvector và API (tự chạy `alembic upgrade head` rồi uvicorn).

- `MEDIA_ROOT`/volume `media`: đổi sang đường **NAS/SAN** thật khi triển khai kho lớn (AD-23); ổ local chỉ hợp dev.
- Air-gap: image kéo sẵn về registry nội bộ; runtime không gọi Internet.

```bash
cd deploy && docker compose up --build
curl http://localhost:8000/api/v1/health
```

⚠️ **Nâng cấp từ compose cũ**: volume `pgdata` từng mount ở `/var/lib/postgresql` (parent,
sai — data thật rơi vào anonymous volume). Đã đổi sang `/var/lib/postgresql/data` (PGDATA
chuẩn). Nếu bạn đã có volume `pgdata` tạo từ compose cũ, **đừng** tái sử dụng trực tiếp —
tạo volume mới (`docker compose down -v` rồi `up` lại) và phục hồi dữ liệu qua `pg_restore`
(mục Backup bên dưới) thay vì trông chờ volume cũ tự khớp path mới.

## Backup (NFR-9, AD-22)

Chỉ 2 kho **backup-critical**: **Postgres (SoT)** và **media gốc**. Vector store/FTS
(`scene_embedding`) nằm chung Postgres nên `pg_dump` đã tự nhiên phủ; keyframe (derived,
dưới `<video_id>/keyframes/`) bị loại trừ khỏi backup media vì dựng lại được từ SoT + media
gốc (AD-4). Lịch/tần suất backup-DR cụ thể để lại cho khảo sát hạ tầng thật của đài — MVP
chỉ cung cấp script chạy thủ công hoặc gắn cron ngoài host (compose không có service
scheduler riêng).

```bash
chmod +x backup.sh   # nếu bit thực thi chưa được giữ khi checkout/copy
BACKUP_DIR=/path/to/backups \
PGHOST=localhost PGPORT=5432 PGUSER=scene PGDATABASE=scene_intelligence \
MEDIA_ROOT=/data/media \
  ./backup.sh
```

Chạy không tương tác (cron): export thêm `PGPASSWORD=scene` (hoặc mật khẩu thật) trước khi
gọi script — `pg_dump` tự đọc biến này; nếu không, `pg_dump` có thể treo/hỏi mật khẩu.

Phục hồi:

```bash
# Postgres — pg_restore vào DB rỗng (đã chạy alembic upgrade head hoặc tạo lại schema)
pg_restore -h localhost -U scene -d scene_intelligence --clean --if-exists postgres_<stamp>.dump

# Media gốc — giải nén vào MEDIA_ROOT
tar -xzf media_<stamp>.tar.gz -C /data/media
```

Sau khi phục hồi Postgres + media gốc, chạy lại pipeline (detect → enrich → describe →
embed/index) để dựng lại keyframe/`scene_embedding`/FTS — không cần backup/phục hồi riêng
cho các kho dẫn xuất này.
