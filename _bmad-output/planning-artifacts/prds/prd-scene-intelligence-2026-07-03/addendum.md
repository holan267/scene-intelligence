# Scene Intelligence — PRD Addendum (technical-how)

Tài liệu này giữ **chiều sâu kỹ thuật** không thuộc PRD (PRD nói *năng lực*, addendum nói *cách*). Dành cho `bmad-architecture` / thiết kế giải pháp. Nguồn: intent doc phiên brainstorm + phiên TRIZ + research thị trường.

## 1. Pipeline làm giàu (đề xuất, không ràng buộc)

Stack tham chiếu (từ readme/brainstorm — là gợi ý, kiến trúc có thể thay best-of-breed):

| Bước | Vai trò | Gợi ý mô hình |
|---|---|---|
| Scene splitting | Tách cảnh | PySceneDetect |
| Shot → Keyframe | Chọn khung đại diện | (theo shot boundary) |
| ASR (tiếng Việt) | Lời thoại → text | Faster Whisper large-v3; cân nhắc fine-tune/thay bằng ASR tiếng Việt on-prem (Speechmatics/AppTek VN, VietASR, dữ liệu VLSP) |
| OCR (tiếng Việt) | Chữ trên hình | EasyOCR + VietOCR |
| Face | Nhận diện khuôn mặt | InsightFace buffalo_l |
| Object | Phát hiện đối tượng | YOLOE |
| Visual embedding | Vector hình ảnh (cho "cảnh giống cảnh này") | SigLIP2 |
| Shot scale | Cỡ cảnh | ResNet (model yếu hơn — coi là tag phụ) |
| Scene Document + keywords | Mô tả cảnh NL | Qwen (chạy 1 lần/scene) |

**Lưu ý best-of-breed:** thị trường (eMAM+Whisper+Twelve Labs, Vizrt+DeepVA) cho thấy nên **sở hữu pipeline + UX + tầng tiếng Việt**, cắm/thay mô hình nền, thay vì tự làm mô hình nền. Twelve Labs (Marengo/Pegasus) là lựa chọn build-vs-buy cho embedding/scene-description nếu chấp nhận nặng/on-prem.

## 2. Tiết kiệm GPU (hiện thực NFR thông lượng ingest — FR-1/4.1)

- **Scene → Shot → Keyframe**: chạy mô hình thị giác chỉ trên 1 Keyframe đại diện/Shot, không mọi khung → giảm ~10–50×.
- **Cascade rẻ → đắt**: mô hình rẻ lọc trước (có người? có chữ?), mô hình đắt (InsightFace, Qwen) chỉ chạy khi Keyframe "đáng".
- **Perceptual-hash khử trùng**: Keyframe gần trùng (studio đọc tin 5 phút) → hash, xử lý 1, gán kết quả cho cả cụm.
- **Qwen ghìm sau cùng**, chạy đúng 1 lần/Scene (mô hình đắt nhất).

## 3. scene_embedding = 1 vector "Scene Document" gộp (hiện thực FR-5)

Quyết định đã chốt: **một** vector gộp/Scene cho tìm kiếm (không tách visual/text/scene search song song). Vector SigLIP thị giác vẫn lưu riêng **chỉ để phục vụ "cảnh giống cảnh này" (FR-11)**, không tham gia search bằng chữ.

**Nguyên tắc vàng:** embed **MÔ TẢ do Qwen viết bằng ngôn ngữ tự nhiên** (như editor kể lại), KHÔNG embed tín hiệu thô — vì query là ngôn ngữ tự nhiên, index cũng phải là ngôn ngữ tự nhiên thì hai vector mới gần nhau.

**Công thức Scene Document (có trọng số):**
```
[Chủ thể + hành động]      ← quan trọng nhất, nhấn/lặp
[Người có tên]              (chỉ khi confidence cao + đã đăng ký)
[Đối tượng → lời tự nhiên]  (không phải label thô; bỏ generic)
[Chữ trên hình - chọn lọc]  (OCR đã siết stopword)
[Bối cảnh]                  (cỡ cảnh / trong-ngoài / ngày-đêm)
[Tóm tắt lời nói 1–2 câu]   (KHÔNG dán cả transcript)
```

