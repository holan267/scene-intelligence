# Scene Intelligence — Intent Document

## 1. Tên & tuyên bố một câu

**Scene Intelligence**: hệ thống upload video/ảnh → pipeline AI tách & làm giàu scene → tìm kiếm trên web bằng ngôn ngữ tự nhiên hoặc keyword.

## 2. Hero use-case (MVP)

**Editor "cứu deadline"**

- **JTBD**: editor gõ 1 câu đời thường → trong ~3s trả về đúng đoạn ~8s băng "ăn" → export một chạm vào timeline.
- **Wow moment** = tốc độ × trúng cảm xúc × export-một-chạm.

## 3. Bộ tính năng lõi editor (5 tính năng thực dụng)

1. NL → thumbnail + timestamp + chèn thẳng vào timeline.
2. Lọc theo cỡ cảnh / có mặt người / độ dài / không dính logo.
3. "Cảnh giống cảnh này" — visual similarity.
4. Export XML/EDL sang Premiere / DaVinci Resolve.
5. Đánh dấu cảnh đã dùng để tránh trùng lặp.

## 4. Xương sống kiến trúc

- **Phễu tìm kiếm 4 tầng** (~130–200ms tổng):
  1. SQL metadata filter (~5ms).
  2. Vector ANN HNSW + BM25 chạy song song, lấy top200 (~20ms).
  3. Merge bằng RRF → top100.
  4. Rerank BGE cross-encoder top50 → top10 (~100ms).
  - Model đắt chỉ chạm ~50 cảnh, không quét cả kho.
- **Tiết kiệm GPU**: Scene → Shot → Keyframe (chạy model chỉ trên 1 frame đại diện/shot, giảm 10–50x); cascade model rẻ → đắt; perceptual-hash khử frame trùng; Qwen chạy 1 lần/scene (model đắt nhất ghìm sau cùng).
- **scene_embedding = 1 vector "scene document" gộp**: embed MÔ TẢ do Qwen viết bằng ngôn ngữ tự nhiên (như editor kể lại), KHÔNG embed tín hiệu thô. Công thức có trọng số: chủ thể + hành động (nhấn/lặp) + người có tên + object dịch sang lời tự nhiên + OCR chọn lọc + bối cảnh (cỡ cảnh / trong-ngoài / ngày-đêm) + tóm tắt lời nói 1–2 câu.
- **Siết nhiễu embedding**: rác = tín hiệu xuất hiện ở HẦU HẾT scene (vô-phân-biệt) HOẶC confidence thấp (sai còn tệ hơn thiếu). OCR → khử chuỗi lặp thành stopword bằng IDF toàn kho (tự học rác theo chính kho); face chỉ ghi tên khi chắc, không bịa "Person A"; bỏ object generic (person/wall ở tin tức).
- **Núm vặn nhanh↔chuẩn**: ANN ef_search; rerank CÓ ĐIỀU KIỆN (bỏ rerank nếu #1 bỏ xa #2 → latency tự co giãn); cache query hot; dồn công nặng về ingest để query rẻ.
- **BẮT BUỘC có eval set** (recall@10 / MRR) để biết chỉnh đúng hay sai.

## 5. Nguyên lý xương sống

- **TRIZ "thắng cả hai"** = tập trung công đắt vào đúng ~5% quan trọng: keyframe (GPU), rerank-50 (search), scene-document có trọng số (embedding).
- **"Dồn công về ingest để query rẻ"** — chính là cách thực hiện lời hứa "editor gõ 1 câu, 3s ra kết quả".
- Kỷ luật thu hẹp: một-đường-sạch ở sản phẩm ("chỉ tìm scene để dựng") = một vector gộp ở kỹ thuật.

## 6. Quyết định đã chốt

- Hero job cho demo đầu tiên = **Editor "cứu deadline"**.
- Dùng **1 vector "scene document" gộp** (không tách vector visual/text riêng cho search).
- Trọng tâm sản phẩm giữ ở **"tìm scene để dựng"**.
- Kiến trúc = **phễu 4 tầng** + **scene_embedding giàu-nhưng-siết-nhiễu** + **eval set**.
- Embedding có **trọng số** (chủ thể là tiêu đề, tag phụ chỉ 1 lần), cắt transcript, chunk scene đa nhịp; **HyDE** ở tầng query.

## 7. Wildcard đang park (tương lai, KHÔNG làm MVP)

- **Reframe marketing "hỏi cả kho → analytics"**: từ "search 1 cảnh" → "hỏi cả kho 1 câu, trả lời bằng số + dẫn chứng" (đếm / xếp hạng / tổng hợp toàn kho).
- Đây là **điểm khác biệt** so với Azure / AWS Rekognition — cửa đột phá tương lai, tách khỏi lõi editor.

## 8. Câu hỏi mở còn lại

- **Scale hàng chục triệu scene (C4)** chưa bàn sâu: quantization / tiered storage / lộ trình pgvector → Qdrant.
- **Query understanding** chưa chốt: LLM parse câu truy vấn vs. parser thuần.
