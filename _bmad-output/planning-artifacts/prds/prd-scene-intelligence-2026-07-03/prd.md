---
title: Scene Intelligence — PRD
status: draft
created: 2026-07-03
updated: 2026-07-03
---

# PRD: Scene Intelligence
*Working title — cần xác nhận.*

## 0. Mục đích tài liệu

PRD này dành cho PM, các bên liên quan tại đài truyền hình, và các workflow phía sau (UX, kiến trúc, epics/stories). Nó mô tả **năng lực** (capabilities) — không mô tả cách hiện thực; các lựa chọn kỹ thuật (mô hình AI, thuật toán tìm kiếm, hạ tầng) nằm ở `addendum.md` đi kèm. Tài liệu xây trên hai nguồn đã có: **intent doc** từ phiên brainstorm (`_bmad-output/brainstorming/brainstorm-scene-intelligence-2026-07-03/brainstorm-intent.md`) và **research thị trường** (`research-landscape.md` cùng thư mục). Từ vựng được neo ở §3 Glossary; features nhóm lại với FR đánh số toàn cục; giả định gắn `[ASSUMPTION]` inline và gom ở §9.

## 1. Vision

**Scene Intelligence** là hệ thống **tìm kiếm cảnh video bằng ngôn ngữ tự nhiên, chạy hoàn toàn on-premise**, dành cho phòng biên tập của đài truyền hình. Người dùng nạp video vào hệ thống; một pipeline AI tự động tách mỗi video thành các **scene**, làm giàu ngữ nghĩa từng scene (lời thoại, chữ trên hình, khuôn mặt, đối tượng, mô tả cảnh), rồi cho phép biên tập viên **gõ một câu đời thường** trên giao diện web và nhận về **đúng đoạn băng cần dùng cùng timecode** trong vài giây.

Vấn đề nó giải: kho băng của đài thường **thiếu tag**, nên biên tập viên phải tua tay hàng giờ hoặc dựa vào trí nhớ đồng nghiệp để tìm B-roll — trong khi deadline lên sóng thì cận kề. Các giải pháp hiện có hoặc là API đám mây (Azure/AWS/Google — không có UX cho biên tập, tiếng Việt yếu, không cho chạy on-prem), hoặc là MAM cloud (Moments Lab, iconik). Đài truyền hình VN cần **on-prem** (chủ quyền dữ liệu, bản quyền, kho quá lớn để đẩy lên cloud) và **tiếng Việt first-class**.

Vì sao đáng làm bây giờ: một đối thủ chuyên newsroom (**Vidrovr**) vừa rời thị trường media (2/2026), để lại khoảng trống; đồng thời **Adobe Premiere "Media Intelligence"** đã nâng kỳ vọng của biên tập viên về tìm kiếm bằng ngôn ngữ tự nhiên — nhưng chỉ trong phạm vi footage đã kéo vào project, chạy một máy, một người. Cửa mở cho một hệ thống **quy mô cả kho, dùng chung, on-prem, tiếng Việt**.

## 2. Target User

### 2.1 Jobs To Be Done

- **(Chính) Biên tập viên "cứu deadline":** *"Khi tôi đang chạy đua với giờ lên sóng, cho tôi gõ một câu đời thường và trong vài giây trả về đúng đoạn băng khiến câu chuyện 'ăn' — để tôi lấy dùng ngay mà không phải tua băng hay cầu cứu ai."* Cảm xúc lõi: sợ trễ sóng, sợ bị đánh giá kém.
- **(Phụ) Người quản lý tư liệu / thủ thư kho băng:** biến kho băng "chết" (thiếu tag, khó tra) thành kho tra cứu được, không phải gắn tag thủ công từng clip.
- **(Ngữ cảnh) Lãnh đạo phòng/đài:** cần một giải pháp **chạy trong nhà**, không phát tán tư liệu ra đám mây, chi phí dự đoán được.

### 2.2 Non-Users (v1)

- Khách hàng thương mại bên ngoài (hãng phim, marketing, an ninh) — sẽ nhắm sau khi bản nội bộ chứng minh giá trị. `[NON-GOAL for MVP]`
- Người dùng cuối xem video (khán giả) — đây là công cụ nội bộ cho người sản xuất.
- Biên tập viên làm việc hoàn toàn trong NLE mong muốn round-trip tự động ở MVP — xem §6.2.

