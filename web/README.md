# web/

SPA React 19.2 + Vite 7 (không SSR). UI chỉ qua REST/JSON `/api/v1` (AD-13); không
truy cập DB/storage trực tiếp; media (thumbnail/video) chỉ qua API (`api/routes_media.py`,
AD-19 — không auth/token cho MVP nội bộ, xem story 3.1 Scope Decision #1).

Dựng thật ở Story 3.1 (Epic 3) — trước đó chỉ là stub (Story 1.1).

## Dev

Cần backend chạy song song ở `:8000` (`uv run uvicorn api.main:app --reload` hoặc
`docker compose up api`).

```
npm install
npm run dev
```

Vite dev server proxy `/api` → `http://localhost:8000` (xem `vite.config.ts`) — không
cần cấu hình CORS, gọi `fetch('/api/v1/...')` tương đối.

## Build

```
npm run build
```

Chạy `tsc -b` (type-check) rồi `vite build` (bundle vào `dist/`). Đây là bar chấp nhận
DUY NHẤT cho frontend hiện tại — chưa có Vitest/React Testing Library/Playwright
(quyết định scope Story 3.1, để lại cho story sau khi cần).
