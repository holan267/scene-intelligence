---
stepsCompleted: [step-01, step-02, step-03]
inputDocuments:
  - '_bmad-output/planning-artifacts/prds/prd-scene-intelligence-2026-07-03/prd.md'
  - '_bmad-output/planning-artifacts/prds/prd-scene-intelligence-2026-07-03/addendum.md'
  - '_bmad-output/planning-artifacts/architecture/architecture-scene-intelligence-2026-07-03/ARCHITECTURE-SPINE.md'
  - '_bmad-output/planning-artifacts/architecture/architecture-scene-intelligence-2026-07-03/stack-verification.md'
---

# Scene Intelligence - Epic Breakdown

## Overview

Tài liệu này phân rã yêu cầu từ PRD và Architecture Spine của Scene Intelligence thành các epic và story khả thi để triển khai. Phạm vi: **MVP nội bộ** cho phòng biên tập đài truyền hình — on-prem, tiếng Việt first-class, kho hàng chục nghìn giờ.

## Requirements Inventory

### Functional Requirements

- **FR-1**: Nạp video theo lô từ nguồn nội bộ (upload hoặc trỏ thư mục/ổ), xếp hàng ≥1.000 tệp, bỏ qua tệp lỗi mà không dừng lô.
- **FR-2**: Tách mỗi Video thành Scene → Shot → Keyframe; mỗi Scene có timecode + thuộc Video nguồn.
- **FR-3**: Làm giàu tiếng Việt first-class — ASR (lời thoại→text) + OCR (chữ trên hình có dấu).
- **FR-4**: Làm giàu thị giác — nhận diện khuôn mặt (chỉ gán tên khi chắc + đã đăng ký) và đối tượng (kèm confidence).
- **FR-5**: Sinh Scene Document (mô tả NL) + đúng một scene_embedding gộp cho mỗi Scene.
- **FR-6**: Tìm kiếm bằng ngôn ngữ tự nhiên — trả Scene xếp theo liên quan, khớp cả nội dung thị giác không có trong lời thoại; jump-to-moment.
- **FR-7**: Lọc kết quả theo thuộc tính có cấu trúc (cỡ cảnh, có mặt ai, độ dài, không dính logo), kết hợp với truy vấn NL.
- **FR-8**: Tìm từ khoá chính xác trên transcript/OCR.
- **FR-9**: Xem trước Scene nhanh ngay trong trình duyệt.
- **FR-10**: Lấy cảnh ra để dùng — tải đoạn clip trim đúng timecode hoặc copy timecode.
- **FR-11**: "Cảnh giống cảnh này" — tìm Scene tương tự thị giác từ một Scene.
- **FR-12**: Đánh dấu Scene "đã dùng" để tránh trùng; ẩn/hiện scene đã dùng.
- **FR-13**: Siết nhiễu khi làm giàu — loại tín hiệu vô-phân-biệt (stopword theo IDF toàn kho) và confidence thấp.
- **FR-14**: Đo chất lượng tìm kiếm trên Eval set — báo cáo recall@10 và MRR, chạy lại so sánh được.

### NonFunctional Requirements

- **NFR-1** (Hiệu năng ingest): làm giàu nhanh hơn thời gian thực trên mỗi GPU (mục tiêu ≥2× realtime/GPU `[ASSUMPTION]`) để xử backlog hàng chục nghìn giờ.
- **NFR-2** (Bền bỉ ingest): tạm dừng/tiếp tục; xử lý lại một Video không nhân đôi dữ liệu.
- **NFR-3** (Độ trễ search): p95 ≤ 2s đầu-cuối trên kho mục tiêu `[ASSUMPTION]`.
- **NFR-4** (Preview): bắt đầu phát ≤ 1s `[ASSUMPTION]`.
- **NFR-5** (Chất lượng ASR): WER tiếng Việt ≤ 15% trên bản tin chuẩn `[ASSUMPTION]`.
- **NFR-6** (Chất lượng search): recall@10 ≥ 0.85, MRR ≥ 0.7 trên Eval set `[ASSUMPTION]`.
- **NFR-7** (Triển khai): on-prem thuần, air-gap được, không phụ thuộc dịch vụ cloud runtime.
- **NFR-8** (Observability): export metrics — p95 độ trễ search, thông lượng ingest, độ sâu hàng đợi, tỷ lệ job lỗi.
- **NFR-9** (Backup): Postgres (SoT) + media gốc là backup-critical; kho dẫn xuất rebuild được.