### 2.3 Key User Journeys

- **UJ-1. Hằng tìm B-roll bão lụt trước giờ lên sóng.**
  - **Persona + ngữ cảnh:** Hằng, biên tập viên thời sự, còn ~10 phút trước bản tin, cần chèn hình minh hoạ cho tin bão số 3.
  - **Entry state:** đã đăng nhập hệ thống nội bộ trên trình duyệt, đang mở tab Scene Intelligence song song với phần mềm dựng.
  - **Path:** gõ *"phố ngập nước, xuồng cứu hộ, phóng viên đứng dưới mưa"* → hệ thống trả về lưới kết quả kèm thumbnail + timecode + tên video nguồn → Hằng rê chuột xem preview nhanh vài cảnh → chọn cảnh ưng, bấm tải đoạn clip (hoặc copy timecode).
  - **Climax:** trong vài giây, đúng đoạn ~8 giây hiện ra ở đầu danh sách — thứ trước đây phải tua 40 phút băng.
  - **Resolution:** Hằng có clip/timecode để đưa vào bản dựng, kịp lên sóng.
  - **Edge case:** nếu không có kết quả đủ tốt, hệ thống gợi ý nới lỏng bộ lọc hoặc hiển thị các cảnh "gần đúng" để Hằng tự cân nhắc.

- **UJ-2. Tuấn tìm thêm các cảnh cùng kiểu để dựng một mạch.**
  - Tuấn, biên tập viên, đã có một cảnh ưng ý; bấm **"cảnh giống cảnh này"** để hệ thống trả về các biến thể B-roll tương tự (cùng bối cảnh/không khí) trong kho, chọn nhanh vài cái ghép thành chuỗi.

- **UJ-3. Lan (thủ thư kho) nạp một đợt băng cũ và theo dõi tiến độ làm giàu.**
  - Lan chỉ hệ thống tới thư mục/ổ chứa băng, khởi động ingest theo lô, và theo dõi bảng tiến độ (đã xử lý bao nhiêu giờ, còn lại bao lâu) mà không phải can thiệp từng file.

## 3. Glossary

- **Scene** — Đơn vị nhỏ nhất có nghĩa để tìm kiếm; một đoạn video liên tục về nội dung, có timecode bắt đầu/kết thúc, thuộc về một Video nguồn. Là đối tượng trả về của tìm kiếm.
- **Shot** — Đoạn quay liên tục giữa hai lần chuyển cảnh; một Scene gồm một hoặc nhiều Shot.
- **Keyframe** — Khung hình đại diện cho một Shot, dùng để chạy các mô hình thị giác (thay vì chạy trên mọi khung hình).
- **Video (nguồn)** — Tệp video gốc được nạp vào hệ thống; chứa nhiều Scene.
- **Ingest** — Quá trình nạp Video vào hệ thống và đưa qua pipeline làm giàu.
- **Enrichment (làm giàu)** — Các bước AI trích xuất tín hiệu từ Scene: lời thoại, chữ trên hình, khuôn mặt, đối tượng, mô tả cảnh, embedding.
- **Scene Document** — Bản mô tả Scene bằng ngôn ngữ tự nhiên (do mô hình sinh), tổng hợp các tín hiệu đã làm giàu; là thứ được đem đi tạo embedding.
- **scene_embedding** — Một vector biểu diễn Scene Document, dùng cho tìm kiếm ngữ nghĩa.
- **Hybrid Search** — Tìm kiếm kết hợp lọc metadata + tìm ngữ nghĩa (vector) + tìm từ khoá (full-text), rồi xếp hạng lại.
- **Jump-to-moment** — Kết quả trả về trỏ thẳng tới timecode của Scene, không phải cả Video.
- **Editor (biên tập viên)** — Người dùng chính; tìm và lấy cảnh để dựng.
- **Eval set** — Bộ cặp *(câu truy vấn thật → Scene đúng)* dùng để đo chất lượng tìm kiếm.
- **recall@10 / MRR** — Thước đo chất lượng tìm kiếm trên Eval set (tỷ lệ có kết quả đúng trong top 10 / thứ hạng trung bình của kết quả đúng).
- **NLE** — Phần mềm dựng phi tuyến (Premiere, DaVinci Resolve).
- **Timecode** — Nhãn thời gian (giờ:phút:giây:khung) định vị vị trí trong Video.
- **B-roll** — Cảnh minh hoạ chèn vào bản tin/phóng sự.

