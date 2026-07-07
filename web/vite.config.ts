import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// AD-13: UI chỉ qua REST/JSON /api/v1 — dev server proxy /api sang backend FastAPI
// (chạy qua uvicorn/docker-compose ở :8000) để tránh CORS + hardcode origin.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