### Additional Requirements

*(Từ Architecture Spine — 22 AD, status final. Đây là các ràng buộc kỹ thuật định hình story.)*

- **Greenfield, không starter template**: khởi tạo source tree định sẵn (`pipeline/ search/ api/ models/ eval/ web/ shared/ deploy/`). → **Epic 1 Story 1** = scaffold + Docker Compose + xương sống 3 kho.
- **Triển khai**: Docker Compose trên 1 node GPU, air-gap (AD-14).
- **Xương sống 3 kho**: PostgreSQL 18 + pgvector 0.8.4 (SoT + vector MVP), **media storage = filesystem nội bộ (NAS/SAN cho kho thật, ổ local cho dev)** sau storage-port (AD-23), model servers (vLLM ≥0.11).
- **Hàng đợi bền**: Postgres-backed (Procrastinate/pgmq); job có trạng thái theo dõi được (AD-10, AD-18).
- **API**: FastAPI 0.139, prefix `/api/v1/`, envelope `{results, meta}`, cursor pagination, auth gating toàn app (AD-13).
- **Web UI**: React 19.2 + Vite 7 (SPA, không SSR).
- **Invariant định hình story**: scene_id bất biến (AD-1); single-writer/domain (AD-3); Postgres SoT, derived rebuild được (AD-4); stage idempotent ghi cột riêng (AD-5); model thị giác chỉ trên Keyframe (AD-6); một scene_embedding (AD-7); phễu search 4 tầng cố định (AD-8); Vietnamese-first cấm model English-only (AD-9); media bất biến (AD-11); timecode = ms (AD-12); derived mang doc_version freshness (AD-16); cổng hiển thị `indexed` (AD-17); clip/thumbnail chỉ qua API-auth (AD-19); eval tất định (AD-20); schema-lọc dùng chung (AD-21); backup SoT+media (AD-22); media qua storage-port trừu tượng (AD-23).
- **Cờ license (procurement, không phải story)**: YOLO26 (AGPL) + InsightFace buffalo_l (non-commercial) — rà/thay trước thương mại hoá (RT-DETR/Apache thay YOLO).

### UX Design Requirements

*Không áp dụng — UX design defer ở MVP (PRD §6.2). Web UI theo AD-13/AD-19 + conventions của spine; UX chi tiết sẽ làm sau.*

### FR Coverage Map

- **FR-1** (Nạp lô): Epic 1 — nạp video theo lô từ nguồn nội bộ
- **FR-2** (Scene→Shot→Keyframe): Epic 1 — tách cảnh
- **FR-3** (ASR/OCR tiếng Việt): Epic 1 — làm giàu Việt
- **FR-4** (Face/Object): Epic 1 — làm giàu thị giác
- **FR-5** (Scene Document + embedding): Epic 1 — sinh embedding
- **FR-6** (Tìm NL): Epic 2 — hybrid search
- **FR-7** (Lọc): Epic 2 — bộ lọc
- **FR-8** (Từ khoá): Epic 2 — full-text
- **FR-9** (Preview): Epic 3 — xem trước
- **FR-10** (Lấy clip/timecode): Epic 3 — lấy cảnh
- **FR-11** (Cảnh giống cảnh này): Epic 3 — tương tự thị giác
- **FR-12** (Đánh dấu đã dùng): Epic 3 — user-state
- **FR-13** (Siết nhiễu): Epic 1 — chất lượng làm giàu
- **FR-14** (Eval): Epic 4 — đo chất lượng

## Epic List

### Epic 1: Nền tảng & Nạp kho làm giàu
Thủ thư trỏ hệ thống vào kho nội bộ; video được tách Scene→Shot→Keyframe và làm giàu ngữ nghĩa (ASR+OCR tiếng Việt, khuôn mặt, đối tượng, Scene Document, scene_embedding), có siết nhiễu, chạy bất đồng bộ qua hàng đợi với tiến độ theo dõi được — trên nền scaffold + Docker Compose + xương sống 3 kho (Postgres/pgvector SoT, media storage filesystem nội bộ NAS/local sau storage-port, model servers). Sau epic này, kho băng trở nên "biết được" và sẵn sàng để tìm kiếm.
**FRs covered:** FR-1, FR-2, FR-3, FR-4, FR-5, FR-13
**NFRs:** NFR-1, NFR-2, NFR-5, NFR-7, NFR-8, NFR-9

