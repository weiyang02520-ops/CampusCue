import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: { port: 4173, host: '127.0.0.1', proxy: { '/api': 'http://127.0.0.1:6200' } },
  build: { sourcemap: true }
})
