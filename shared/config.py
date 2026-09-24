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
    # server: `ollama serve` mở cổng 11434, phục vụ CẢ describe lẫn embed qua
    # /v1/chat/completions + /v1/embeddings tương thích OpenAI. Vì vậy describe_model_url
    # và embed_model_url TRÙNG NHAU ở dev — model nào chạy do tên trong payload quyết
    # định, không phải cổng (xem `describe_model_name` dưới đây và tên BGE-M3 hardcode
    # trong pipeline/embed_backends.py).
    # Từ TRONG container phải dùng host.docker.internal thay cho localhost (localhost trỏ
    # vào chính container) — xem DESCRIBE/EMBED_MODEL_URL trong deploy/docker-compose.yml.
    # On-prem GPU thật: tách lại thành vLLM/TEI riêng (cổng 8001-8003 như thiết kế ban
    # đầu) — chỉ đổi env, code không cần sửa.
    describe_model_url: str = "http://localhost:11434"
    embed_model_url: str = "http://localhost:11434"
    # Tên model describe gửi trong payload — phải khớp tag Ollama đang phục vụ (hoặc
    # `--served-model-name` của vLLM). KHÔNG phải tag gốc `qwen3-vl:2b`: qwen3-vl là model
    # *thinking* còn Ollama mặc định num_ctx=4096. Một keyframe đã ngốn ~2.1k token prompt,
    # phần "suy nghĩ" ăn nốt chỗ còn lại rồi chạm trần -> finish_reason='length' và content
    # RỖNG -> describe raise -> scene kẹt ở 'pending' (AD-17), không có lần gọi embeddings
    # nào cho scene đó. Nới cửa sổ ngữ cảnh KHÔNG làm được qua /v1 (Ollama bỏ qua
    # `options.num_ctx` ở lớp OpenAI-compat, cả `think`/`reasoning_effort` cũng vậy) nên
    # num_ctx phải được nướng sẵn vào một tag dẫn xuất — deploy/run-worker.sh tự tạo tag
    # này qua /api/create nếu chưa có. Tự tạo tay:
    #   curl http://localhost:11434/api/create -d '{"model":"qwen3-vl:2b-ctx16k",
    #     "from":"qwen3-vl:2b","parameters":{"num_ctx":16384}}'
    describe_model_name: str = "qwen3-vl:2b-ctx16k"
    # Backend sinh Scene Document: 'qwen3vl' (Model Server nội bộ, mặc định — đúng với
    # air-gap AD-14) | 'deepseek' (API đám mây, dùng khi node chưa có GPU đủ chạy model
    # VL). Hai backend nói CÙNG giao thức /v1/chat/completions nên chỉ khác endpoint,
    # tên model và header xác thực — xem pipeline/describe_backends.py.
    describe_backend: str = "deepseek"
    # DeepSeek — chỉ dùng khi describe_backend='deepseek'.
    # CẢNH BÁO: keyframe RỜI máy chủ (gửi base64 lên api.deepseek.com), ngược với mặc
    # định air-gap của AD-14 — chỉ bật cho tư liệu được phép ra ngoài.
    # base_url không kèm '/v1': adapter tự nối như với các model server khác.
    deepseek_base_url: str = "https://api.deepseek.com"
    # Mặc định RỖNG và phải giữ rỗng: file này do git theo dõi. Key thật đặt qua env
    # (deploy/worker.local.env cho worker host, deploy/.env cho compose — đều gitignore).
    deepseek_api_key: str = ""
    # DeepSeek không có tag num_ctx dẫn xuất như Ollama nên đây là tên model trần.
    deepseek_model: str = "deepseek-flash"
    rerank_model_url: str = "http://host.docker.internal:8090"
    # Detect (Story 1.3): worker chạy tách scene/shot ngay sau khi đăng ký Video.
    # Tắt (DETECT_ON_INGEST=false) khi chỉ muốn nạp danh mục video mà chưa decode.
    detect_on_ingest: bool = True
    # Ngưỡng ContentDetector của PySceneDetect: thấp -> cắt nhiều cảnh hơn. 27.0 là mặc
    # định của thư viện; [ASSUMPTION] chưa tinh chỉnh theo chất liệu tin tức (Epic 4).
    detect_threshold: float = Field(default=27.0, gt=0)
    # Enrich tiếng Việt (Story 1.4 wiring): worker chạy ASR (PhoWhisper-large) + OCR
    # (VietOCR) cho từng scene ngay sau detect.
    # Mặc định TẮT — khác detect_on_ingest: `scenedetect` là dependency cứng của project,
    # còn faster-whisper/easyocr/ietocr + trọng số PhoWhisper-large (convert CTranslate2)
    # KHÔNG nằm trong pyproject (nặng, tải riêng theo node cho air-gap AD-14). Bật mặc
    # định sẽ khiến MỌI task rơi vào 'error' trên máy chưa cài model. Bật khi node worker
    # đã có đủ model.
    enrich_on_ingest: bool = True
    # Trọng số ASR/OCR nạp từ ĐĨA, không bao giờ tải lúc chạy (AD-14 air-gap) — cả ba thư
    # viện đều mặc định tự tải về ~/.cache. Dựng bằng `deploy/fetch-models.sh` trên máy có
    # Internet rồi copy sang node. Trong container: mount vào /models (docker-compose.yml).
    # PhoWhisper-large đã convert CTranslate2 (faster-whisper nạp theo đường dẫn thư mục).
    asr_model_dir: str = "./_data/models/PhoWhisper-large-ct2"
    # Thiết bị + kiểu tính toán của faster-whisper/CTranslate2 (KHÁC `enrich_device` bên
    # dưới, vốn chỉ dành cho EasyOCR/VietOCR chạy trên PyTorch).
    # 'auto' | 'cpu' | 'cuda' — CTranslate2 KHÔNG có backend Metal/MPS, nên trên Apple
    # Silicon chỉ có đường CPU; đặt 'mps' là lỗi.
    asr_device: str = "auto"
    # 'default' giữ nguyên kiểu đã lưu trong model. Trọng số dựng bằng fetch-models.sh mặc
    # định là float16 -> trên CPU không chạy được fp16, ctranslate2 tự nở ngược lên float32
    # (cảnh báo `compute type ... converted to float32`): tốn gấp đôi RAM và chậm hơn.
    # Đặt 'int8' để lượng tử hoá NGAY LÚC NẠP (không cần convert lại trọng số) — đây là
    # lựa chọn cho node CPU/Apple Silicon. Node GPU giữ 'float16'.
    asr_compute_type: str = "default"
    # Tắt riêng OCR, vẫn chạy ASR. Dùng khi trọng số OCR chưa nạp được trên node: OCR
    # không chạy thì KHÔNG ghi gì vào scene.ocr_text (AD-5), nên kết quả OCR của lượt
    # trước không bị xoá. ASR không có cờ riêng — tắt ASR = tắt luôn enrich_on_ingest.
    enrich_ocr: bool = True
    # Thư mục chứa craft_mlt_25k.pth (phần dò vùng chữ của EasyOCR).
    ocr_detector_dir: str = "./_data/models/easyocr"
    # Thư mục chứa <model>.pth + <model>.yml của VietOCR (config hợp nhất, tránh gọi mạng).
    ocr_recognizer_dir: str = "./_data/models/vietocr"
    # 'cpu' | 'cuda' — dùng cho EasyOCR/VietOCR. faster-whisper đọc `asr_device` riêng ở
    # trên (hai stack khác nhau: PyTorch vs CTranslate2). Triển khai đích là 1 node GPU
    # (AD-14): đặt 'cuda' khi node có GPU, OCR hàng trăm keyframe/video trên CPU rất chậm.
    enrich_device: str = "cpu"
    # Index (Story 1.6 wiring): worker chạy describe (Qwen3-VL) -> embed/index (BGE-M3) cho
    # từng scene sau enrich. Đây là stage DUY NHẤT set `scene.search_status='indexed'`
    # (AD-17) — tắt thì scene nằm ở 'pending' và search không trả về gì.
    # Mặc định TẮT: khác detect/enrich (chạy in-process), stage này cần HAI model server
    # (AD-14) sống ở describe_model_url + embed_model_url; bật khi chưa có server sẽ đẩy
    # mọi task vào 'error'.
    index_on_ingest: bool = True
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
