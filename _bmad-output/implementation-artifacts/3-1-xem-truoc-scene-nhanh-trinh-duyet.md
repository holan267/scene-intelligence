---
baseline_commit: 9988f8381300af65c7ddae8bca106cfe9fd6149a
---

# Story 3.1: Xem trước Scene nhanh trong trình duyệt

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a **biên tập viên**,
I want **xem trước một Scene ngay trên web (rê/bấm vào kết quả tìm kiếm)**,
so that **tôi thẩm định cảnh mà không mở phần mềm khác**.

## Scope Decisions (đã xác nhận với Lan / suy ra từ hiện trạng codebase)

**1. Auth — bỏ qua hoàn toàn cho MVP nội bộ (xác nhận qua AskUserQuestion).** AD-19 yêu cầu media chỉ phục vụ qua API "cùng cổng auth" với "token/hết hạn". Kiến trúc spine đánh dấu auth toàn app là `[ASSUMPTION: SSO/LDAP của đài — cần chốt]` (chưa chốt hạ tầng thật) và hiện KHÔNG có bất kỳ cơ chế auth nào trong codebase. Lan chọn: **không thêm token/gating ở story này** — mạng nội bộ/air-gap (NFR-7) là ranh giới bảo mật duy nhất cho MVP. Đây là nới lỏng có chủ đích so với AD-19 (đánh dấu `[ADOPTED]`, không phải `[ASSUMPTION]`) — ghi rõ vào `deferred-work.md`: auth/token thật cho media endpoint là việc riêng, cần chốt hạ tầng SSO/LDAP trước. Phần CÒN LẠI của AD-19 (UI không nhận path filesystem thật, không truy cập storage trực tiếp, media chỉ qua API) **vẫn áp dụng đầy đủ** — chỉ bỏ phần token/auth.

**2. `web/` hiện chỉ là stub.** `web/README.md`: *"Stub ở Story 1.1 — dựng thật ở Epic 3."* Story này là story ĐẦU TIÊN dựng SPA thật (React 19.2 + Vite 7, xem `stack-verification.md` dòng 21). Không có code React/Vite nào tồn tại — phải scaffold từ đầu.

**3. Không có "thumbnail" hay "proxy" riêng — dùng lại Keyframe.** Story 1.1's AC nhắc "sinh proxy/thumbnail" nhưng grep toàn bộ `pipeline/` không ra kết quả nào cho "thumbnail"/"proxy" — chưa từng implement. Artifact gần nhất là `Shot.keyframe_key` (ảnh khung đại diện, Story 1.3). Quyết định: **dùng keyframe của Shot đầu tiên (start_ms nhỏ nhất) trong Scene làm thumbnail** — không tạo thêm pipeline sinh thumbnail riêng (ngoài phạm vi story này).

**4. Không có "proxy" video riêng — stream trực tiếp từ `Video.source_key` (bản gốc, bất biến — AD-11).** Preview phát/scrub đọc thẳng từ media gốc qua storage-port + HTTP Range (browser tự seek đúng đoạn `start_ms`/`end_ms` qua `<video>` timecode fragment). **Giới hạn đã biết**: định dạng nạp gồm MP4/MOV/MXF/MPEG-TS (PRD §4.1 FR-1) nhưng trình duyệt HTML5 `<video>` chỉ phát được codec/container nó hỗ trợ (thường H.264/AAC trong MP4) — MOV/MXF/MPEG-TS có thể KHÔNG phát được trực tiếp. Transcode sang proxy web-compatible là việc riêng (ngoài phạm vi, cùng gap với "proxy" chưa từng implement ở mục 3) — ghi vào `deferred-work.md`.

**5. Frontend test tooling — không giới thiệu framework test JS mới ở story này.** Dự án hiện chỉ có kỷ luật test Python (pytest). Bar chấp nhận cho phần frontend ở story này là `npm run build` chạy sạch (type-check + bundle) — KHÔNG thêm Vitest/RTL/Playwright. Quyết định component-test framework cho `web/` là việc riêng của Epic 3 (nhiều story sau sẽ dùng), không quyết định vội ở story đầu tiên.

## Acceptance Criteria

