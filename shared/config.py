"""Cấu hình nạp từ env/.env (AD: config qua env, không hardcode).

Xem Consistency Conventions trong ARCHITECTURE-SPINE.md.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+psycopg://scene:scene@localhost:5432/scene_intelligence"
    media_backend: str = "filesystem"
    media_root: str = "./_data/media"
    api_env: str = "dev"
    # Model servers (AD-14) — endpoint OpenAI-compatible (Story 1.6).
    # Dev 1 máy (Apple Silicon: vLLM cần CUDA, không chạy native) dùng Ollama làm model
    # server: `ollama serve` mở cổng 11434 với /v1/embeddings tương thích OpenAI. Ollama
    # match tên model KHÔNG phân biệt hoa/thường nên `"model": "BGE-M3"` hardcode trong
    # adapter khớp đúng `bge-m3:latest`, trả dense 1024 chiều = SCENE_EMBEDDING_DIM.
    # Từ TRONG container phải dùng host.docker.internal thay cho localhost (localhost trỏ
    # vào chính container) — xem EMBED_MODEL_URL trong deploy/docker-compose.yml.
    # On-prem GPU thật: trỏ sang vLLM/TEI riêng (cổng 8001-8003 như thiết kế ban đầu).
    describe_model_url: str = "http://localhost:8001"
    embed_model_url: str = "http://localhost:11434"
    rerank_model_url: str = "http://localhost:8003"
    # Detect (Story 1.3): worker chạy tách scene/shot ngay sau khi đăng ký Video.
    # Tắt (DETECT_ON_INGEST=false) khi chỉ muốn nạp danh mục video mà chưa decode.
    detect_on_ingest: bool = True
    # Ngưỡng ContentDetector của PySceneDetect: thấp -> cắt nhiều cảnh hơn. 27.0 là mặc
    # định của thư viện; [ASSUMPTION] chưa tinh chỉnh theo chất liệu tin tức (Epic 4).
    detect_threshold: float = Field(default=27.0, gt=0)
    # Enrich tiếng Việt (Story 1.4 wiring): worker chạy ASR (PhoWhisper-large) + OCR
    # (VietOCR) cho từng scene ngay sau detect.
    # Mặc định TẮT — khác detect_on_ingest: `scenedetect` là dependency cứng của project,
    # còn faster-whisper/easyocr/vietocr + trọng số PhoWhisper-large (convert CTranslate2)
    # KHÔNG nằm trong pyproject (nặng, tải riêng theo node cho air-gap AD-14). Bật mặc
    # định sẽ khiến MỌI task rơi vào 'error' trên máy chưa cài model. Bật khi node worker
    # đã có đủ model.
    enrich_on_ingest: bool = False
    # Thư mục model PhoWhisper-large đã convert sang CTranslate2 (faster-whisper nạp theo
    # đường dẫn). Trong container: mount trọng số vào /models (xem deploy/docker-compose.yml).
    asr_model_dir: str = "PhoWhisper-large"
    # Crash-recovery (Story 1.7, NFR-2/AD-18): [ASSUMPTION] lease 15 phút, tối đa 3 lần thử
    task_lease_seconds: int = Field(default=900, gt=0)
    task_max_attempts: int = Field(default=3, gt=0)
    # Metrics (Story 1.7, NFR-8): [ASSUMPTION] cửa sổ trượt 5 phút cho throughput/error-rate
    # gt=0 -> chặn ZeroDivisionError ở collect_metrics() khi cấu hình sai
    metrics_window_seconds: int = Field(default=300, gt=0)
    # Search (Story 2.1, AD-8): [ASSUMPTION] pool ANN trước lọc/rerank, ngưỡng bỏ rerank
    search_pool_size: int = Field(default=20, gt=0)
    # Code review fix (Story 2.2): 0.15 được tune ở Story 2.1 cho normalize_ann_score
    # (cosine-distance, phổ điểm rải dày 0-1). Từ Story 2.2, gap-check chạy trên
    # normalize_rrf_score — điểm giữa hai rank liền kề của MỘT nhánh sát nhau hơn nhiều
    # (vd k=60: rank1-chỉ-1-nhánh=0.5, rank2-chỉ-1-nhánh≈0.492, gap≈0.008) nên ngưỡng 0.15
    # cũ gần như không bao giờ đạt được nữa (cần lệch ~28 rank), khiến rerank chạy gần như
    # mọi truy vấn — vô tình vô hiệu hoá tối ưu "bỏ rerank khi #1 áp đảo" của AD-8. Hạ về
    # 0.05 (tương đương #1 phải dẫn trước #2 khoảng ~8 rank trong cùng một nhánh, hoặc #1
    # là candidate khớp CẢ hai nhánh trong khi #2 chỉ khớp một) để ngưỡng còn ý nghĩa dưới
    # thang điểm RRF. `[ASSUMPTION]` — tinh chỉnh lại khi có Eval set (Epic 4).
    rerank_skip_gap: float = Field(default=0.05, ge=0.0, le=1.0)
    # Search (Story 2.2, AD-8): hằng số Reciprocal Rank Fusion (Cormack et al. 2009) — 60 là
    # giá trị chuẩn phổ biến trong tài liệu IR, tham số hoá để tinh chỉnh sau ở Epic 4
    rrf_k: int = Field(default=60, gt=0)


@lru_cache
def get_settings() -> Settings:
    """Trả về Settings (cache 1 lần cho cả process)."""
    return Settings()
