import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

// In Docker, the backend runs in a separate container reachable at "backend:7860"
const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:7860'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 5173,
    host: '0.0.0.0',
    proxy: {
      '/api': {
        target: BACKEND_URL,
        changeOrigin: true,
        ws: true,
      },
      '/auth': {
        target: BACKEND_URL,
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
  },
})
