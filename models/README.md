# models/

Client tới model servers (vLLM ≥0.11 cho Qwen3-VL, embedder BGE-M3, reranker bge-reranker-v2-m3). Vietnamese-first, cấm model English-only trong đường NL (AD-9). Weights nạp local (air-gap — AD-14). Chưa cần chạy ở Story 1.1.

⚠️ Thư mục này là **client tới model server**, không chứa trọng số. Trọng số của stage
enrich (PhoWhisper-large, EasyOCR CRAFT, VietOCR) chạy in-process trong worker và nằm dưới
`_data/models/` (đã gitignore) — dựng bằng `deploy/fetch-models.sh`, xem `deploy/README.md`.

