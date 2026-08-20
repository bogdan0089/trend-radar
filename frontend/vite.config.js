import { fileURLToPath, URL } from 'node:url'

import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

// In production nginx proxies /api to the api container, so the app always
// talks to a same-origin /api and never needs an absolute backend URL.
// `npm run dev` reproduces that with the proxy below.
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    host: true,
    port: 5173,
    proxy: {
      '/api': {
        target: process.env.VITE_DEV_API_TARGET || 'http://localhost:8011',
        changeOrigin: true,
      },
    },
  },
})
