import { defineConfig, devices } from '@playwright/test';

const PORT = 4173;
const STUB_API_PORT = 8099;

export default defineConfig({
  testDir: './tests',
  testMatch: ['e2e/**/*.spec.ts', 'accessibility/**/*.spec.ts'],
  outputDir: './test-results',

  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  // Spread rather than `workers: undefined`: under `exactOptionalPropertyTypes`
  // an explicit undefined is not the same as an absent key, and absent is what
  // "let Playwright decide" means.
  ...(process.env.CI ? { workers: 2 } : {}),
  timeout: 30_000,
  expect: { timeout: 5_000 },

  reporter: process.env.CI
    ? [['html', { open: 'never' }], ['github']]
    : [['list'], ['html', { open: 'never' }]],

  use: {
    baseURL: process.env.E2E_BASE_URL ?? `http://localhost:${PORT}`,
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    timezoneId: 'Asia/Kolkata',
    locale: 'en-IN',
    // Functional specs assert behaviour, not motion. With the app's ambient
    // loops (live-dot pulses, skeleton pulses, route fades) actually running,
    // headless Chromium's software compositor keeps rendering frames for every
    // open page, and across parallel workers that CPU cost pushed navigation
    // assertions past their 5s timeout on slower machines. Reduced motion makes
    // every animation finish in 0.01ms (see the block at the end of app.css),
    // so specs run against the same DOM without paying for frames.
    contextOptions: { reducedMotion: 'reduce' }
  },

  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
    { name: 'firefox', use: { ...devices['Desktop Firefox'] } },
    { name: 'mobile', use: { ...devices['Pixel 7'] } }
  ],

  webServer: [
    // Stands in for the backend so the suite is hermetic. See tests/e2e/stub-api.mjs.
    {
      command: `node tests/e2e/stub-api.mjs`,
      url: `http://localhost:${STUB_API_PORT}/__stub/health`,
      reuseExistingServer: !process.env.CI,
      timeout: 30_000
    },
    // Tests run against the production build: dev-only behaviour has hidden
    // real bugs here before (hydration and CSP differ between the two, and the
    // CSP is nonce-based in production only).
    {
      command: `pnpm build && pnpm start`,
      port: PORT,
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
      env: {
        PORT: String(PORT),
        API_INTERNAL_URL: `http://localhost:${STUB_API_PORT}`
      }
    }
  ]
});
