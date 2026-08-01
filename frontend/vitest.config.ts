import { svelte } from '@sveltejs/vite-plugin-svelte';
import { fileURLToPath } from 'node:url';
import { defineConfig } from 'vitest/config';

const resolve = (path: string) => fileURLToPath(new URL(path, import.meta.url));

export default defineConfig({
  plugins: [svelte({ hot: false })],
  resolve: {
    // Vitest runs without the SvelteKit plugin, so the kit aliases from
    // svelte.config.js have to be repeated here.
    alias: {
      $app: resolve('./src/lib/app'),
      $contexts: resolve('./src/lib/contexts'),
      $shared: resolve('./src/lib/shared'),
      $lib: resolve('./src/lib')
    },
    conditions: ['browser']
  },
  test: {
    environment: 'jsdom',
    globals: true,
    include: ['tests/unit/**/*.{test,spec}.ts', 'tests/component/**/*.{test,spec}.ts'],
    setupFiles: ['./src/lib/shared/testing/setup.ts'],
    clearMocks: true,
    restoreMocks: true,
    coverage: {
      provider: 'v8',
      reportsDirectory: './coverage',
      include: ['src/lib/**/*.{ts,svelte}'],
      exclude: ['src/lib/shared/api/generated/**', 'src/lib/shared/testing/**']
    }
  }
});