**Mâu thuẫn giàu ↔ nhòe** (nhồi bừa làm loãng vector). Đòn:
- Có trọng số: chủ thể = "tiêu đề", tag phụ chỉ 1 lần.
- Cắt transcript còn 1–2 câu tóm.
- Chunk Scene đa nhịp (1 Scene 2 nội dung rất khác → 2 sub-embedding).

## 4. Siết nhiễu (hiện thực FR-13)

**Rác = tín hiệu (a) xuất hiện ở HẦU HẾT Scene [vô-phân-biệt], hoặc (b) confidence thấp [sai còn tệ hơn thiếu].**

| Tín hiệu | Cách siết |
|---|---|
| OCR (bẩn nhất) | Bỏ chuỗi <2 ký tự/ký tự lạ; **khử chuỗi lặp toàn kho → stopword bằng IDF** (tự học rác theo chính kho); giữ text có nghĩa |
| Face | Chỉ ghi tên khi confidence cao + đã đăng ký; mặt lạ = "không xác định", KHÔNG bịa "Person A" |
| Object | Bỏ confidence thấp; bỏ generic (person/wall/floor ở tin tức); giữ hiếm & đặc trưng |
| Transcript | Tóm 1–2 câu, cắt filler |
| Shot scale/emotion | Chỉ đưa khi confidence cao; tag phụ |

## 5. Hybrid Search — phễu 4 tầng (hiện thực FR-6/7/8 + NFR độ trễ)

```
Chục triệu Scene
  ① SQL metadata filter        ~5ms   → còn vài nghìn
  ② song song: Vector ANN(HNSW) top200 + BM25 top200   ~20ms
  ③ merge RRF                  ~2ms   → top100
  ④ rerank BGE cross-encoder   ~100ms → top50 → top10
  → ~130–200ms
```
Win-both: mô hình đắt (reranker) chỉ chạm ~50 Scene, không quét cả kho.

**Núm vặn nhanh↔chuẩn:**
- ANN `ef_search` (cao = chuẩn hơn/chậm hơn).
- **Rerank có điều kiện**: bỏ rerank nếu #1 bỏ xa #2 → latency tự co giãn theo độ khó.
- Cache query hot.
- **Dồn công nặng về ingest để query rẻ** — chính là cách giữ lời hứa "gõ 1 câu, vài giây ra kết quả".
- **HyDE** (tuỳ chọn): LLM viết "Scene Document lý tưởng" khớp query rồi embed cái đó → so document-với-document, cùng phương ngữ, trúng hơn. Chi phí 1 lần LLM nhẹ/query.

## 6. Scale hàng chục nghìn giờ trở lên (Open Question §8.1)

- Lưu 3 tầng: PostgreSQL (metadata + JSONB), Vector DB (scene_embedding), Object Storage (video gốc/proxy).
- Lộ trình vector: **pgvector** (quy mô vừa) → **Qdrant** (quy mô lớn).
- Nén vector (PQ/quantization), tiered storage (hot/cold), tính IDF/stopword theo kho.
- Chưa khảo sát phần cứng thực tế → các ngưỡng thông lượng/độ trễ trong PRD đang là `[ASSUMPTION]`.

## 7. Nguyên lý xương sống (giữ nhất quán khi thiết kế)

- **TRIZ "thắng cả hai"** = tập trung công đắt vào đúng ~5% quan trọng: keyframe (GPU), rerank-50 (search), Scene-Document-có-trọng-số (embedding).
- **Kỷ luật thu hẹp**: một-đường-sạch ở sản phẩm ("chỉ tìm scene để dựng") = một vector gộp ở kỹ thuật.

## 8. Bối cảnh cạnh tranh ảnh hưởng thiết kế (từ research)

- **NLE round-trip** (XML/AAF/EDL + panel, timecode đúng) là điểm sống-còn khi thương mại hoá — thiết kế dữ liệu/timecode ngay từ đầu để sau bổ sung dễ (dù MVP defer).
- Wedge phòng thủ: **on-prem + tiếng Việt ASR/OCR + editor UX**. Thiết kế phải giữ được 3 trụ này.
- Đối thủ cần theo dõi: **Moments Lab** (cloud, newsroom AI), **Adobe Premiere Media Intelligence** (nâng chuẩn editor, nhưng bin-scoped/on-device/1 người).
