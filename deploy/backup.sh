#!/bin/sh
# Backup Postgres (SoT) + media gốc (Story 1.7, NFR-9/AD-22).
# Phạm vi: chỉ 2 kho backup-critical. Vector store/FTS nằm chung Postgres nên pg_dump đã
# tự nhiên phủ; keyframe (derived, dưới <video_id>/keyframes/) bị loại trừ khỏi media backup
# vì rebuild được từ SoT + media gốc.
#
# Dùng: BACKUP_DIR=/path/to/backups deploy/backup.sh
# Biến môi trường (khớp deploy/docker-compose.yml service `postgres`/`api`):
#   BACKUP_DIR   (bắt buộc) thư mục đích lưu file backup
#   PGHOST       (mặc định: localhost)
#   PGPORT       (mặc định: 5432)
#   PGUSER       (mặc định: scene)
#   PGDATABASE   (mặc định: scene_intelligence)
#   MEDIA_ROOT   (mặc định: ./_data/media)
#   PGPASSWORD   (không bắt buộc — export trước khi gọi script nếu chạy không tương tác
#                 qua cron; pg_dump tự đọc biến này, không cần code riêng ở đây. Không
#                 export -> pg_dump có thể treo/hỏi mật khẩu khi chạy non-interactive.)
set -eu

: "${BACKUP_DIR:?BACKUP_DIR chưa được set}"
PGHOST="${PGHOST:-localhost}"
PGPORT="${PGPORT:-5432}"
PGUSER="${PGUSER:-scene}"
PGDATABASE="${PGDATABASE:-scene_intelligence}"
MEDIA_ROOT="${MEDIA_ROOT:-./_data/media}"

mkdir -p "$BACKUP_DIR"
STAMP=$(date +%Y%m%d%H%M%S)

echo "==> pg_dump ($PGDATABASE@$PGHOST:$PGPORT) -> $BACKUP_DIR/postgres_$STAMP.dump"
pg_dump -Fc -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" \
    -f "$BACKUP_DIR/postgres_$STAMP.dump"

echo "==> media gốc ($MEDIA_ROOT, loại trừ keyframe dẫn xuất) -> $BACKUP_DIR/media_$STAMP.tar.gz"
tar --exclude='*/keyframes/*' -czf "$BACKUP_DIR/media_$STAMP.tar.gz" -C "$MEDIA_ROOT" .

echo "==> xong: $BACKUP_DIR/postgres_$STAMP.dump, $BACKUP_DIR/media_$STAMP.tar.gz"