## 4. Features

### 4.1 Ingest & Scene Pipeline (Nạp và làm giàu scene)

**Description:** Thủ thư kho hoặc biên tập viên chỉ hệ thống tới nguồn video (upload hoặc trỏ vào ổ/thư mục nội bộ). Hệ thống tự động tách mỗi Video thành Scene → Shot → Keyframe, rồi làm giàu từng Scene: chuyển lời thoại thành văn bản (tiếng Việt), nhận chữ trên hình (tiếng Việt), nhận diện khuôn mặt/đối tượng, và sinh một **Scene Document** mô tả cảnh bằng ngôn ngữ tự nhiên. Mọi thứ chạy on-premise. Pipeline ưu tiên **chất lượng tiếng Việt** và **tiết kiệm tài nguyên** để kịp làm giàu một kho hàng chục nghìn giờ. Chi tiết mô hình/thuật toán ở `addendum.md`. Realizes UJ-3.

**Functional Requirements:**

#### FR-1: Nạp video theo lô từ nguồn nội bộ
Thủ thư kho có thể nạp một hoặc nhiều Video bằng cách upload hoặc trỏ hệ thống vào một thư mục/ổ lưu trữ nội bộ.

**Consequences (testable):**
- Có thể xếp hàng ≥ 1.000 tệp trong một lệnh nạp lô và hệ thống xử lý tuần tự/song song mà không cần thao tác từng tệp.
- Các định dạng video phát sóng phổ biến được chấp nhận `[ASSUMPTION: MP4/MOV/MXF/MPEG-TS; danh sách chính xác cần xác nhận với đài]`.
- Tệp lỗi/không đọc được bị bỏ qua, ghi log, và không làm dừng cả lô.

#### FR-2: Tách Scene → Shot → Keyframe
Hệ thống tách mỗi Video thành các Scene (đơn vị tìm kiếm), mỗi Scene thành các Shot, và chọn Keyframe đại diện cho mỗi Shot.

**Consequences (testable):**
- Mỗi Scene có timecode bắt đầu/kết thúc và thuộc về đúng Video nguồn.
- Các mô hình thị giác chỉ chạy trên Keyframe, không chạy trên mọi khung hình (kiểm chứng qua log số khung được xử lý/Scene).

#### FR-3: Làm giàu tiếng Việt first-class (ASR + OCR)
Hệ thống chuyển lời thoại thành văn bản và nhận chữ trên hình với chất lượng cao cho **tiếng Việt**.

**Consequences (testable):**
- Tỷ lệ lỗi từ (WER) của ASR tiếng Việt trên tập kiểm thử tin tức đạt ngưỡng mục tiêu `[ASSUMPTION: WER ≤ 15% trên giọng đọc bản tin chuẩn; ngưỡng cần chốt]`.
- OCR đọc được chữ tiếng Việt có dấu trên lower-third/banner/biển chữ.

#### FR-4: Làm giàu thị giác (khuôn mặt, đối tượng)
Hệ thống nhận diện khuôn mặt và đối tượng trong Keyframe của mỗi Scene.

**Consequences (testable):**
- Khuôn mặt chỉ được gán tên khi độ tin cậy vượt ngưỡng và người đó đã được đăng ký; ngoài ra để "người không xác định" (không bịa danh tính).
- Đối tượng lưu kèm độ tin cậy; đối tượng phổ biến-vô-nghĩa bị lọc bớt (xem §4.4 chất lượng).

#### FR-5: Sinh Scene Document và scene_embedding
Hệ thống sinh một Scene Document (mô tả cảnh bằng ngôn ngữ tự nhiên) cho mỗi Scene và tạo một scene_embedding từ đó.

**Consequences (testable):**
- Mỗi Scene có đúng **một** scene_embedding gộp (không tách nhiều vector cho tìm kiếm — xem addendum).
- Scene Document ở dạng ngôn ngữ tự nhiên (không phải danh sách nhãn thô).

**Feature-specific NFRs:**
- **Thông lượng ingest:** hệ thống phải làm giàu nhanh hơn thời gian thực trên mỗi GPU để xử lý được backlog hàng chục nghìn giờ trong thời gian chấp nhận được `[ASSUMPTION: mục tiêu ≥ 2× realtime/GPU; phụ thuộc cấu hình phần cứng của đài — cần chốt]`.
- **Bền bỉ:** ingest có thể tạm dừng/tiếp tục; xử lý lại một Video mà không nhân đôi dữ liệu.

