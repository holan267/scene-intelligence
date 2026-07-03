# Stack Verification — mid-2026 (web-checked)

| Technology | Version | Fit | Note |
|---|---|---|---|
| PySceneDetect | 0.7 (5/2026) | ✅ | VFR timestamps; Python ≥3.10 |
| faster-whisper + **PhoWhisper-large** (VinAI) | current | ✅ | **Dùng PhoWhisper-large qua faster-whisper/CTranslate2** cho tiếng Việt (SOTA open Vi ASR), không dùng Whisper base |
| InsightFace (buffalo_l) | 1.0 (5/2026) | ✅⚠️ | buffalo_l vẫn chuẩn; **license thương mại** cần rà khi bán ra ngoài |
| Ultralytics **YOLO26** | 2026 | ✅ | Default hiện tại (NMS-free). "YOLOE" = biến thể open-vocab (YOLOE-26), chỉ dùng nếu cần open-vocab; không phải số version |
| SigLIP 2 | transformers ~4.5x | ✅ | `Siglip2Model`; multilingual vision embedding |
| EasyOCR + **VietOCR (pbcquoc, Python)** | current | ✅⚠️ | Dùng **bản Python pbcquoc/vietocr** (transformer), KHÔNG phải app Java Tesseract trùng tên |
| **Qwen3-VL** (scene description VLM) | 2026 | ✅ | Qwen3-VL 8B (12–16GB) / 32B (24GB). **Qwen2.5-VL đã lỗi thời** |
| **bge-reranker-v2-m3** | cập nhật 2026 | ✅ | Cross-encoder rerank đa ngữ, phủ tiếng Việt tốt |
| **BGE-M3** (text embedding cho scene_embedding) | current | ✅ | Default thực dụng: 100+ ngôn ngữ, 8192 token, dense+sparse+multivector; ăn khớp bge-reranker-v2-m3. (Qwen3-Embedding-8B nếu cần chính xác hơn, tốn hơn) |
| FastAPI | 0.139.0 (7/2026) | ✅ | Python ≥3.10 (dùng 3.12/3.13) |
| PostgreSQL + pgvector | PG 18.x; pgvector 0.8.4 | ✅⚠️ | Tốt tới ~vài triệu–50M vector/1 node (với pgvectorscale); qua ~50–100M chuyển DB chuyên |
| Qdrant | v1.17.1 (3/2026) | ✅ | Dùng khi scale lớn; ACORN sửa filtered-recall |
| **Object storage** | — | ⚠️ **ĐỔI** | **MinIO CE khai tử 2/2026** (repo archived, console gỡ, bản trả phí AIStor). Dùng **SeaweedFS / Garage / Ceph RGW** (S3-compatible) |
| Task queue | — | ✅ | Đã có Postgres → **Postgres-backed (Procrastinate/pgmq)** tránh thêm hạ tầng; nếu giữ Redis thì **Dramatiq** |
| Redis / **Valkey** | Redis 8.8 / Valkey 9.1 | ✅⚠️ | Redis AGPL; **Valkey (BSD)** drop-in sạch license nếu cần |
| Serving Qwen GPU | **vLLM** (prod) / Ollama (dev) | ✅ | vLLM cho throughput/multi-GPU on-prem |
| Web UI | **React 19.2 + Vite 7** | ✅ | SPA nội bộ gated + video HTML5; không cần SSR → React+Vite (Next.js chỉ khi cần SSR/SEO) |

## Red flags cần hành động
1. **MinIO CE đã chết** → chọn S3-store khác (SeaweedFS/Garage/Ceph RGW) ngay.
2. **Tiếng Việt ASR**: nâng cấp Whisper base → **PhoWhisper-large** (đúng cam kết "tiếng Việt first-class").
3. **Qwen3-VL** cho scene description (không Qwen2.5-VL).
4. **VietOCR**: cắm đúng bản Python pbcquoc.
5. **License**: InsightFace (thương mại) + Redis (AGPL) — rà khi thương mại hoá; Valkey là đường thoát Redis.
