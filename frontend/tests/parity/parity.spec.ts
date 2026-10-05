import { expect, test, type Page } from '@playwright/test';
import { mkdirSync } from 'node:fs';
import { join } from 'node:path';
import { comparePng } from './compare';

/**
 * Side-by-side pixel comparison against the SvelteKit app.
 *
 * The migration's contract is "framework swap, not redesign", and eyeballing
 * two screenshots does not prove that. This loads the same path in both apps at
 * the same viewport and fails on a pixel difference above a small threshold.
 *
 * Not part of `pnpm test:e2e` — it needs the SvelteKit app running alongside.
 * Since the swap that is no longer in the working tree, so check the last
 * pre-migration commit out beside it:
 *
 *   git worktree add ../cn-svelte <pre-migration-sha>
 *   cd ../cn-svelte/frontend && pnpm install && pnpm dev   # :5173
 *   cd frontend && pnpm parity                             # this file
 *
 * Kept rather than deleted: it is the evidence that the port reproduced the
 * original UI, and the method to re-check any screen that gets questioned.
 *
 * Pages behind the terminal guard need both apps talking to the same API. Point
 * the Svelte dev server at this suite's stub so the two agree on who is signed
 * in:
 *
 *   cd frontend && API_PROXY_TARGET=http://localhost:8099 pnpm dev
 */

const SVELTE = process.env.PARITY_SVELTE_URL ?? 'http://localhost:5173';
const OUT = 'parity-output';

/**
 * Chosen to straddle every breakpoint the stylesheets actually use — 90rem,
 * 72rem, 64rem, 60rem, 48rem, 40rem and 30rem — so a media query that was
 * mis-transcribed shows up rather than hiding between the samples.
 */
const WIDTHS = [1600, 1280, 1024, 768, 640, 375];

const PUBLIC_PATHS = ['/login', '/register', '/forgot-password'];

/** Behind the terminal guard: needs the session cookie the stub recognises. */
const TERMINAL_PATHS = [
  '/dashboard',
  '/advanced-dashboard',
  '/option-chain',
  '/options',
  '/options/open-interest',
  '/settings/profile',
  '/settings/security',
  '/settings/notifications',
  '/settings/global',
  '/settings/help',
  '/settings',
  '/options/pcr',
  '/analyse'
];

async function shoot(page: Page, url: string, width: number, file: string): Promise<Buffer> {
  await page.setViewportSize({ width, height: 900 });
  await page.goto(url, { waitUntil: 'networkidle' });
  // The spinner in Button and the auth callback animate forever; freeze them so
  // a diff never depends on when the screenshot landed.
  await page.addStyleTag({ content: '*, *::before, *::after { animation: none !important; }' });
  return page.screenshot({ path: join(OUT, file), fullPage: true });
}

const STUB_API = process.env.PARITY_STUB_API ?? 'http://localhost:8099';

test.beforeAll(() => {
  mkdirSync(OUT, { recursive: true });
});

/**
 * Send both apps' browser-side API calls to the same stub.
 *
 * Only the Vite dev server proxies `/api`; `react-router-serve` does not, and in
 * production a reverse proxy fronts both. Without this the two apps would get
 * different failure responses for the same request and the diff would be
 * measuring the harness rather than the port.
 */
test.beforeEach(async ({ page }) => {
  // The Open Interest page renders a clock that ticks every second, and the two
  // screenshots are taken seconds apart. Fixing `Date` — without faking timers,
  // which would stall react-query — makes it render the same string in both.
  await page.clock.setFixedTime(new Date('2026-01-15T10:46:46+05:30'));

  await page.route('**/api/v1/**', async (route) => {
    const url = new URL(route.request().url());
    await route.continue({ url: `${STUB_API}${url.pathname}${url.search}` });
  });
});

function comparePaths(paths: string[], signedIn: boolean) {
  for (const path of paths) {
    for (const width of WIDTHS) {
      test(`${path} matches the Svelte app at ${width}px`, async ({ page, context, baseURL }) => {
        if (signedIn) {
          // Same cookie for both origins so the stub reports the same user.
          await context.addCookies([
            { name: 'cn_session', value: 'test', url: baseURL ?? 'http://localhost:4173' },
            { name: 'cn_session', value: 'test', url: SVELTE }
          ]);
        }

        const slug = `${path.replace(/\//g, '_') || '_root'}-${width}`;

        const svelte = await shoot(page, `${SVELTE}${path}`, width, `${slug}.svelte.png`);
        const react = await shoot(page, `${baseURL}${path}`, width, `${slug}.react.png`);

        const { mismatchedPixels, totalPixels } = comparePng(
          svelte,
          react,
          join(OUT, `${slug}.diff.png`)
        );

        // 0.1% absorbs font antialiasing between two separate page loads without
        // hiding a real layout or colour change.
        const ratio = mismatchedPixels / totalPixels;
        expect(
          ratio,
          `${mismatchedPixels}/${totalPixels} pixels differ — see ${OUT}/${slug}.diff.png`
        ).toBeLessThan(0.001);
      });
    }
  }
}

test.describe('public routes', () => comparePaths(PUBLIC_PATHS, false));
test.describe('terminal routes', () => comparePaths(TERMINAL_PATHS, true));