### 4.2 Hybrid Search (Tìm kiếm bằng ngôn ngữ tự nhiên)

**Description:** Biên tập viên gõ một câu đời thường (hoặc từ khoá) vào ô tìm kiếm trên web. Hệ thống kết hợp lọc metadata + tìm ngữ nghĩa + tìm từ khoá rồi xếp hạng lại, trả về danh sách Scene phù hợp nhất, mỗi kết quả trỏ thẳng tới timecode (jump-to-moment). Có bộ lọc để thu hẹp. Realizes UJ-1.

**Functional Requirements:**

#### FR-6: Tìm kiếm bằng ngôn ngữ tự nhiên
Biên tập viên có thể gõ một truy vấn ngôn ngữ tự nhiên và nhận về danh sách Scene xếp theo độ liên quan.

**Consequences (testable):**
- Truy vấn mô tả nội dung thị giác trả về đúng Scene **kể cả khi từ khoá không xuất hiện trong lời thoại** (ví dụ "ô tô chạy trên cầu" khớp cảnh không có chữ "ô tô" trong transcript).
- Mỗi kết quả gồm: thumbnail, Video nguồn, timecode bắt đầu/kết thúc, điểm liên quan.
- Kết quả trỏ tới timecode của Scene (jump-to-moment), không phải đầu Video.

#### FR-7: Lọc kết quả
Biên tập viên có thể lọc kết quả theo các thuộc tính có cấu trúc.

**Consequences (testable):**
- Có ít nhất các bộ lọc: cỡ cảnh (cận/trung/toàn), có mặt người (và ai nếu đã đăng ký), độ dài Scene, và "không dính logo/bug đài" `[ASSUMPTION: tập bộ lọc tối thiểu; có thể mở rộng theo phản hồi phòng biên tập]`.
- Bộ lọc kết hợp được với truy vấn ngôn ngữ tự nhiên trong cùng một lần tìm.

#### FR-8: Tìm từ khoá chính xác
Biên tập viên có thể tìm chính xác một cụm từ xuất hiện trong lời thoại hoặc chữ trên hình.

**Consequences (testable):**
- Truy vấn kiểu từ khoá (ví dụ tên riêng, "World Cup") tìm đúng Scene có cụm đó trong transcript/OCR.

**Feature-specific NFRs:**
- **Độ trễ tìm kiếm:** p95 thời gian trả kết quả ≤ ngưỡng mục tiêu `[ASSUMPTION: p95 ≤ 2s đầu-cuối trên kho mục tiêu; cần chốt]`.

### 4.3 Results & Editor Actions (Kết quả và thao tác của biên tập viên)

**Description:** Từ danh sách kết quả, biên tập viên xem trước nhanh, lấy cảnh ra để dùng, tìm thêm cảnh tương tự, và đánh dấu cảnh đã dùng. Đây là nơi "wow moment" hiện ra: từ câu gõ tới clip trong tay. Realizes UJ-1, UJ-2.

**Functional Requirements:**

#### FR-9: Xem trước Scene nhanh
Biên tập viên có thể xem trước một Scene ngay trong trình duyệt mà không cần mở phần mềm khác.

**Consequences (testable):**
- Rê/bấm vào kết quả phát preview đoạn Scene (hoặc scrub) trong ≤ 1s bắt đầu phát `[ASSUMPTION]`.

#### FR-10: Lấy cảnh ra để dùng
Biên tập viên có thể tải đoạn clip của Scene hoặc sao chép timecode để đưa vào bản dựng.

**Consequences (testable):**
- Tải về đúng đoạn Scene theo timecode (trim đúng đầu/cuối).
- Sao chép timecode (và định danh Video) ra clipboard ở định dạng dùng lại được.
- *(Round-trip NLE tự động — xuất XML/EDL/AAF + panel — là §6.2, ngoài phạm vi MVP.)*

#### FR-11: "Cảnh giống cảnh này"
Từ một Scene bất kỳ, biên tập viên có thể yêu cầu các Scene tương tự về hình ảnh/không khí.

**Consequences (testable):**
- Trả về danh sách Scene tương tự dựa trên tương đồng thị giác, khác với tìm bằng chữ. Realizes UJ-2.

