#!/usr/bin/env bash
# Dựng trọng số cho stage enrich (ASR + OCR tiếng Việt).
#
# CHẠY TRÊN MÁY CÓ INTERNET, rồi copy thư mục kết quả sang node air-gap (AD-14).
# Node chạy production KHÔNG bao giờ tải trọng số: pipeline/enrich_backends.py chặn mọi
# đường tải của faster-whisper/EasyOCR/VietOCR và fail nếu thiếu file.
#
#   uv pip install -e '.[enrich,fetch-models]'
#   deploy/fetch-models.sh [THƯ_MỤC_ĐÍCH]        # mặc định <repo>/_data/models
#
# Layout tạo ra (khớp ASR_MODEL_DIR / OCR_DETECTOR_DIR / OCR_RECOGNIZER_DIR):
#   PhoWhisper-large-ct2/   model.bin, tokenizer.json, preprocessor_config.json...
#   easyocr/                craft_mlt_25k.pth
#   vietocr/                vgg_transformer.pth, vgg_transformer.yml
#   SHA256SUMS              để đối chiếu sau khi copy sang node
#
# ⚠️ LICENSE: PhoWhisper-large là tài sản nghiên cứu của VinAI — Whisper gốc là MIT nhưng
# điều khoản của bản fine-tune mới là thứ có hiệu lực. Rà trước khi dùng thương mại.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="${1:-$REPO_ROOT/_data/models}"
ASR_REPO="${ASR_REPO:-vinai/PhoWhisper-large}"
ASR_QUANTIZATION="${ASR_QUANTIZATION:-float16}"
OCR_MODEL="${OCR_MODEL:-vgg_transformer}"

PY_BIN="${PYTHON:-python3}"
if [ -x "$REPO_ROOT/.venv/bin/python" ] && [ -z "${PYTHON:-}" ]; then
  PY_BIN="$REPO_ROOT/.venv/bin/python"
fi

echo "==> Đích:  $DEST"
echo "==> Python: $PY_BIN"

missing="$("$PY_BIN" - <<'PY'
mods = {
    "ctranslate2": "fetch-models",
    "transformers": "fetch-models",
    "huggingface_hub": "fetch-models",
    "easyocr": "enrich",
    "vietocr": "enrich",
    "yaml": "enrich",
}
import importlib.util as u
print(" ".join(sorted({extra for m, extra in mods.items() if u.find_spec(m) is None})))
PY
)"
if [ -n "$missing" ]; then
  echo "THIẾU phụ thuộc (nhóm: $missing)." >&2
  echo "Cài bằng: uv pip install -e '.[enrich,fetch-models]'" >&2
  exit 1
fi

mkdir -p "$DEST"
DEST="$(cd "$DEST" && pwd)"   # tuyệt đối hoá sau khi chắc chắn tồn tại

ASR_REPO="$ASR_REPO" ASR_QUANTIZATION="$ASR_QUANTIZATION" OCR_MODEL="$OCR_MODEL" \
  "$PY_BIN" - "$DEST" <<'PY'
import os
import sys
import urllib.request
from pathlib import Path

dest = Path(sys.argv[1])
asr_repo = os.environ["ASR_REPO"]
quantization = os.environ["ASR_QUANTIZATION"]
ocr_model = os.environ["OCR_MODEL"]

# ---------------------------------------------------------------- ASR: PhoWhisper -> CT2
asr_out = dest / "PhoWhisper-large-ct2"
if (asr_out / "model.bin").is_file():
    print(f"==> ASR: đã có {asr_out}, bỏ qua")
else:
    print(f"==> ASR: tải {asr_repo} (~3 GB) rồi convert sang CTranslate2 ({quantization})")
    from ctranslate2.converters import TransformersConverter
    from huggingface_hub import snapshot_download

    src = Path(snapshot_download(asr_repo))
    # PhoWhisper ship dạng HF/Whisper weights — faster-whisper KHÔNG nạp trực tiếp được,
    # phải convert. Đây là bước một lần, không phải model đóng gói sẵn.
    copy_files = [
        name
        for name in ("tokenizer.json", "preprocessor_config.json", "tokenizer_config.json",
                     "vocab.json", "merges.txt", "normalizer.json", "special_tokens_map.json")
        if (src / name).is_file()
    ]
    TransformersConverter(str(src), copy_files=copy_files).convert(
        str(asr_out), quantization=quantization, force=True
    )