### Epic 2: Tìm cảnh bằng ngôn ngữ tự nhiên
Biên tập viên gõ một câu đời thường (hoặc từ khoá) và nhận về đúng các Scene liên quan qua phễu 4 tầng cố định (SQL filter → ANN∥BM25 → RRF → rerank), lọc theo thuộc tính, jump-to-moment, chỉ trả Scene đã index đủ. Sau epic này, editor tìm được cảnh trong vài giây.
**FRs covered:** FR-6, FR-7, FR-8
**NFRs:** NFR-3

### Epic 3: Xem & lấy cảnh để dựng
Biên tập viên xem trước Scene nhanh trong trình duyệt, tải đoạn clip trim đúng timecode hoặc copy timecode (qua API cùng cổng auth), tìm "cảnh giống cảnh này", và đánh dấu cảnh đã dùng để tránh trùng. Sau epic này, editor lấy được cảnh ra dùng thật trong bản dựng.
**FRs covered:** FR-9, FR-10, FR-11, FR-12
**NFRs:** NFR-4

### Epic 4: Đo & tin cậy chất lượng tìm kiếm
Team tạo Eval set và chạy đánh giá tìm kiếm ở chế độ tất định (rerank bật, ngưỡng cố định, bỏ cache), báo cáo recall@10 và MRR, so sánh được giữa các lần đổi công thức. Sau epic này, chất lượng tìm kiếm đo được và đạt mốc thành công MVP.
**FRs covered:** FR-14
**NFRs:** NFR-6

---

## Epic 1: Nền tảng & Nạp kho làm giàu

Dựng nền on-prem và biến kho video thô thành các Scene tìm-được: nạp lô → tách cảnh → làm giàu tiếng Việt + thị giác → sinh embedding + siết nhiễu → mở cổng "indexed". Bao trùm scaffold, Docker Compose, xương sống 3 kho, hàng đợi bền. (AD-1,3,4,5,6,7,9,10,11,12,13,14,16,17,18,22)

### Story 1.1: Scaffold nền tảng & xương sống 3 kho

As a kỹ sư nền tảng,
I want một khung dự án chạy được với Docker Compose và ba kho dữ liệu (Postgres+pgvector, media storage filesystem nội bộ qua storage-port, chỗ cho model servers),
So that mọi story sau có nền on-prem, air-gap được để build lên.

**Acceptance Criteria:**

**Given** một máy có Docker và một volume media đã mount (NAS/SAN cho kho thật, ổ local cho dev),
**When** chạy `docker compose up`,
**Then** khởi động được PostgreSQL 18 (bật pgvector), media storage đọc/ghi qua **storage-port** theo media-key (không path tuyệt đối — AD-23), và API `GET /api/v1/health` trả 200
**And** source tree có đủ thư mục `pipeline/ search/ api/ models/ eval/ web/ shared/ deploy/` theo spine
**And** không có dịch vụ nào gọi ra Internet (air-gap được — NFR-7, AD-14)
**And** schema cơ sở gồm bảng `video`, `scene` tối thiểu với `scene_id` là id bất biến (UUID/content-hash — AD-1) và thời gian dạng `*_ms` (AD-12).

### Story 1.2: Nạp video theo lô qua hàng đợi có tiến độ

As a thủ thư kho,
I want trỏ hệ thống vào thư mục/ổ nội bộ (hoặc upload) để nạp một lô video và theo dõi tiến độ,
So that tôi đưa cả kho vào hệ thống mà không phải thao tác từng tệp. (FR-1, AD-10, AD-18)

**Acceptance Criteria:**

**Given** một thư mục chứa ≥1.000 video,
**When** tôi tạo một job nạp lô,
**Then** hệ thống xếp toàn bộ tệp vào hàng đợi bền (Postgres-backed) và trả `job_id`
**And** tôi query được trạng thái/tiến độ job (đã xử lý / còn lại / lỗi)
**And** tệp lỗi/không đọc được bị bỏ qua, ghi log, và không làm dừng cả lô
**And** trạng thái job chỉ do orchestrator quyết (worker báo tiến độ task của mình — AD-18)
**And** nạp lại cùng tệp không nhân đôi Video (idempotent — NFR-2, AD-5).

