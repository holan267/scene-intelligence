FROM python:3.12-slim

WORKDIR /app

# Cài thêm phụ thuộc stage enrich (ASR/OCR)? Mặc định KHÔNG: kéo theo torch, +~2-3 GB.
# Bật bằng `--build-arg INSTALL_ENRICH=true` (compose đọc biến INSTALL_ENRICH trong .env).
ARG INSTALL_ENRICH=false

# uv để cài phụ thuộc nhanh, đóng băng theo pyproject
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Cài phụ thuộc TỪ pyproject (không hardcode -> không drift)
COPY pyproject.toml uv.lock* ./
RUN if [ "$INSTALL_ENRICH" = "true" ]; then \
        # libgomp1: torch/onnxruntime cần, image slim không có sẵn.
        # ffmpeg: dự phòng cho decode audio (PyAV đã bundle sẵn, nhưng codec lạ cần bản hệ thống).
        apt-get update && apt-get install -y --no-install-recommends libgomp1 ffmpeg && \
        rm -rf /var/lib/apt/lists/* && \
        uv pip install --system ".[enrich]"; \
    else \
        uv pip install --system .; \
    fi

COPY . .

EXPOSE 8000
CMD ["sh", "deploy/entrypoint.sh"]