# tokenizer.json PHẢI có: thiếu thì lúc chạy faster-whisper lặng lẽ tải openai/whisper-tiny
# từ HuggingFace -> vỡ air-gap. Repo gốc không phải lúc nào cũng kèm file này nên sinh lại.
if not (asr_out / "tokenizer.json").is_file():
    print("==> ASR: thiếu tokenizer.json, sinh lại từ transformers")
    from transformers import WhisperTokenizerFast

    WhisperTokenizerFast.from_pretrained(asr_repo).save_pretrained(asr_out)
if not (asr_out / "preprocessor_config.json").is_file():
    from transformers import WhisperFeatureExtractor

    WhisperFeatureExtractor.from_pretrained(asr_repo).save_pretrained(asr_out)

# ------------------------------------------------------- OCR (dò chữ): EasyOCR CRAFT
easyocr_dir = dest / "easyocr"
if (easyocr_dir / "craft_mlt_25k.pth").is_file():
    print(f"==> OCR/detect: đã có {easyocr_dir}, bỏ qua")
else:
    print("==> OCR/detect: tải trọng số CRAFT của EasyOCR (~80 MB)")
    easyocr_dir.mkdir(parents=True, exist_ok=True)
    import easyocr

    # Để CHÍNH easyocr tải về đúng thư mục đích: URL đi theo version thư viện, hardcode
    # ở đây sẽ mục theo thời gian. recognizer=False -> chỉ lấy phần dò chữ (VietOCR đọc).
    easyocr.Reader(
        ["vi"], gpu=False, recognizer=False,
        model_storage_directory=str(easyocr_dir), download_enabled=True, verbose=False,
    )

# ------------------------------------------------------- OCR (đọc chữ): VietOCR
vietocr_dir = dest / "vietocr"
weights_path = vietocr_dir / f"{ocr_model}.pth"
config_path = vietocr_dir / f"{ocr_model}.yml"
if weights_path.is_file() and config_path.is_file():
    print(f"==> OCR/read: đã có {vietocr_dir}, bỏ qua")
else:
    print(f"==> OCR/read: tải VietOCR {ocr_model} (~150 MB)")
    vietocr_dir.mkdir(parents=True, exist_ok=True)
    import yaml
    from vietocr.tool.config import Cfg

    # load_config_from_name() GỌI MẠNG (tải YAML từ vocr.vn) -> chỉ chạy được ở đây, không
    # chạy được trên node air-gap. Ghi lại bản hợp nhất để runtime đọc từ đĩa.
    cfg = Cfg.load_config_from_name(ocr_model)
    url = cfg["weights"]
    if not str(url).startswith("http"):
        raise SystemExit(f"config VietOCR không trỏ tới URL trọng số: {url!r}")
    urllib.request.urlretrieve(url, weights_path)
    # KHÔNG ghi URL vào config đã lưu: nếu có ai nạp nó mà không ép 'weights' thì Predictor
    # sẽ lại tải. Đường dẫn tương đối -> không phải URL -> không bao giờ tải.
    cfg["weights"] = weights_path.name
    with config_path.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(dict(cfg), fh, allow_unicode=True, sort_keys=False)

print("==> Xong.")
PY

# Manifest để đối chiếu sau khi copy sang node air-gap (sneakernet hay hỏng âm thầm).
echo "==> Ghi SHA256SUMS"
( cd "$DEST" && find . -type f ! -name SHA256SUMS -exec shasum -a 256 {} + | sort -k2 > SHA256SUMS )

echo
du -sh "$DEST"/* 2>/dev/null || true
cat <<EOF

Copy sang node air-gap rồi kiểm tra:
  rsync -a "$DEST/" <node>:/srv/scene-intelligence/_data/models/
  cd /srv/scene-intelligence/_data/models && shasum -a 256 -c SHA256SUMS

Trên node, trỏ MODEL_HOST_PATH trong deploy/.env vào thư mục đó rồi bật ENRICH_ON_INGEST=true.
EOF
