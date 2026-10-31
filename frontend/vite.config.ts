import { reactRouter } from '@react-router/dev/vite';
import { defineConfig } from 'vite';

export default defineConfig({
  plugins: [reactRouter()],

  // Resolves the $app / $contexts / $shared aliases from tsconfig.json. Native
  // since Vite 8 — no vite-tsconfig-paths plugin needed.
  resolve: { tsconfigPaths: true },

  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      // Same-origin in development so the session cookie is sent without
      // relaxing SameSite. Production serves both behind one hostname.
      //
      // `127.0.0.1`, not `localhost`. Uvicorn binds IPv4 only by default, and
      // Node resolves `localhost` to `::1` first on Windows — so the proxy
      // asked for a socket nothing was listening on and Vite turned the
      // ECONNREFUSED into a 502 on every API call, login included. Node's
      // happy-eyeballs fallback retries over IPv4 and usually hides this,
      // which is what made it look intermittent. Naming the family removes
      // the guess. `API_PROXY_TARGET` still overrides for the container,
      // where the backend is `api:8000` rather than loopback.
      '/api': {
        target: process.env.API_PROXY_TARGET ?? 'http://127.0.0.1:8000',
        changeOrigin: true
      },
      '/ws': {
        target: process.env.WS_PROXY_TARGET ?? 'ws://127.0.0.1:8001',
        ws: true
      }
    }
  },

  css: {
    modules: {
      // Svelte scoped `.badge-ico` verbatim; CSS Modules files keep kebab-case
      // so style blocks copy across unedited, and TSX reads them as `s.badgeIco`.
      localsConvention: 'camelCase'
    }
  },

  build: {
    target: 'es2022',
    sourcemap: true,
    chunkSizeWarningLimit: 700
  },

  // Only PUBLIC_-prefixed variables reach the browser bundle, matching the
  // SvelteKit `env.publicPrefix` this replaces.
  envPrefix: 'PUBLIC_'
});