### Story 1.3: Tách Scene → Shot → Keyframe

As a hệ thống ingest,
I want tách mỗi Video thành Scene → Shot → Keyframe và tạo proxy/thumbnail,
So that các bước làm giàu chỉ chạy trên khung đại diện và mỗi kết quả trỏ đúng timecode. (FR-2, AD-6, AD-11, AD-12)

**Acceptance Criteria:**

**Given** một Video đã nạp,
**When** stage detect chạy,
**Then** sinh các Scene có `start_ms`/`end_ms` + Shot + một Keyframe/Shot, gắn `scene_id` bất biến
**And** video gốc trên storage nội bộ (NAS/local) không bị sửa (chỉ thêm proxy/thumbnail — AD-11)
**And** Keyframe gần-trùng bị khử bằng perceptual-hash trước khi enrich (AD-6)
**And** chạy lại stage detect trên cùng Video ánh xạ vào `scene_id` cũ, không re-mint (AD-1).

### Story 1.4: Làm giàu tiếng Việt — ASR + OCR

As a hệ thống ingest,
I want chuyển lời thoại thành văn bản và đọc chữ trên hình bằng model tiếng Việt,
So that Scene có transcript + OCR chất lượng cao cho tìm kiếm. (FR-3, AD-9, NFR-5)

**Acceptance Criteria:**

**Given** một Scene có audio và Keyframe,
**When** stage ASR (PhoWhisper-large) và OCR (VietOCR) chạy,
**Then** transcript tiếng Việt và text OCR có dấu được ghi vào **cột riêng** của Scene (không read-modify-write JSONB chung — AD-5)
**And** đường NL chỉ dùng model hỗ trợ tiếng Việt (cấm English-only — AD-9)
**And** WER ASR trên tập kiểm thử bản tin đạt ngưỡng mục tiêu `[ASSUMPTION: ≤15%]` (NFR-5)
**And** chạy lại ASR/OCR chỉ đè cột của chính nó.

### Story 1.5: Làm giàu thị giác — Khuôn mặt & Đối tượng

As a hệ thống ingest,
I want nhận diện khuôn mặt và đối tượng trên Keyframe,
So that Scene có tín hiệu người/vật để lọc và mô tả. (FR-4, AD-6, AD-11)

**Acceptance Criteria:**

**Given** một Keyframe và một registry danh tính đã đăng ký,
**When** stage face (InsightFace) và object (YOLO) chạy,
**Then** khuôn mặt chỉ được gán tên khi confidence ≥ ngưỡng **và** đã đăng ký; ngoài ra = "không xác định" (không bịa — AD-11)
**And** đối tượng lưu kèm confidence
**And** cho phép đăng ký/ cập nhật danh tính người (MC, chính khách…)
**And** kết quả ghi vào cột riêng của Scene (AD-5).

### Story 1.6: Scene Document, scene_embedding, siết nhiễu & cổng index

As a hệ thống ingest,
I want sinh Scene Document (Qwen3-VL), tạo một scene_embedding (BGE-M3), siết nhiễu, rồi mở cổng "indexed",
So that Scene trở nên tìm-được với chất lượng cao. (FR-5, FR-13, AD-4, AD-7, AD-16, AD-17)

**Acceptance Criteria:**

**Given** một Scene đã có tín hiệu ASR/OCR/face/object,
**When** stage describe → embed → index chạy,
**Then** sinh Scene Document NL và **đúng một** scene_embedding/Scene (BGE-M3 vào pgvector) + dòng FTS (AD-7)
**And** derived-artifact mang `doc_version` = checksum của Scene Document (AD-16)
**And** tín hiệu vô-phân-biệt (OCR/nhãn lặp toàn kho) bị hạ thành stopword theo IDF; confidence thấp không vào Document (FR-13)
**And** Scene chỉ chuyển `search_status = indexed` (nguyên tử) **sau khi** đã ghi xong vector + FTS (AD-17)
**And** xoá/dựng lại vector+FTS từ Postgres cho kết quả tương đương (derived rebuildable — AD-4).

### Story 1.7: Vận hành — Metrics, Backup & tính bền

