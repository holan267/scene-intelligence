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

Mỗi task: đăng ký `Video` → **detect** (tách scene/shot + trích keyframe, dedupe pHash) →
**enrich** (ASR + OCR, nếu bật). Keyframe ghi vào `MEDIA_ROOT/<video_id>/keyframes/` (dẫn
xuất, loại khỏi backup — AD-4). Decode chạy bằng CPU trong container, không cần model
server. Tắt bằng `DETECT_ON_INGEST=false` trong `deploy/.env` nếu chỉ muốn nạp danh mục.

Nạp lại cùng thư mục chỉ re-queue task `skipped`/`error`; task `done` bị coi là trùng. Muốn
detect lại từ đầu (vd đổi `DETECT_THRESHOLD`) thì xoá row tương ứng trong `ingest_task`.

Các bước describe/embed **chưa** nối vào worker — job `done` nghĩa là đã detect (và enrich
nếu bật) xong, chưa có `scene_document` hay vector.

## Stage enrich: ASR (PhoWhisper-large) + OCR (EasyOCR + VietOCR)

Khác BGE-M3 bên dưới, hai model này **chạy in-process trong worker**, không qua model
server — chúng không có endpoint OpenAI-compatible. Mặc định **TẮT**. Bật cần đủ ba thứ:

| # | Thứ cần | Làm sao |
| --- | --- | --- |
| 1 | Thư viện trong image | `INSTALL_ENRICH=true` (build-arg, +~2-3 GB vì torch) |
| 2 | Trọng số trên đĩa | `deploy/fetch-models.sh` trên máy **có Internet**, copy sang node |
| 3 | Bật stage | `ENRICH_ON_INGEST=true` (thêm `ENRICH_OCR=false` nếu chỉ chạy ASR) |

Thiếu bất kỳ cái nào thì task rơi vào `error` kèm thông báo chỉ rõ thiếu gì (worker không
sập). Kết quả ghi vào `scene.transcript` và `scene.ocr_text`.

### Chạy ASR-only (`ENRICH_OCR=false`)

Dùng khi trọng số OCR chưa nạp được. ASR vẫn chạy bình thường; stage OCR **không ghi gì**
vào `scene.ocr_text`, nên kết quả OCR của lượt trước (nếu có) không bị xoá — đúng AD-5.
Không có cờ riêng để tắt ASR: tắt ASR nghĩa là tắt luôn `ENRICH_ON_INGEST`.

### Vướng đã gặp khi dựng trọng số

- **VietOCR:** `ModuleNotFoundError: No module named 'pkg_resources'`. vietocr vẫn import
  `pkg_resources`, thứ đã bị gỡ khỏi môi trường Python ≥3.12 khi không có setuptools. Cài
  thêm `setuptools` vào cùng venv rồi chạy lại `fetch-models.sh`.
- **ASR trên CPU:** ctranslate2 báo `compute type ... float16 ... converted to float32` —
  máy không chạy được float16 nên model nở gấp đôi bộ nhớ và chậm hơn. Trên node CPU nên
  dựng lại bằng `ASR_QUANTIZATION=int8 deploy/fetch-models.sh`; trên node GPU thì float16
  là đúng.

### Dựng trọng số (bước một lần, trên máy có Internet)

Runtime **không bao giờ tải trọng số** (AD-14). Cả ba thư viện đều mặc định tự tải về
`~/.cache` khi gọi lần đầu — trong container thì vừa gọi Internet vừa mất sạch sau mỗi lần
restart, nên `pipeline/enrich_backends.py` chặn hết các đường đó và fail nếu thiếu file.

```bash
uv pip install -e '.[enrich,fetch-models]'
deploy/fetch-models.sh                 # mặc định ghi vào <repo>/_data/models
```

Script làm ba việc, bỏ qua thứ đã có (chạy lại an toàn):

