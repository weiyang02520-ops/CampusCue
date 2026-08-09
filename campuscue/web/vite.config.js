import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

/**
 * The board is a separate SPA from AstrBot's admin dashboard, served by the same
 * FastAPI process under /campus.
 *
 * base must be '/campus/' so the built asset URLs resolve when the app is served
 * from a subpath rather than the site root.
 */
export default defineConfig({
  base: '/campus/',
  plugins: [vue()],
  server: {
    port: 5180,
    // In dev the Vite server holds the page and proxies the API to the running
    // bot, so there is no CORS configuration to maintain on the Python side.
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:6185',
        changeOrigin: true,
        // SSE breaks silently if the proxy buffers, which would kill exactly the
        // live-arrival behaviour the board is built around.
        ws: false,
      },
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
})
