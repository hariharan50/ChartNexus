import { svelte, vitePreprocess } from '@sveltejs/vite-plugin-svelte';
import { fileURLToPath } from 'node:url';
import { defineConfig } from 'vitest/config';

const resolve = (path: string) => fileURLToPath(new URL(path, import.meta.url));

export default defineConfig({
  plugins: [
    svelte({
      hot: false,
      // Ignore svelte.config.js here. Its `vitePreprocess()` runs Vite's CSS
      // pipeline over every <style> block, which throws under Vitest ("Cannot
      // create proxy with a non-object as target"). Nothing in that config is
      // needed for component tests — the kit aliases are redeclared below, and
      // `lang="ts"` is handled by esbuild.
      configFile: false,
      preprocess: vitePreprocess({ style: false })
    })
  ],
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