As a người vận hành hệ thống,
I want metrics quan sát được, sao lưu kho critical, và ingest bền,
So that tôi tin hệ thống chạy được ở quy mô kho lớn và phục hồi được. (NFR-1, NFR-2, NFR-8, NFR-9, AD-22)

**Acceptance Criteria:**

**Given** hệ đang ingest,
**When** tôi xem bảng điều khiển/endpoint metrics,
**Then** thấy thông lượng ingest, độ sâu hàng đợi, tỷ lệ job lỗi (NFR-8)
**And** thông lượng làm giàu đạt mục tiêu `[ASSUMPTION: ≥2× realtime/GPU]` (NFR-1)
**And** worker crash → job retry, không mất việc (NFR-2, AD-18)
**And** cấu hình backup phủ **Postgres (SoT) + media gốc**; kho dẫn xuất rebuild được, không backup ngang hàng (NFR-9, AD-22).

---

## Epic 2: Tìm cảnh bằng ngôn ngữ tự nhiên

Editor gõ một câu → phễu 4 tầng cố định trả về đúng Scene đã index, kèm lọc và từ khoá. (AD-8, AD-13, AD-16, AD-17, AD-21)

### Story 2.1: Tìm ngữ nghĩa + rerank, trả envelope jump-to-moment

As a biên tập viên,
I want gõ một câu đời thường và nhận về các Scene liên quan nhất, mỗi cái trỏ đúng timecode,
So that tôi tìm được cảnh mà không cần từ khoá khớp lời thoại. (FR-6, AD-8, AD-13, AD-17)

**Acceptance Criteria:**

**Given** kho đã có Scene `indexed`,
**When** tôi gọi `POST /api/v1/search` với một câu NL,
**Then** hệ chạy vector ANN → rerank (bge-reranker-v2-m3) và trả envelope `{results:[{scene_id, video_id, start_ms, end_ms, score, thumbnail_url, highlights}], meta}` (AD-13)
**And** truy vấn mô tả thị giác trả đúng Scene kể cả khi transcript không chứa từ khoá đó
**And** chỉ trả Scene `search_status = indexed` (AD-17), không trả Scene lệch `doc_version` (AD-16)
**And** rerank có điều kiện: bỏ rerank khi #1 bỏ xa #2; p95 độ trễ ≤ ngưỡng `[ASSUMPTION: 2s]` (NFR-3).

### Story 2.2: Full-text + hợp nhất Hybrid (RRF)

As a biên tập viên,
I want tìm chính xác cụm từ trong lời thoại/OCR và được hợp nhất với kết quả ngữ nghĩa,
So that cả tên riêng lẫn ý nghĩa đều tìm ra. (FR-8, AD-8)

**Acceptance Criteria:**

**Given** kho đã index,
**When** tôi tìm một cụm từ khoá (ví dụ tên riêng, "World Cup"),
**Then** BM25/FTS trả đúng Scene có cụm đó trong transcript/OCR
**And** kết quả FTS và vector được hợp nhất bằng RRF ở **mức Scene** (một candidate/Scene trước rerank — AD-7, AD-8)
**And** thứ tự phễu là cố định: filter → (ANN ∥ FTS) → RRF → rerank.

### Story 2.3: Bộ lọc metadata theo schema dùng chung

As a biên tập viên,
I want thu hẹp kết quả theo cỡ cảnh, người, độ dài, "không dính logo",
So that tôi tới đúng loại cảnh nhanh hơn. (FR-7, AD-21)

**Acceptance Criteria:**

**Given** một truy vấn NL,
**When** tôi thêm bộ lọc,
**Then** hệ áp filter trước phễu và kết hợp được với truy vấn NL trong cùng lần tìm
**And** tập thuộc tính lọc lấy từ **một schema dùng chung** ở `shared/` mà ingest ghi và search/UI đọc cùng (AD-21)
**And** thêm một bộ lọc mới = sửa schema chung, không khai báo rời ở search hay UI.

---

## Epic 3: Xem & lấy cảnh để dựng

Editor xem trước, lấy clip/timecode qua API-auth, tìm cảnh tương tự, đánh dấu đã dùng. (AD-1, AD-3, AD-7, AD-11, AD-12, AD-19)

### Story 3.1: Xem trước Scene nhanh trong trình duyệt