1. **Given** một Scene có ≥1 Shot với `keyframe_key`, **When** gọi `GET /api/v1/scenes/{scene_id}/thumbnail`, **Then** API trả về ảnh keyframe của Shot có `start_ms` nhỏ nhất thuộc Scene đó, đọc qua storage-port (`storage.get`), KHÔNG lộ path filesystem thật trong response — [Source: FR-9, AD-19, AD-23].
2. **Given** `scene_id` không tồn tại, HOẶC Scene tồn tại nhưng không có Shot nào, HOẶC Shot có nhưng `keyframe_key IS NULL`, **When** gọi endpoint thumbnail, **Then** trả `404` rõ ràng (không phải `500`/crash) — [Source: robustness].
3. **Given** một Video đã nạp (`Video.source_key`), **When** gọi `GET /api/v1/videos/{video_id}/stream`, **Then** API stream nội dung video gốc qua storage-port (`storage.local_path` + Starlette `FileResponse`, hỗ trợ HTTP Range — `Accept-Ranges: bytes`, trả `206 Partial Content` khi có header `Range`) — KHÔNG buộc tải toàn bộ file trước khi phát được — [Source: FR-9, NFR-4, AD-19].
4. **Given** `video_id` không tồn tại, **When** gọi endpoint stream, **Then** trả `404` — [Source: robustness].
5. **Given** UI (`web/`) đã dựng thật (React 19.2 + Vite 7, thay thế stub Story 1.1), **When** biên tập viên rê/bấm vào một kết quả tìm kiếm (từ `POST /api/v1/search`, envelope có `thumbnail_url`, `video_id`, `start_ms`, `end_ms`), **Then** UI hiển thị thumbnail (`<img src={thumbnail_url}>`) và khi rê/bấm phát preview bằng `<video>` trỏ tới `/api/v1/videos/{video_id}/stream` với thời điểm bắt đầu đúng `start_ms` (dùng timecode fragment hoặc set `currentTime` sau `loadedmetadata`) — [Source: FR-9, NFR-4 `[ASSUMPTION: bắt đầu phát ≤1s]` — xác minh thủ công, không unit-test được thời gian thật].
6. **Given** quyết định scope đã xác nhận (không auth), **When** media được serve, **Then** UI KHÔNG BAO GIỜ nhận đường dẫn filesystem/khoá lưu trữ thật (`media_key`/`source_key`/`keyframe_key`) qua bất kỳ response nào — chỉ nhận URL API tương đối (`/api/v1/...`) — [Source: AD-19 (phần còn lại sau khi bỏ token)].

## Tasks / Subtasks

