#!/usr/bin/env bash
# Chạy worker ingest TRÊN HOST (không qua compose — xem đầu deploy/docker-compose.yml).
#
#   deploy/run-worker.sh                 # cả 3 stage: detect + enrich + describe/index
#   deploy/run-worker.sh enrich          # chỉ detect + ASR/OCR  (INDEX_ON_INGEST=false)
#   deploy/run-worker.sh index           # chỉ describe + embed  (ENRICH_ON_INGEST=false)
#   deploy/run-worker.sh detect          # chỉ tách scene/shot + keyframe
#
# Vì sao nên tách lượt: worker commit MỘT LẦN sau khi drain xong cả hàng đợi
# (pipeline/worker_main.py::_loop). Chạy cả 3 stage cho một lô lớn nghĩa là hàng giờ công
# nằm trong một transaction chưa commit — worker chết là mất sạch. `enrich` rồi `index` là
# hai lượt ngắn, mỗi lượt tự chốt kết quả vào DB.
#
# Ghi đè bất kỳ biến nào bằng cách export trước khi gọi, ví dụ:
#   ENRICH_OCR=true deploy/run-worker.sh enrich
#
# Cấu hình riêng theo máy: đặt trong deploy/worker.local.env (không commit) — script tự
# nạp nếu có. Biến đã export ở shell luôn thắng file đó.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MODE="${1:-all}"

# --- Python: ưu tiên .venv của repo (nơi có faster-whisper/easyocr/vietocr) -------------
PY_BIN="${PYTHON:-}"
if [ -z "$PY_BIN" ]; then
  if [ -x "$REPO_ROOT/.venv/bin/python" ]; then
    PY_BIN="$REPO_ROOT/.venv/bin/python"
  else
    PY_BIN="python3"
  fi
fi

# --- Cấu hình riêng theo máy ------------------------------------------------------------
LOCAL_ENV="$REPO_ROOT/deploy/worker.local.env"
if [ -f "$LOCAL_ENV" ]; then
  # `set -a` để mọi gán trong file thành biến môi trường mà không cần export từng dòng.
  set -a
  # shellcheck disable=SC1090
  . "$LOCAL_ENV"
  set +a
fi

# --- Mặc định ---------------------------------------------------------------------------
# Khác docker-compose.yml ở hai chỗ, đều vì đây là host chứ không phải container:
#   - postgres/Ollama ở `localhost`, KHÔNG phải `postgres`/`host.docker.internal`
#   - đường dẫn là đường thật trên máy, không phải /data/media và /models
export DATABASE_URL="${DATABASE_URL:-postgresql+psycopg://scene:scene@localhost:5432/scene_intelligence}"
export MEDIA_BACKEND="${MEDIA_BACKEND:-filesystem}"
export MEDIA_ROOT="${MEDIA_ROOT:-$REPO_ROOT/_data/media}"
export API_ENV="${API_ENV:-dev}"

export DETECT_THRESHOLD="${DETECT_THRESHOLD:-27.0}"

# Trọng số ASR/OCR nạp từ đĩa, không bao giờ tải lúc chạy (AD-14) — dựng bằng
# deploy/fetch-models.sh.
export ASR_MODEL_DIR="${ASR_MODEL_DIR:-$REPO_ROOT/_data/models/PhoWhisper-large-ct2}"
export OCR_DETECTOR_DIR="${OCR_DETECTOR_DIR:-$REPO_ROOT/_data/models/easyocr}"
export OCR_RECOGNIZER_DIR="${OCR_RECOGNIZER_DIR:-$REPO_ROOT/_data/models/vietocr}"
# OCR mặc định TẮT: _data/models/vietocr thường chưa có trọng số. OCR không chạy thì
# KHÔNG ghi gì vào scene.ocr_text (AD-5) nên kết quả lượt trước không bị xoá.
export ENRICH_OCR="${ENRICH_OCR:-false}"
export ENRICH_DEVICE="${ENRICH_DEVICE:-cpu}"
# ASR chạy trên CTranslate2, không phải PyTorch: không có 'mps' nên trên Apple Silicon chỉ
# còn CPU. Trọng số float16 nạp trên CPU sẽ bị nở lên float32 (gấp đôi RAM, chậm hơn) —
# int8 lượng tử hoá ngay lúc nạp nên không phải convert lại trọng số. Node GPU:
# ASR_DEVICE=cuda ASR_COMPUTE_TYPE=float16.
export ASR_DEVICE="${ASR_DEVICE:-cpu}"
export ASR_COMPUTE_TYPE="${ASR_COMPUTE_TYPE:-int8}"

# 'qwen3vl' (model server nội bộ) | 'deepseek' (API đám mây — keyframe rời khỏi máy chủ,
# cần DEEPSEEK_API_KEY, xem shared/config.py).
export DESCRIBE_BACKEND="${DESCRIBE_BACKEND:-qwen3vl}"
export DESCRIBE_MODEL_URL="${DESCRIBE_MODEL_URL:-http://localhost:11434}"
export EMBED_MODEL_URL="${EMBED_MODEL_URL:-http://localhost:11434}"

