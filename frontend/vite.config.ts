import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// base: './' —— dist 可以被 FastAPI（或任意静态服务器）挂在任何子路径下
export default defineConfig({
  base: './',
  plugins: [vue()],
  server: {
    host: '127.0.0.1',
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8200',
        changeOrigin: true,
      },
    },
  },
  build: {
    target: 'es2022',
    chunkSizeWarningLimit: 1200,
  },
})
