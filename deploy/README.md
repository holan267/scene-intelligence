# deploy/

Triển khai on-prem 1 node (AD-14). `docker compose up` khởi động Postgres 18+pgvector và API (tự chạy `alembic upgrade head` rồi uvicorn).

- `MEDIA_ROOT` (trong container) luôn là `/data/media`. Đường **host** được bind-mount vào
  đó đặt ở biến `MEDIA_HOST_PATH` trong `deploy/.env` — khác nhau theo máy nên **không**
  hard-code vào compose.
- Air-gap: image kéo sẵn về registry nội bộ; runtime không gọi Internet.

```bash
cd deploy
cp .env.example .env     # rồi sửa MEDIA_HOST_PATH cho đúng máy đang chạy
docker compose up --build
curl http://localhost:8000/api/v1/health
```

### `MEDIA_HOST_PATH` theo hệ điều hành

| Máy | Ví dụ giá trị |
| --- | --- |
| Windows | `D:/media` (dùng `/`, không dùng `\`; ổ phải được share trong Docker Desktop → Settings → Resources → File sharing) |
| macOS | `/Users/<user>/media`, hoặc `/Volumes/<ổ ngoài>/media` |
| Linux / NAS | `/mnt/nas/media` |

Không đặt biến ⇒ mặc định `../_data/media` (thư mục `_data/` ở gốc repo, đã gitignore) —
đủ cho dev, đổi sang **NAS/SAN** thật khi triển khai kho lớn (AD-23).

> Lỗi `invalid volume specification: '.../D:/media:/data/media:rw'` nghĩa là compose vẫn
> đang nhận đường Windows `D:/media` trên máy macOS/Linux: Docker coi nó là đường tương
> đối và nối vào thư mục hiện tại. Sửa `MEDIA_HOST_PATH` trong `deploy/.env` thành đường
> tuyệt đối của máy đó rồi `docker compose up` lại.

⚠️ **Nâng cấp từ compose cũ**: volume `pgdata` từng mount ở `/var/lib/postgresql` (parent,
sai — data thật rơi vào anonymous volume). Đã đổi sang `/var/lib/postgresql/data` (PGDATA
chuẩn). Nếu bạn đã có volume `pgdata` tạo từ compose cũ, **đừng** tái sử dụng trực tiếp —
tạo volume mới (`docker compose down -v` rồi `up` lại) và phục hồi dữ liệu qua `pg_restore`
(mục Backup bên dưới) thay vì trông chờ volume cũ tự khớp path mới.

## Nạp lô & chạy pipeline

Worker (`deploy-worker-1`) **không tự quét** thư mục media: nó chỉ drain hàng đợi trong
Postgres. Job phải được nạp qua API — `source_dir` là đường **trong container**
(`/data/media`, không phải đường host; `resolve_source_dir` chặn mọi path ngoài MEDIA_ROOT):

```bash
curl -X POST http://localhost:8000/api/v1/ingest \
  -H 'Content-Type: application/json' -d '{"source_dir":"/data/media"}'
# -> {"meta": {"job_id": "...", "queued": 1, ...}}

curl http://localhost:8000/api/v1/jobs/<job_id>     # theo dõi tiến độ
```

Mỗi task: đăng ký `Video` → **detect** (tách scene/shot + trích keyframe, dedupe pHash).
Keyframe ghi vào `MEDIA_ROOT/<video_id>/keyframes/` (dẫn xuất, loại khỏi backup — AD-4).
Decode chạy bằng CPU trong container, không cần model server. Tắt bằng
`DETECT_ON_INGEST=false` trong `deploy/.env` nếu chỉ muốn nạp danh mục.

Nạp lại cùng thư mục chỉ re-queue task `skipped`/`error`; task `done` bị coi là trùng. Muốn
detect lại từ đầu (vd đổi `DETECT_THRESHOLD`) thì xoá row tương ứng trong `ingest_task`.

Các bước enrich/describe/embed **chưa** nối vào worker — job `done` nghĩa là đã detect xong,
chưa có mô tả hay vector.

## Model server BGE-M3 (bắt buộc cho search & bước embed của pipeline)

BGE-M3 **không** nằm trong compose: nó cần GPU/Metal của máy host mà container không có.
Trên máy dev 1 node (nhất là Apple Silicon — vLLM cần CUDA, không chạy native; image CPU của
TEI/Infinity chỉ có bản amd64) thì chạy bằng **Ollama trên host**:

```bash
ollama pull bge-m3        # ~1.2 GB, weights nằm local => vẫn air-gap được sau lần tải đầu
ollama serve              # mở cổng 11434
curl http://localhost:11434/v1/embeddings \
  -H 'Content-Type: application/json' \
  -d '{"model":"BGE-M3","input":"thử"}'   # kỳ vọng data[0].embedding dài 1024
```

Ollama cung cấp `/v1/embeddings` tương thích OpenAI, và **match tên model không phân biệt
hoa/thường**, nên `{"model": "BGE-M3"}` mà adapter gửi khớp đúng `bge-m3:latest` — không cần
sửa payload. Dense 1024 chiều đúng bằng `SCENE_EMBEDDING_DIM`.

Container trỏ tới host qua `EMBED_MODEL_URL` (đã có mặc định trong compose):

```
EMBED_MODEL_URL=http://host.docker.internal:11434
```

> ⚠️ **Đừng dùng `localhost` trong `EMBED_MODEL_URL`.** Trong container `localhost` là chính
> container đó, nên API sẽ trả
> `502 {"message": "Gọi BGE-M3 thất bại: All connection attempts failed"}`.
> Lỗi 502 này cũng xuất hiện khi Ollama chưa chạy — kiểm tra bằng
> `curl http://localhost:11434/api/version` trước khi nghi ngờ code.

Ollama phải đang chạy mỗi khi search hoặc chạy pipeline. Cách bền: bật Ollama.app khởi động
cùng máy, hoặc giữ `ollama serve` trong một launch agent / tmux session riêng.

Khi triển khai on-prem có GPU NVIDIA thật thì đổi `EMBED_MODEL_URL` sang model server
vLLM/TEI riêng (cổng 8002 như thiết kế AD-14) — code không cần sửa.

⚠️ `describe_model_url` (Qwen3-VL, 8001) và `rerank_model_url` (bge-reranker-v2-m3, 8003)
**vẫn chưa có server nào**. Search trả kết quả đúng khi DB rỗng hoặc khi rerank bị bỏ qua
theo `rerank_skip_gap`, nhưng sẽ trả cùng lỗi 502 ở nhánh rerank khi đã có dữ liệu thật:
Ollama không có API rerank nên bge-reranker-v2-m3 cần server khác (TEI `/rerank`, hoặc tự
bọc `FlagEmbedding`).

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
