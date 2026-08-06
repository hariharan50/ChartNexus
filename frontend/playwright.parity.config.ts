import { defineConfig, devices } from '@playwright/test';
import base from './playwright.config';

const PORT = 4173;

/**
 * The parity suite, kept out of the main config because it needs the SvelteKit
 * app running on :5173 as the reference, from a pre-migration worktree. See
 * tests/parity/parity.spec.ts for the setup.
 *
 * The stub API is inherited from the base config, so both apps see the same
 * signed-out state; a signed-in comparison needs the real backend and the same
 * cookie in both, which is why only public routes are covered for now.
 */
export default defineConfig({
  ...base,
  testDir: './tests',
  testMatch: ['parity/**/*.spec.ts'],
  // Screenshots must survive the run — the main config wipes ./test-results.
  outputDir: './test-results-parity',
  // A pixel diff is meaningless when two tests race over the same viewport.
  fullyParallel: false,
  workers: 1,
  retries: 0,
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: [
    {
      command: `pnpm build && pnpm start`,
      port: PORT,
      reuseExistingServer: true,
      timeout: 120_000,
      env: { PORT: String(PORT), API_INTERNAL_URL: 'http://localhost:8099' }
    }
  ]
});