- [x] **Task 1 — `api/routes_media.py` (module mới): `GET /api/v1/scenes/{scene_id}/thumbnail`** (AC: #1, #2, #6):
  - [x] Query `Scene` theo `scene_id` — không tồn tại → `HTTPException(404)`.
  - [x] Query `Shot` theo `scene_id`, `ORDER BY start_ms ASC, shot_id ASC LIMIT 1` (tie-break `shot_id` cho tất định khi nhiều Shot cùng `start_ms`) — không có Shot nào, HOẶC `Shot.keyframe_key IS NULL` → `HTTPException(404)`.
  - [x] `storage = build_storage()` (theo đúng pattern `api/main.py::storage_health` — gọi trực tiếp, KHÔNG qua `Depends`), `data = storage.get(shot.keyframe_key)` → `Response(content=data, media_type="image/jpeg")` — `[ASSUMPTION]` keyframe luôn JPEG (đúng theo Story 1.3 `pipeline/detect.py` extractor, chưa có định dạng khác).
  - [x] KHÔNG trả `keyframe_key`/path filesystem thật trong bất kỳ header/body nào (AC #6).

- [x] **Task 2 — `api/routes_media.py`: `GET /api/v1/videos/{video_id}/stream`** (AC: #3, #4, #6):
  - [x] Query `Video` theo `video_id` — không tồn tại → `HTTPException(404)`.
  - [x] `path = storage.local_path(video.source_key)` (escape hatch có sẵn từ Story 1.1, đúng mục đích thiết kế — xem `shared/storage.py` docstring "cho phép thư viện decode video nhận đường dẫn mà vẫn đi qua port").
  - [x] `media_type = mimetypes.guess_type(video.source_key)[0] or "application/octet-stream"`.
  - [x] Trả `FileResponse(path, media_type=media_type)` — Starlette `FileResponse` tự xử lý `Range` header (206 partial content, `Content-Range`, `Accept-Ranges: bytes`) khi phục vụ từ path filesystem thật — KHÔNG tự viết logic Range thủ công.
  - [x] Ghi chú docstring: browser chỉ phát được codec/container nó hỗ trợ (thường H.264/AAC trong MP4) — MOV/MXF/MPEG-TS nguồn có thể không phát trực tiếp được (Dev Notes, deferred).

- [x] **Task 3 — Wire router** (AC: #1-#4): `api/main.py` — `from api.routes_media import router as media_router`, `app.include_router(media_router)`, theo đúng pattern 3 router hiện có (`ingest_router`, `metrics_router`, `search_router`).

- [x] **Task 4 — Test backend** (AC: #1-#4, #6): `tests/test_routes_media.py` (mới, 7 test) — dùng `httpx.AsyncClient` + `ASGITransport` (KHÔNG `starlette.testclient.TestClient`, xem Debug Log lý do event-loop) kết hợp DB sqlite thật (`async_session`) + storage filesystem thật trên `tmp_path`:
  - [x] Override `get_session` (FastAPI `app.dependency_overrides[get_session] = ...`) bằng một async generator khác cùng signature, trỏ session sqlite in-memory (fixture `async_session` có sẵn) thay vì engine Postgres thật.
  - [x] Ghi một file JPEG giả (vài byte bất kỳ, không cần ảnh thật hợp lệ — endpoint chỉ đọc/trả bytes, không decode) vào `tmp_path` qua `FilesystemStorage(tmp_path)`, seed `Video`+`Scene`+`Shot(keyframe_key=...)` vào DB.
  - [x] Test thumbnail: 200 + đúng bytes đã ghi (của Shot start_ms nhỏ nhất, xác nhận KHÔNG theo thứ tự insert); 404 khi `scene_id` sai; 404 khi Scene không có Shot; 404 khi Shot có nhưng `keyframe_key=None`.
  - [x] Ghi một file video giả (vài byte bất kỳ, không cần video thật hợp lệ — Starlette `FileResponse` không decode nội dung) vào `tmp_path`, seed `Video(source_key=...)`.
  - [x] Test stream: request KHÔNG có header `Range` → 200 + toàn bộ bytes + `Accept-Ranges: bytes`; request CÓ header `Range: bytes=0-3` → `206` + đúng 4 byte đầu + header `Content-Range` đúng (`bytes 0-3/10`); 404 khi `video_id` sai.
  - [x] Test cả hai response KHÔNG chứa `keyframe_key`/`source_key`/path filesystem thật trong header hay body (AC #6); test stream KHÔNG có header `Content-Disposition` (không ép download, không truyền `filename=`).

- [x] **Task 5 — Scaffold `web/` (React 19.2 + Vite 7)** (AC: #5): thay thế stub, dựng SPA thật:
  - [x] Scaffold bằng `npm create vite@7 . -- --template react-ts` (chạy trong `web/`, non-interactive) — giữ lại `README.md` hiện có (cập nhật nội dung, không xoá lịch sử ghi chú AD). Nếu scaffolder từ chối vì thư mục "không rỗng" (chỉ có `README.md`): tạm di chuyển `README.md` ra ngoài, scaffold, rồi chuyển lại + merge nội dung. React scaffold mặc định ra `19.1.1` — pin lại `^19.2.0` trong `package.json` + `npm install` để khớp đúng `stack-verification.md` (cài được `19.2.7`).
  - [x] `vite.config.ts`: dev server proxy `/api` → `http://localhost:8000` (backend chạy qua `uvicorn`/docker-compose) — UI gọi `fetch('/api/v1/search', ...)` tương đối, không hardcode origin.
  - [x] `src/App.tsx` (hoặc component tương đương): ô nhập câu truy vấn → `POST /api/v1/search` → render danh sách kết quả — mỗi kết quả: `<img src={result.thumbnail_url}>` (thumbnail) + khi rê/bấm (`onMouseEnter`/`onClick`) hiện `<video>` `src={\`/api/v1/videos/${result.video_id}/stream#t=${startSec},${endSec}\`}` (đổi `start_ms`/`end_ms` sang giây: `ms/1000`) — timecode fragment (`#t=start,end`) là cơ chế HTML5 chuẩn để browser seek + giới hạn phát trong khoảng, KHÔNG cần logic JS thủ công để cắt đoạn.
  - [x] KHÔNG implement lọc (`filters`, Story 2.3), tải clip (Story 3.2), "cảnh giống cảnh này" (Story 3.3), đánh dấu đã dùng (Story 3.4) — ngoài phạm vi story này, chỉ tìm kiếm NL + preview.

- [x] **Task 6 — Xác nhận build frontend** (AC: #5): `npm run build` trong `web/` chạy sạch (type-check qua `tsc` + bundle qua Vite) — đây là bar chấp nhận DUY NHẤT cho frontend ở story này (xem Scope Decision #5) — KHÔNG thêm Vitest/React Testing Library/Playwright.

- [x] **Task 7 — Cập nhật `web/README.md` + `deferred-work.md`** (tài liệu):
  - [x] `web/README.md`: hướng dẫn dev (`npm install && npm run dev`, cần backend chạy song song ở `:8000`), ghi rõ đã dựng thật (không còn "Stub").
  - [x] `deferred-work.md`: 2 entry mới — (a) auth/token thật cho media endpoint (AD-19 phần token) cần chốt hạ tầng SSO/LDAP trước; (b) transcode video nguồn (MOV/MXF/MPEG-TS) sang proxy web-compatible (H.264/AAC MP4) cho browser phát được — hiện stream trực tiếp bản gốc, chỉ đảm bảo phát được với nguồn đã là MP4/H.264.

### Review Findings

- [x] [Review][Patch] Thiếu xử lý khi `Scene`/`Video` có row trong DB nhưng file tương ứng đã mất trên disk — cả `scene_thumbnail` (`storage.get(shot.keyframe_key)`) lẫn `video_stream` (`storage.local_path`/`FileResponse`) đều raise exception không bắt → `500` thay vì `404` đã test cho trường hợp "row không tồn tại" [api/routes_media.py] — **Fixed**: thêm `storage.exists()` check trước khi đọc/serve, raise `HTTPException(404)`. Verify lại thật qua docker (rebuild+curl) → đúng 404.
- [x] [Review][Patch] `shot.keyframe_key = ""` (chuỗi rỗng, không phải `None`) lọt qua check `is None` → `storage._resolve` raise `ValueError("media_key rỗng")` → `500` thay vì `404` [api/routes_media.py] — **Fixed**: đổi điều kiện thành `not shot.keyframe_key` (bắt cả `None` lẫn `""`).
- [x] [Review][Patch] `web/package-lock.json` chưa thực sự nằm trong diff/staged dù File List của story liệt kê là file mới — ảnh hưởng tái lập bản build (pin React 19.2.7) [web/package-lock.json] — **Fixed**: sẽ `git add` cùng các file khác khi commit story (không phải lỗi code, chỉ là sai sót staging).
- [x] [Review][Patch] Task 2 hứa ghi chú docstring về giới hạn codec (MOV/MXF không phát được trực tiếp) nhưng docstring thật của `video_stream` không có dòng đó [api/routes_media.py] — **Fixed**: thêm đoạn "Giới hạn đã biết" vào docstring.
- [x] [Review][Patch] Task 5 hứa `onClick` (rê/bấm) nhưng code chỉ có `onMouseEnter`/`onMouseLeave` — thiếu trigger cho thiết bị cảm ứng (không có hover) [web/src/App.tsx] — **Fixed**: thêm `onClick={() => togglePreview(...)}` (bật/tắt preview).
- [x] [Review][Patch] `handleSearch` không có `AbortController`/guard thứ tự request — response chậm của một query cũ có thể ghi đè kết quả của query mới hơn (race condition) [web/src/App.tsx] — **Fixed**: thêm `useRef` đếm `requestId`, chỉ áp dụng kết quả nếu vẫn là request mới nhất.
- [x] [Review][Patch] `<img>`/`<video>` không có `onError` — khi thumbnail/stream 404 (có test kỹ ở backend), UI chỉ hiện ảnh vỡ/video đen im lặng, không có fallback [web/src/App.tsx] — **Fixed**: `<video onError>` quay lại thumbnail; `<img onError>` ẩn ảnh vỡ (`visibility: hidden`).
- [x] [Review][Patch] Test `assert b"v1/keyframes" not in resp.content` là no-op (kiểm tra bytes JPEG cho một chuỗi không bao giờ xuất hiện trong đó) — dressed up như AC #6 check nhưng không kiểm tra gì thật; assertion header ngay bên dưới mới là check thật [tests/test_routes_media.py] — **Fixed**: xoá assertion vô nghĩa, giữ lại check header thật.
- [x] [Review][Patch] `<title>` trang vẫn là mặc định Vite `"Vite + React + TS"`, chưa đổi thành tên sản phẩm [web/index.html] — **Fixed**: đổi thành `"Scene Intelligence"`.
- [x] [Review][Patch] `<video>` preview thiếu `playsInline` — mobile Safari sẽ ép fullscreen thay vì phát inline trong hover preview [web/src/App.tsx] — **Fixed**: thêm attribute `playsInline`.
- [x] [Review][Defer] `storage.get()` (đọc bytes keyframe) là lời gọi đồng bộ (sync) trong route handler `async def` — có thể chặn event loop dưới tải cao [api/routes_media.py] — deferred, ảnh hưởng nhỏ ở quy mô MVP (file JPEG nhỏ), cần thiết kế `run_in_threadpool` cẩn thận hơn là patch phản xạ.
- [x] [Review][Defer] Không có `Cache-Control`/`ETag`/`Last-Modified` trên response thumbnail/stream — mỗi lần render lại grid kết quả đều tải lại toàn bộ media từ disk [api/routes_media.py] — deferred, tối ưu hiệu năng cần thiết kế cache-invalidation riêng (khi re-ingest/re-detect).
- [x] [Review][Defer] Conditional rendering unmount/remount toàn bộ `<img>`/`<video>` mỗi lần hover in/out, không preload — di chuột nhanh qua nhiều kết quả có thể chồng nhiều video đang load cùng lúc [web/src/App.tsx] — deferred, cần thiết kế lại luồng tương tác (preload/giữ mount), lớn hơn phạm vi 1 patch.

## Dev Notes

- **`build_storage()`/`get_settings()` gọi trực tiếp, KHÔNG qua `Depends`** — đúng pattern đã có ở `api/main.py::storage_health` (không phải pattern mới); giữ nhất quán, không tự chế dependency-injection layer mới cho storage.
- **`storage.local_path()` là escape hatch có chủ đích** (docstring `shared/storage.py`: *"cho phép thư viện decode video (cv2/scenedetect) nhận đường dẫn mà vẫn đi qua port"*) — dùng đúng mục đích thiết kế cho `FileResponse`, KHÔNG phải vi phạm storage-port abstraction. Khi đổi sang S3-compat adapter sau này (AD-23), endpoint stream này là nơi DUY NHẤT cần đổi cách phục vụ (stream ra temp thay vì path thật) — ghi chú trong code.
- **KHÔNG tự viết logic HTTP Range thủ công** — Starlette `FileResponse` (đã là dependency có sẵn qua FastAPI, không phải thư viện mới) tự xử lý đúng chuẩn khi nhận path filesystem thật + có `stat()` — đây là lý do Task 2 dùng path thật (`local_path`) thay vì đọc bytes qua `storage.get()` (sẽ mất khả năng Range tự động của Starlette).
- **KHÔNG truyền `filename=` vào `FileResponse`** ở endpoint stream — mặc định `content_disposition_type` của Starlette khi có `filename` là `"attachment"`, sẽ ép trình duyệt TẢI XUỐNG thay vì phát inline trong `<video>` (phá AC #5). Không truyền `filename` → không có header `Content-Disposition` → phát inline bình thường.
- **`tests/conftest.py::client` KHÔNG đủ cho test route mới** — fixture đó chỉ override `db_health`/`storage_health` (health check giả), KHÔNG có `get_session`/storage thật để route thumbnail/stream đọc dữ liệu. Task 4 phải tự dựng fixture riêng trong `tests/test_routes_media.py`, KHÔNG sửa `client`/`async_session` chung ở `conftest.py` (tránh phá test hiện có dùng chúng).
- **Không có tiền lệ test file thật (image/video bytes) trong repo** — các test hiện có (`tests/test_storage.py` nếu có, `tests/test_ingest.py`…) test logic, không test serving file thật qua HTTP. Dùng `tmp_path` (pytest fixture built-in) + `FilesystemStorage(tmp_path)` trực tiếp (không qua `get_settings()`/env) để cô lập hoàn toàn, không đụng `MEDIA_ROOT` thật.
- **`web/` KHÔNG có code nào tồn tại ngoài `README.md`** — đây là lần đầu tiên thư mục này có source thật. Sau khi scaffold bằng `npm create vite`, sẽ có `package.json`, `tsconfig*.json`, `vite.config.ts`, `src/`, `public/`, `.gitignore` (Vite tự sinh, đã có `node_modules/`) — review kỹ `.gitignore` sinh ra để KHÔNG commit `node_modules/`.
- **NFR-4 (`≤1s` bắt đầu phát) không unit-test được** — phụ thuộc network/disk/hardware thật, cùng cách xử lý các `[ASSUMPTION]` khác đã có tiền lệ (WER Story 1.4, throughput Story 1.7) — chỉ note là cần xác minh thủ công khi có hạ tầng thật, không viết test giả định thời gian.
- **Thumbnail luôn từ Shot ĐẦU TIÊN của Scene** — không phải Keyframe "đại diện nhất"/"rõ nét nhất" (không có tín hiệu đó); đơn giản nhất, tất định, đủ cho MVP. Nếu sau này muốn chọn khung đẹp hơn, đó là cải tiến riêng ngoài phạm vi.
- **Video stream endpoint đọc TRỰC TIẾP `Video.source_key` (bản gốc, bất biến — AD-11)** — không có proxy nén sẵn. Nếu file gốc rất lớn (hàng chục GB), Starlette `FileResponse` + Range vẫn hoạt động đúng (chỉ đọc phần byte trình duyệt yêu cầu, không load cả file vào RAM) — không cần lo về memory, nhưng KHÔNG cải thiện được tốc độ decode nếu codec nguồn nặng (đó là giới hạn transcode đã ghi ở Scope Decision #4/Task 7).
- **Không đụng `pipeline/`, không migration mới, không sửa `shared/models.py`** — chỉ đọc dữ liệu Epic 1 đã ghi sẵn (`Video.source_key`, `Shot.keyframe_key`).

### Project Structure Notes

- **File mới (backend)**: `api/routes_media.py`, `tests/test_routes_media.py`.
- **File sửa (backend)**: `api/main.py` (wire router mới), `_bmad-output/implementation-artifacts/deferred-work.md` (2 entry mới).
- **File mới (frontend, scaffold Vite)**: toàn bộ `web/` ngoài `README.md` hiện có — `package.json`, `vite.config.ts`, `tsconfig*.json`, `index.html`, `src/main.tsx`, `src/App.tsx` (hoặc cấu trúc component do Vite template sinh + chỉnh sửa theo Task 5), `.gitignore` (Vite tự sinh).
- **File sửa (frontend)**: `web/README.md`.
- **Không migration mới** — không thêm cột/bảng DB.
- Backend endpoint mới nằm ở `api/routes_media.py`, KHÔNG gộp vào `api/routes_search.py` (search vs media-serving là hai mối quan tâm khác nhau, đúng convention tách file theo domain đã có — `routes_ingest.py`, `routes_search.py`, `routes_metrics.py`).

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story-3.1]
- [Source: _bmad-output/planning-artifacts/architecture/architecture-scene-intelligence-2026-07-03/ARCHITECTURE-SPINE.md#AD-19] (dòng 149-152: media chỉ qua API cùng auth, stream/proxy, UI không nhận path thật) + #AD-23 (dòng 169-172: storage-port, `local_path` escape hatch cho decoder) + #AD-11 (dòng 109-112: media gốc bất biến) + dòng 182 (`auth = đăng nhập nội bộ gating toàn app [ASSUMPTION: SSO/LDAP của đài — cần chốt]`)
- [Source: _bmad-output/planning-artifacts/architecture/architecture-scene-intelligence-2026-07-03/stack-verification.md#L21] (`React 19.2 + Vite 7`, SPA nội bộ + video HTML5, không SSR)
- [Source: _bmad-output/planning-artifacts/prds/prd-scene-intelligence-2026-07-03/prd.md#FR-9] (preview Scene nhanh trong trình duyệt) + `#NFR-4` (bắt đầu phát ≤1s `[ASSUMPTION]`) + `#FR-1` (định dạng nạp MP4/MOV/MXF/MPEG-TS)
- [Source: shared/storage.py] (`StoragePort`, `FilesystemStorage`, `local_path()` escape hatch cho decoder)
- [Source: shared/models.py#L22-33,85-97] (`Video.source_key`, `Shot.scene_id/start_ms/keyframe_key`)
- [Source: search/rank.py#L59-77] (`build_envelope` đã sinh `thumbnail_url = f"/api/v1/scenes/{scene_id}/thumbnail"` từ Story 2.1, comment "Story 3.1 mới phục vụ thật" — endpoint này CHÍNH LÀ điều đó)
- [Source: api/main.py] (pattern `build_storage()`/`get_settings()` gọi trực tiếp không qua `Depends`, cách wire router)
- [Source: api/routes_ingest.py, api/routes_search.py] (convention route file theo domain, response qua `api/envelope.py::ok`)
- [Source: web/README.md] ("Stub ở Story 1.1 — dựng thật ở Epic 3" — chính là story này)
- [Source: tests/conftest.py] (`client` fixture hiện có KHÔNG đủ cho route DB/storage thật — cần fixture riêng ở Task 4)

## Dev Agent Record

### Agent Model Used

claude-sonnet-5 (BMad dev-story)

### Debug Log References

- `uv run pytest tests/test_routes_media.py -q` (RED trước khi tạo `api/routes_media.py`) → `ModuleNotFoundError: No module named 'api.routes_media'` — xác nhận đúng thất bại trước khi implement.
- `uv run pytest tests/test_routes_media.py -q` (sau khi implement Task 1-3) → **7 passed** ngay lần đầu (thumbnail 4 test, stream 3 test) — thiết kế `httpx.AsyncClient` + `ASGITransport` (thay vì `starlette.testclient.TestClient`) chạy đúng trong cùng event loop với fixture `async_session` (sqlite in-memory `StaticPool`), tránh rủi ro cross-loop của `TestClient` (chạy qua portal thread riêng).
- `uv run pytest -q` (toàn bộ) → **148 passed** (141 trước + 7 mới). `uv run ruff check` → sạch.
- `npm create vite@7 . -- --template react-ts` scaffold ra React `19.1.1` — pin lại `^19.2.0` trong `package.json` + `npm install` → cài được `19.2.7`, khớp `stack-verification.md`.
- `npm run build` (Task 6, bar chấp nhận DUY NHẤT cho frontend) → `tsc -b` + `vite build` sạch, bundle 194.60 kB (gzip 61.36 kB).
- **Live E2E verification (không chỉ dựa vào unit test)**: phát hiện docker-compose stack (`postgres`/`api`/`worker`) đã chạy sẵn 45h trên máy dev. Rebuild image `api` (`docker compose build api` + `up -d api`) → xác nhận 2 route mới xuất hiện đúng trong `/openapi.json` thật. Insert tạm 1 Scene + 1 Shot (kèm keyframe giả) tham chiếu Video thật đã ingest sẵn (`test/test.mxf`, 14,667,324 bytes) → `curl` thật:
  - Thumbnail: `200`, đúng 47 byte đã ghi, `content-type: image/jpeg`.
  - Thumbnail scene lạ: `404`.
  - Stream không Range: `200`, đúng `14667324` bytes (khớp size file thật), `Accept-Ranges: bytes`.
  - Stream có `Range: bytes=0-99`: `206`, đúng 100 byte, `Content-Range: bytes 0-99/14667324`.
  - Stream video lạ: `404`.
  - Dọn dữ liệu test tạm ngay sau khi verify (DELETE Scene/Shot + xoá file keyframe giả) — không để lại rác trong DB/media thật.
- **Live frontend verification**: chạy `npm run dev` (Vite, `:5173`), dùng Playwright headless Chromium (cài tạm ở thư mục scratch, KHÔNG thêm vào `web/package.json` — giữ đúng quyết định "không giới thiệu JS test framework mới") điều khiển trình duyệt thật: trang tải đúng (tiêu đề "Scene Intelligence", ô nhập + nút Tìm), gõ query + submit → fetch thật qua Vite proxy tới backend `:8000` thật → backend trả `502` (model server embed/rerank KHÔNG chạy trong môi trường dev này) → UI hiển thị đúng "Tìm kiếm lỗi (502)", không crash, `console --errors` chỉ có đúng 1 dòng network 502 (không có JS exception). **Giới hạn đã biết**: không verify được luồng preview đầy đủ (thumbnail thật trong kết quả search + video phát khi hover) vì không có model server embed/rerank chạy trong sandbox — phần backend serving (thumbnail/stream) đã verify độc lập & đầy đủ qua curl thật ở trên; phần UI rendering kết quả + preview chỉ verify qua code review + build sạch, chưa qua browser thật với dữ liệu search thật.
- **Code review (10 patch)**: `uv run pytest tests/test_routes_media.py -q` (RED trước khi sửa `api/routes_media.py`) → 3 test mới fail (`assert 404 == 500`/`RuntimeError` từ `FileResponse`) — xác nhận đúng thất bại. Sau khi thêm `storage.exists()` check + đổi `is None` → `not shot.keyframe_key` → **10 passed**. `uv run pytest -q` (toàn bộ) → **151 passed** (148 + 3 mới). `uv run ruff check` → sạch. `npm run build` sau patch frontend (onClick/race-guard/onError/playsInline/title) → sạch, bundle 194.84 kB (gzip 61.45 kB). `npm run lint` → sạch (chưa từng chạy trước đó, giờ verify sạch). **Live re-verification qua docker thật**: rebuild + restart `api` container, insert Scene/Shot với `keyframe_key` trỏ file không tồn tại + Video với `source_key` không tồn tại → `curl` xác nhận cả hai trả đúng `404` (trước patch sẽ là `500`) — dọn dữ liệu test ngay sau khi verify.

### Completion Notes List

- **Task 1**: `api/routes_media.py::scene_thumbnail` — query Scene (404 nếu không có) → query Shot `ORDER BY start_ms ASC, shot_id ASC LIMIT 1` (404 nếu không có Shot/không có keyframe_key) → `storage.get()` → `Response(media_type="image/jpeg")`.
- **Task 2**: `api/routes_media.py::video_stream` — query Video (404 nếu không có) → `storage.local_path()` + `FileResponse` (Range tự động qua Starlette, không tự viết logic) — KHÔNG truyền `filename=` (tránh ép download).
- **Task 3**: Wire `media_router` vào `api/main.py`, cùng vị trí với 3 router hiện có.
- **Task 4**: `tests/test_routes_media.py` (mới, 7 test) — `httpx.AsyncClient`/`ASGITransport` thay `TestClient` để tránh cross-event-loop với sqlite `StaticPool`; monkeypatch `routes_media_module.build_storage` trỏ `FilesystemStorage(tmp_path)`.
- **Task 5**: Scaffold `web/` bằng `npm create vite@7 . -- --template react-ts`, pin React `^19.2.0`; `vite.config.ts` proxy `/api` → `:8000`; `src/App.tsx` — form tìm kiếm + grid kết quả (thumbnail mặc định, video preview khi hover qua timecode fragment `#t=start,end`).
- **Task 6**: `npm run build` sạch — bar chấp nhận frontend, không thêm Vitest/RTL/Playwright vào dependencies dự án (Playwright chỉ dùng tạm ở thư mục scratch ngoài repo để tự verify, xem Debug Log).
- **Task 7**: `web/README.md` cập nhật (hướng dẫn dev/build, không còn "Stub"); `deferred-work.md` thêm 2 entry (auth/token thật cho media endpoint; transcode video nguồn sang proxy web-compatible).
- AC #1-#6 đều thoả: #1/#2 test thuần qua `tests/test_routes_media.py` + verify lại bằng curl thật; #3/#4 test Range + verify curl thật; #5 verify qua Playwright browser thật (giới hạn: không có dữ liệu search thật do thiếu model server); #6 test + curl thật xác nhận không header/body nào chứa media-key/path gốc.
- Không đụng `pipeline/`, không migration mới, không sửa `shared/models.py` — đúng phạm vi đã xác nhận.
- **Code review (10 patch áp dụng)**: (1)+(2) `storage.exists()` check trước khi serve thumbnail/stream → 404 sạch khi file mất trên disk hoặc `keyframe_key` rỗng; verify lại thật qua docker (rebuild + curl) → đúng 404 thay vì 500 trước đó; (3) `web/package-lock.json` sẽ được `git add` khi commit; (4) thêm ghi chú giới hạn codec vào docstring `video_stream`; (5) thêm `onClick` toggle preview; (6) thêm guard thứ tự request (`useRef` counter) chống race condition; (7) thêm `onError` cho `<img>`/`<video>`; (8) xoá assertion no-op trong test; (9) đổi `<title>` thành "Scene Intelligence"; (10) thêm `playsInline` cho `<video>`. 3 finding defer (blocking sync I/O, thiếu cache header, unmount/remount preview) ghi vào `deferred-work.md`. 151/151 test pass, `npm run build`/`npm run lint` sạch.

### File List

- **Mới (backend)**: `api/routes_media.py`, `tests/test_routes_media.py`
- **Sửa (backend)**: `api/main.py` (wire `media_router`), `_bmad-output/implementation-artifacts/deferred-work.md` (5 entry mới: 2 từ story creation + 3 từ code review), `_bmad-output/implementation-artifacts/sprint-status.yaml` (status)
- **Mới (frontend, scaffold Vite + React 19.2)**: `web/package.json`, `web/package-lock.json`, `web/vite.config.ts`, `web/tsconfig.json`, `web/tsconfig.app.json`, `web/tsconfig.node.json`, `web/index.html`, `web/eslint.config.js`, `web/.gitignore`, `web/public/vite.svg`, `web/src/main.tsx`, `web/src/App.tsx`, `web/src/App.css`, `web/src/index.css`, `web/src/types.ts`, `web/src/vite-env.d.ts`, `web/src/assets/react.svg`
- **Sửa (frontend)**: `web/README.md`, `web/index.html` (title, code review fix)

## Change Log

- 2026-07-06 — Story 3.1 tạo bởi create-story workflow (Amelia). Xác nhận với Lan qua AskUserQuestion: bỏ qua auth/token cho MVP nội bộ (nới lỏng AD-19 phần token, giữ nguyên phần "không lộ path thật"). Phát hiện gap: `web/` chỉ là stub, chưa từng có "thumbnail"/"proxy" pipeline riêng (dùng lại Keyframe/source_key gốc thay thế).
- 2026-07-06 — Story 3.1: `api/routes_media.py` (thumbnail Scene qua Keyframe đầu tiên, video stream qua `FileResponse` + HTTP Range) + dựng thật `web/` (React 19.2 + Vite 7, thay stub Story 1.1) với UI tìm kiếm + preview hover. 148/148 test backend pass (7 mới), `npm run build` sạch, ruff clean. Verify sống qua docker-compose thật (curl + Playwright browser thật) — xem Debug Log Dev Agent Record. 2 entry deferred (auth/token thật, transcode video proxy).
- 2026-07-06 — Code review: 10 patch áp dụng (404 sạch khi file mất trên disk/keyframe_key rỗng, docstring codec, onClick, race guard tìm kiếm, onError fallback, xoá test no-op, title, playsInline) + 3 finding defer (blocking I/O, cache header, unmount/remount preview). 151/151 test pass, build/lint sạch, verify lại 404-fix qua docker thật.