#### FR-12: Đánh dấu cảnh đã dùng
Biên tập viên có thể đánh dấu một Scene là "đã dùng" để tránh lặp lại giữa các bản tin.

**Consequences (testable):**
- Scene đã đánh dấu hiển thị nhãn trực quan trong kết quả tìm kiếm sau đó.
- Có tuỳ chọn ẩn/hiện các Scene đã dùng trong kết quả.

### 4.4 Search Quality & Evaluation (Chất lượng tìm kiếm và đo lường)

**Description:** Chất lượng tìm kiếm được "mua" từ lúc ingest (Scene Document giàu nhưng siết nhiễu) và phải **đo được**, không chỉnh mò. Hệ thống có cơ chế đánh giá chất lượng tìm kiếm trên một Eval set.

**Functional Requirements:**

#### FR-13: Siết nhiễu khi làm giàu
Hệ thống loại bớt tín hiệu gây nhiễu khỏi Scene Document (tín hiệu xuất hiện ở hầu hết Scene, hoặc độ tin cậy thấp).

**Consequences (testable):**
- Chuỗi OCR/nhãn lặp ở hầu hết Scene (logo, ticker) bị hạ trọng số/loại như "stopword" theo chính kho.
- Tín hiệu độ tin cậy thấp không được đưa vào Scene Document dưới dạng khẳng định.

#### FR-14: Đo chất lượng bằng Eval set
PM/kỹ sư có thể chạy đánh giá tìm kiếm trên một Eval set và nhận về các chỉ số.

**Consequences (testable):**
- Hệ thống báo cáo recall@10 và MRR trên Eval set.
- Mỗi lần đổi công thức Scene Document/xếp hạng, có thể chạy lại và so sánh chỉ số.
- Ngưỡng chấp nhận cho MVP `[ASSUMPTION: recall@10 ≥ 0.85, MRR ≥ 0.7; cần chốt với phòng biên tập]`.

## 5. Non-Goals (Explicit)

- **Không** là nền tảng đám mây / SaaS đa khách ở MVP — thuần on-premise, một đài.
- **Không** làm round-trip NLE tự động (xuất XML/AAF/EDL + panel Premiere/Resolve) ở MVP — để phase sau.
- **Không** làm tầng analytics "hỏi cả kho" (đếm/xếp hạng/tổng hợp toàn kho) ở MVP — là wildcard tương lai. `[NOTE FOR PM: đây là điểm khác biệt mạnh vs Azure/AWS; revisit sau khi lõi editor chạy.]`
- **Không** nhận diện người nổi tiếng có sẵn (celebrity recognition), person tracking xuyên khung, nhận diện cảm xúc, live ingest ở MVP.
- **Không** phục vụ khách hàng thương mại ngoài đài ở MVP.
- **Không** thay thế MAM/hệ lưu trữ hiện có của đài — Scene Intelligence là tầng tìm kiếm/làm giàu, không phải hệ quản lý lưu trữ gốc. `[ASSUMPTION: cần xác nhận ranh giới với hệ lưu trữ hiện tại của đài.]`

## 6. MVP Scope

### 6.1 In Scope
- Ingest theo lô từ nguồn nội bộ; tách Scene→Shot→Keyframe.
- Làm giàu: ASR + OCR **tiếng Việt first-class**, khuôn mặt, đối tượng, Scene Document + scene_embedding.
- Hybrid Search web: tìm bằng ngôn ngữ tự nhiên + từ khoá + bộ lọc; jump-to-moment.
- Kết quả: thumbnail + timecode + preview nhanh; tải clip / copy timecode; "cảnh giống cảnh này"; đánh dấu đã dùng.
- Siết nhiễu khi làm giàu; Eval set + recall@10/MRR.
- Chạy hoàn toàn on-premise; ingest được kho hàng chục nghìn giờ.

### 6.2 Out of Scope for MVP
- **Round-trip NLE tự động** (XML/EDL/AAF + panel trong Premiere/Resolve) — *deferred v2*; là điểm sống-còn khi thương mại hoá nhưng bản nội bộ chỉ cần tải clip/copy timecode. `[NOTE FOR PM: emotionally load-bearing cho thương mại hoá — revisit ngay sau MVP.]`
- **Tầng analytics "hỏi cả kho"** — *deferred v2+*.
- **Scale ra nhiều đài / multi-tenant / SaaS** — *deferred*.
- **Mô hình cấp phép thương mại, pricing** — *deferred* (bản nội bộ chưa cần).
- Person tracking, celebrity recognition, emotion, live/streaming ingest — *deferred*.
- Đa ngôn ngữ ngoài Việt/Anh — *deferred*.

