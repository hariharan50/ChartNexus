import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

export default defineConfig({
  plugins: [sveltekit()],

  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      // Same-origin in development so the session cookie is sent without
      // relaxing SameSite. Production serves both behind one hostname.
      '/api': {
        target: process.env.API_PROXY_TARGET ?? 'http://localhost:8000',
        changeOrigin: true
      },
      '/ws': {
        target: process.env.WS_PROXY_TARGET ?? 'ws://localhost:8001',
        ws: true
      }
    }
  },

  build: {
    target: 'es2022',
    sourcemap: true,
    chunkSizeWarningLimit: 700
  },

  optimizeDeps: {
    exclude: ['@tanstack/svelte-query']
  }
});