1. **PhoWhisper-large** — tải từ `vinai/PhoWhisper-large` rồi **convert sang CTranslate2**.
   Bước convert là bắt buộc: PhoWhisper ship dạng HF/Whisper weights, faster-whisper không
   nạp trực tiếp được. Script cũng bảo đảm có `tokenizer.json` — thiếu file này thì lúc
   chạy faster-whisper lặng lẽ tải `openai/whisper-tiny` từ HuggingFace.
2. **EasyOCR CRAFT** (`craft_mlt_25k.pth`) — chỉ phần dò vùng chữ; phần đọc để VietOCR lo
   vì recognizer `vi` sẵn có của EasyOCR đọc dấu kém hơn hẳn.
3. **VietOCR** (`vgg_transformer.pth` + `.yml`) — bản Python **pbcquoc**, không phải app
   Java Tesseract trùng tên. Config YAML được lưu ra đĩa vì `Cfg.load_config_from_name()`
   tải config từ `vocr.vn` qua mạng, không chạy được trên node air-gap.

Kết quả (~3-4 GB):

```
_data/models/
├── PhoWhisper-large-ct2/   model.bin, tokenizer.json, preprocessor_config.json...
├── easyocr/                craft_mlt_25k.pth
├── vietocr/                vgg_transformer.pth, vgg_transformer.yml
└── SHA256SUMS
```

Copy sang node air-gap rồi **đối chiếu** — sneakernet hay hỏng âm thầm:

```bash
rsync -a _data/models/ <node>:/srv/scene-intelligence/_data/models/
ssh <node> 'cd /srv/scene-intelligence/_data/models && shasum -a 256 -c SHA256SUMS'
```

### Bật trên node

```bash
# deploy/.env
INSTALL_ENRICH=true
ENRICH_ON_INGEST=true
MODEL_HOST_PATH=/srv/scene-intelligence/_data/models
ENRICH_DEVICE=cuda      # cpu nếu node không có GPU

docker compose build worker && docker compose up -d worker
```

`MODEL_HOST_PATH` bind-mount **read-only** vào `/models`. Đặt `ENRICH_DEVICE=cuda` khi node
có GPU — OCR hàng trăm keyframe mỗi video trên CPU rất chậm. (compose chưa khai báo
`deploy.resources.devices`; thêm khi có node GPU thật.)

### ⚠️ License cần rà trước khi thương mại hoá

- **PhoWhisper-large** là tài sản nghiên cứu của VinAI. Whisper gốc là MIT nhưng điều khoản
  của bản fine-tune mới là thứ có hiệu lực — rà trước khi bán ra ngoài.
- EasyOCR (Apache-2.0) và VietOCR (Apache-2.0) thì sạch.

## Model server BGE-M3 + Qwen3-VL (bắt buộc cho search & stage index của pipeline)

Hai model này **không** nằm trong compose: chúng cần GPU/Metal của máy host mà container
không có. Trên máy dev 1 node (nhất là Apple Silicon — vLLM cần CUDA, không chạy native;
image CPU của TEI/Infinity chỉ có bản amd64) thì chạy bằng **Ollama trên host**. Một tiến
trình `ollama serve` phục vụ CẢ HAI trên cùng cổng 11434 — model nào chạy do **tên trong
payload** quyết định, không phải cổng:

```bash
ollama pull bge-m3        # ~1.2 GB — embed scene_document + câu truy vấn
ollama pull qwen3-vl:2b   # ~2.4 GB — sinh Scene Document từ keyframe (describe)
ollama serve              # mở cổng 11434 cho cả hai

# Tag dẫn xuất có num_ctx nới rộng — ĐÂY mới là tag worker gửi (xem cảnh báo bên dưới).
# deploy/run-worker.sh tự chạy lệnh này nếu tag chưa tồn tại.
curl http://localhost:11434/api/create \
  -d '{"model":"qwen3-vl:2b-ctx16k","from":"qwen3-vl:2b","parameters":{"num_ctx":16384}}'

curl http://localhost:11434/v1/embeddings \
  -H 'Content-Type: application/json' \
  -d '{"model":"BGE-M3","input":"thử"}'   # kỳ vọng data[0].embedding dài 1024

curl http://localhost:11434/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"qwen3-vl:2b-ctx16k","messages":[{"role":"user","content":"xin chào"}]}'
```