# Tag describe là tag DẪN XUẤT có num_ctx nới rộng, KHÔNG phải tag gốc: qwen3-vl là model
# thinking, với num_ctx=4096 mặc định của Ollama thì một keyframe (~2.1k token prompt) +
# phần suy nghĩ là chạm trần -> model trả content RỖNG -> scene không bao giờ được index.
# num_ctx không đặt được qua payload /v1 (Ollama bỏ qua) nên phải nướng sẵn vào tag; phần
# "Kiểm tra trước khi chạy" bên dưới tự tạo tag này nếu chưa có. Mặc định phải khớp
# `describe_model_name` trong shared/config.py.
export DESCRIBE_MODEL_NAME="${DESCRIBE_MODEL_NAME:-qwen3-vl:2b-ctx16k}"
DESCRIBE_BASE_MODEL="${DESCRIBE_BASE_MODEL:-qwen3-vl:2b}"
DESCRIBE_NUM_CTX="${DESCRIBE_NUM_CTX:-16384}"

# --- Stage bật/tắt theo MODE ------------------------------------------------------------
case "$MODE" in
  all)
    export DETECT_ON_INGEST=true  ENRICH_ON_INGEST=true  INDEX_ON_INGEST=true ;;
  detect)
    export DETECT_ON_INGEST=true  ENRICH_ON_INGEST=false INDEX_ON_INGEST=false ;;
  enrich)
    export DETECT_ON_INGEST=true  ENRICH_ON_INGEST=true  INDEX_ON_INGEST=false ;;
  index)
    # detect tắt: scene/shot đã có từ lượt trước, decode lại chỉ tốn thời gian.
    export DETECT_ON_INGEST=false ENRICH_ON_INGEST=false INDEX_ON_INGEST=true ;;
  *)
    echo "MODE không hợp lệ: '$MODE' (chọn: all | detect | enrich | index)" >&2
    exit 2 ;;
esac

# --- Kiểm tra trước khi chạy ------------------------------------------------------------
# Fail sớm ở đây thay vì để từng task rơi vào 'error' rồi mới đi đọc ingest_task.reason.
if [ ! -d "$MEDIA_ROOT" ]; then
  echo "MEDIA_ROOT không tồn tại: $MEDIA_ROOT" >&2
  exit 1
fi
if [ "$ENRICH_ON_INGEST" = "true" ] && [ ! -f "$ASR_MODEL_DIR/tokenizer.json" ]; then
  echo "Thiếu trọng số ASR ở $ASR_MODEL_DIR (cần model.bin + tokenizer.json)." >&2
  echo "Chạy deploy/fetch-models.sh trên máy có Internet rồi copy sang." >&2
  exit 1
fi
if [ "$INDEX_ON_INGEST" = "true" ] && [ "$DESCRIBE_BACKEND" = "deepseek" ] && [ -z "${DEEPSEEK_API_KEY:-}" ]; then
  echo "DESCRIBE_BACKEND=deepseek nhưng chưa có DEEPSEEK_API_KEY." >&2
  exit 1
fi
# Phần dựng tag num_ctx chỉ có nghĩa với Ollama tự host — backend deepseek bỏ qua.
if [ "$INDEX_ON_INGEST" = "true" ] && [ "$DESCRIBE_BACKEND" = "qwen3vl" ]; then
  if ! curl -sf -m 5 "$DESCRIBE_MODEL_URL/api/tags" >/dev/null 2>&1; then
    echo "Không gọi được model server ở $DESCRIBE_MODEL_URL — chạy \`ollama serve\` trước." >&2
    exit 1
  fi
  # Tag dẫn xuất chưa có -> dựng từ tag gốc với num_ctx đã nới. /api/create là idempotent
  # (tạo lại tag đã có cũng không sao) nhưng vẫn kiểm tra trước để khỏi chờ vô ích.
  if ! curl -sf -m 10 "$DESCRIBE_MODEL_URL/api/show" \
       -d "{\"model\":\"$DESCRIBE_MODEL_NAME\"}" >/dev/null 2>&1; then
    echo "==> dựng $DESCRIBE_MODEL_NAME từ $DESCRIBE_BASE_MODEL (num_ctx=$DESCRIBE_NUM_CTX)"
    if ! curl -sf -m 300 "$DESCRIBE_MODEL_URL/api/create" \
         -d "{\"model\":\"$DESCRIBE_MODEL_NAME\",\"from\":\"$DESCRIBE_BASE_MODEL\",\"parameters\":{\"num_ctx\":$DESCRIBE_NUM_CTX},\"stream\":false}" >/dev/null; then
      echo "Không dựng được $DESCRIBE_MODEL_NAME. Đã pull tag gốc chưa? \`ollama pull $DESCRIBE_BASE_MODEL\`" >&2
      exit 1
    fi
  fi
fi

echo "==> mode      : $MODE (detect=$DETECT_ON_INGEST enrich=$ENRICH_ON_INGEST index=$INDEX_ON_INGEST)"
echo "==> python    : $PY_BIN"
echo "==> media     : $MEDIA_ROOT"
echo "==> database  : ${DATABASE_URL##*@}"
[ "$ENRICH_ON_INGEST" = "true" ] && echo "==> asr        : $ASR_MODEL_DIR ($ASR_DEVICE/$ASR_COMPUTE_TYPE, ocr=$ENRICH_OCR)"
if [ "$INDEX_ON_INGEST" = "true" ]; then
  if [ "$DESCRIBE_BACKEND" = "deepseek" ]; then
    echo "==> describe   : DeepSeek API (${DEEPSEEK_MODEL:-deepseek-flash})"
  else
    echo "==> model srv  : $DESCRIBE_MODEL_URL ($DESCRIBE_MODEL_NAME)"
  fi
fi
echo

# cd vào repo: shared/config.py đọc .env theo thư mục hiện tại, và ASR_MODEL_DIR mặc định
# của Settings là đường tương đối.
cd "$REPO_ROOT"
exec "$PY_BIN" -m pipeline.worker_main