As a biên tập viên,
I want xem trước một Scene ngay trên web,
So that tôi thẩm định cảnh mà không mở phần mềm khác. (FR-9, AD-19, NFR-4)

**Acceptance Criteria:**

**Given** một kết quả tìm kiếm,
**When** tôi rê/bấm vào nó,
**Then** preview đoạn Scene phát (hoặc scrub) và bắt đầu phát ≤ ngưỡng `[ASSUMPTION: 1s]` (NFR-4)
**And** media chỉ phục vụ qua API dưới cùng cổng auth (API stream/proxy, token/hết hạn — AD-19); UI không nhận đường dẫn filesystem/khoá lưu trữ thật, không truy cập storage trực tiếp.

### Story 3.2: Lấy cảnh — tải clip trim đúng timecode / copy timecode

As a biên tập viên,
I want tải đoạn clip của Scene hoặc copy timecode,
So that tôi đưa được cảnh vào bản dựng. (FR-10, AD-12, AD-19)

**Acceptance Criteria:**

**Given** một Scene ưng ý,
**When** tôi bấm tải clip,
**Then** API trim đúng đoạn theo `start_ms`/`end_ms` và trả file (trim là thao tác do API sở hữu — AD-19)
**And** tôi copy được timecode + định danh Video ra clipboard ở dạng dùng lại được
**And** không có đường lấy media vượt cổng auth.

### Story 3.3: "Cảnh giống cảnh này"

As a biên tập viên,
I want từ một Scene tìm các Scene tương tự về hình ảnh,
So that tôi gom nhanh các biến thể B-roll để dựng một mạch. (FR-11, AD-7)

**Acceptance Criteria:**

**Given** một Scene,
**When** tôi bấm "cảnh giống cảnh này",
**Then** hệ trả các Scene tương tự dựa trên **visual embedding (SigLIP2) ở collection riêng** (AD-7)
**And** đường này tách khỏi search text, không dùng scene_embedding gộp.

### Story 3.4: Đánh dấu cảnh đã dùng

As a biên tập viên,
I want đánh dấu một Scene "đã dùng" và ẩn/hiện chúng,
So that tôi tránh lặp cảnh giữa các bản tin. (FR-12, AD-1, AD-3)

**Acceptance Criteria:**

**Given** một Scene trong kết quả,
**When** tôi đánh dấu "đã dùng",
**Then** trạng thái ghi vào **user-state do API sở hữu** (single-writer — AD-3), khoá theo `scene_id` bất biến (AD-1)
**And** Scene đã dùng hiển thị nhãn trong các lần tìm sau
**And** tôi bật/tắt ẩn Scene đã dùng trong kết quả.

---

## Epic 4: Đo & tin cậy chất lượng tìm kiếm

Team tạo Eval set và đo recall@10/MRR ở chế độ tất định qua chính Search Service. (AD-15, AD-20)

### Story 4.1: Tạo & quản lý Eval set

As a PM/kỹ sư,
I want tạo và lưu bộ cặp (câu truy vấn thật → Scene đúng),
So that tôi có chuẩn để đo chất lượng tìm kiếm. (FR-14)

**Acceptance Criteria:**

**Given** kho đã index,
**When** tôi thêm một cặp truy vấn→Scene-đúng,
**Then** cặp được lưu vào Eval set và liệt kê/sửa/xoá được
**And** Eval set tham chiếu Scene bằng `scene_id` bất biến (ổn định qua re-ingest — AD-1).

### Story 4.2: Chạy đánh giá tất định & báo cáo recall@10/MRR

As a PM/kỹ sư,
I want chạy đánh giá trên Eval set và nhận chỉ số tái lập được,
So that mỗi lần đổi công thức tôi biết chất lượng lên hay xuống. (FR-14, AD-20, NFR-6)

**Acceptance Criteria:**

**Given** một Eval set,
**When** tôi chạy đánh giá,
**Then** hệ gọi **cùng** Search Service mà UI dùng (không nhánh code riêng — AD-15)
**And** chạy ở **chế độ tất định**: rerank luôn bật, ngưỡng cố định, bỏ cache (AD-20)
**And** báo cáo recall@10 và MRR; chạy lại trên cùng Eval set + index cho kết quả tái lập
**And** đạt ngưỡng mục tiêu `[ASSUMPTION: recall@10 ≥ 0.85, MRR ≥ 0.7]` (NFR-6).