Ollama cung cấp `/v1/embeddings` + `/v1/chat/completions` tương thích OpenAI (kể cả
`image_url` dạng `data:image/jpeg;base64,...` mà `Qwen3VLDescriber` gửi).

> ⚠️ **Tên model phải khớp tag.** Ollama match tên không phân biệt hoa/thường nên
> `{"model": "BGE-M3"}` khớp `bge-m3:latest`, nhưng **tag đầy đủ là bắt buộc** với
> Qwen3-VL: không có `qwen3-vl:latest`, gửi `"Qwen3-VL"` trần sẽ trả 404. Xem
> `pipeline/describe_backends.py`.

> ⚠️ **num_ctx mặc định 4096 là quá nhỏ — phải dùng tag dẫn xuất.** qwen3-vl là model
> *thinking*: nó xả phần suy nghĩ ra trước rồi mới viết câu trả lời. Một keyframe đã chiếm
> ~2.1k token prompt, nên với num_ctx=4096 phần suy nghĩ ăn nốt chỗ còn lại và request kết
> thúc bằng `finish_reason="length"` với `content` **rỗng**. Triệu chứng ở worker rất dễ
> đọc nhầm: log có N lần `chat/completions` nhưng chỉ vài lần `embeddings`, phần lớn scene
> kẹt ở `search_status='pending'`, `ingest_task.reason` ghi *"Qwen3-VL trả nội dung rỗng"*
> — trông như lỗi ở bước embed dù bước describe mới là chỗ chết. `options.num_ctx` trong
> payload **không có tác dụng**: lớp OpenAI-compat của Ollama bỏ qua nó (cả `think` lẫn
> `reasoning_effort` cũng vậy), nên num_ctx phải được nướng vào tag bằng `/api/create` như
> trên. Đo trên 3 keyframe thật: 4096 hỏng 2/3 scene, 8192 vẫn có lần bị cắt giữa câu,
> 16384 đủ cho cả 3.

Container trỏ tới host qua hai biến (đã có mặc định trong compose):

```
EMBED_MODEL_URL=http://host.docker.internal:11434
DESCRIBE_MODEL_URL=http://host.docker.internal:11434
```

> ⚠️ **Đừng dùng `localhost` trong hai biến này.** Trong container `localhost` là chính
> container đó, nên API sẽ trả
> `502 {"message": "Gọi BGE-M3 thất bại: All connection attempts failed"}`.
> Lỗi 502 này cũng xuất hiện khi Ollama chưa chạy — kiểm tra bằng
> `curl http://localhost:11434/api/version` trước khi nghi ngờ code.

Ollama phải đang chạy mỗi khi search hoặc chạy pipeline. Cách bền: bật Ollama.app khởi động
cùng máy, hoặc giữ `ollama serve` trong một launch agent / tmux session riêng.

Khi triển khai on-prem có GPU NVIDIA thật thì tách lại thành hai model server vLLM/TEI riêng
(cổng 8001/8002 như thiết kế AD-14) — chỉ đổi env, code không cần sửa. Với vLLM nhớ đặt
`--served-model-name` khớp với `DESCRIBE_MODEL_NAME` mà adapter gửi (vLLM đặt cửa sổ ngữ
cảnh qua `--max-model-len` nên không cần tag dẫn xuất — chỉ cần đủ rộng cho prompt có ảnh).

⚠️ `rerank_model_url` (bge-reranker-v2-m3, 8003) **vẫn chưa có server nào**. Search trả kết
quả đúng khi DB rỗng hoặc khi rerank bị bỏ qua theo `rerank_skip_gap`, nhưng sẽ trả lỗi 502
ở nhánh rerank khi đã có dữ liệu thật: Ollama không có API rerank nên bge-reranker-v2-m3 cần
server khác (TEI `/rerank`, hoặc tự bọc `FlagEmbedding`).

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
