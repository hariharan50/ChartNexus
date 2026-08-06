import react from '@vitejs/plugin-react';
import { fileURLToPath } from 'node:url';
import { defineConfig } from 'vitest/config';

const resolve = (path: string) => fileURLToPath(new URL(path, import.meta.url));

export default defineConfig({
  // The React Router plugin is deliberately absent: it owns routing/SSR entry
  // generation, none of which a unit or component test needs. Plain
  // @vitejs/plugin-react gives JSX + Fast Refresh transforms and nothing else.
  plugins: [react()],
  resolve: {
    alias: {
      $app: resolve('./app/lib/app'),
      $contexts: resolve('./app/lib/contexts'),
      $shared: resolve('./app/lib/shared'),
      $lib: resolve('./app/lib')
    },
    conditions: ['browser']
  },
  css: {
    modules: { localsConvention: 'camelCase' }
  },
  test: {
    environment: 'jsdom',
    globals: true,
    include: ['tests/unit/**/*.{test,spec}.{ts,tsx}', 'tests/component/**/*.{test,spec}.{ts,tsx}'],
    setupFiles: ['./app/lib/shared/testing/setup.ts'],
    clearMocks: true,
    restoreMocks: true,
    coverage: {
      provider: 'v8',
      reportsDirectory: './coverage',
      include: ['app/lib/**/*.{ts,tsx}'],
      exclude: ['app/lib/shared/api/generated/**', 'app/lib/shared/testing/**']
    }
  }
});