## 7. Success Metrics

**Primary**
- **SM-1: Thời gian tới clip.** Thời gian trung vị để biên tập viên tìm và lấy được đúng B-roll giảm còn **< 60s** (so với baseline tua tay/hỏi đồng nghiệp). Validates FR-6, FR-9, FR-10.
- **SM-2: Chất lượng tìm kiếm.** recall@10 ≥ 0.85 và MRR ≥ 0.7 trên Eval set. `[ASSUMPTION ngưỡng]` Validates FR-6, FR-13, FR-14.
- **SM-3: Tỷ lệ tìm thấy.** ≥ 80% truy vấn thật của phòng biên tập cho ra ít nhất một Scene dùng được trong top 10. Validates FR-6, FR-7.

**Secondary**
- **SM-4: Thông lượng ingest.** Làm giàu được toàn bộ kho mục tiêu trong thời gian chấp nhận được với phần cứng của đài. Validates FR-1, FR-2 (NFR ingest).
- **SM-5: Áp dụng thật.** Ít nhất một phòng biên tập dùng hệ thống cho công việc deadline thật trong giai đoạn pilot. Validates mục tiêu MVP.

**Counter-metrics (không tối ưu)**
- **SM-C1: Precision@10 không được hy sinh cho recall.** Không "nhồi" danh sách kết quả dài để tăng recall — precision@10 phải giữ ở ngưỡng chấp nhận. Counterbalances SM-2.
- **SM-C2: Chất lượng làm giàu không hy sinh cho tốc độ ingest.** Không tăng thông lượng bằng cách bỏ bớt bước làm giàu tới mức tụt recall. Counterbalances SM-4.
- **SM-C3: Độ trễ không được "làm đẹp" chỉ bằng cache.** SM-1 phải đạt cả với truy vấn mới (cache-miss). Counterbalances SM-1.

## 8. Open Questions

1. **Scale kho hàng chục nghìn giờ:** lộ trình hạ tầng tìm kiếm khi kho lớn (nén vector, tiered storage, pgvector → Qdrant) — chưa bàn sâu; cần khảo sát phần cứng thực tế của đài. *(chi tiết ở addendum §Scale)*
2. **Query understanding:** có cần một bước LLM phân tích câu truy vấn (tách bộ lọc) hay parser đơn giản là đủ cho MVP? — chưa chốt.
3. **Ranh giới với hệ lưu trữ/MAM hiện có của đài:** Scene Intelligence đọc từ đâu, lưu proxy/clip ở đâu, ai là "nguồn sự thật" cho video gốc?
4. **Đăng ký khuôn mặt:** quy trình đăng ký danh tính (chính khách, MC…) do ai làm, cập nhật thế nào?
5. **Phần cứng GPU thực tế** của đài (số GPU, đời) để chốt các ngưỡng thông lượng/độ trễ đang gắn `[ASSUMPTION]`.
6. **Định dạng video** thực tế trong kho đài (MXF? codec?) để chốt FR-1.

## 9. Assumptions Index

- §4.1 FR-1 — Định dạng nạp gồm MP4/MOV/MXF/MPEG-TS (cần xác nhận với đài).
- §4.1 NFR — Mục tiêu thông lượng ingest ≥ 2× realtime/GPU (phụ thuộc phần cứng).
- §4.1 FR-3 — Ngưỡng WER ASR tiếng Việt ≤ 15% trên bản tin chuẩn.
- §4.2 FR-7 — Tập bộ lọc tối thiểu (cỡ cảnh/mặt/độ dài/không logo) có thể mở rộng.
- §4.2 NFR — p95 độ trễ tìm kiếm ≤ 2s trên kho mục tiêu.
- §4.3 FR-9 — Preview bắt đầu phát ≤ 1s.
- §4.4 FR-14 / SM-2 — Ngưỡng recall@10 ≥ 0.85, MRR ≥ 0.7.
- §5 — Ranh giới với hệ lưu trữ/MAM hiện có của đài cần xác nhận.
