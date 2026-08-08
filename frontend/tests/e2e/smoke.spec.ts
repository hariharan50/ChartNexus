import { expect, test } from '@playwright/test';

/**
 * The two loaders that decide where a visitor lands: the `/` landing page and
 * the terminal auth guard. Both were SvelteKit `load` functions; both are now
 * React Router loaders reached over a different fetch path.
 */

test('/ renders the landing page for a signed-out visitor', async ({ page }) => {
  const response = await page.goto('/');
  expect(response?.status()).toBe(200);
  await expect(page).toHaveURL('/');
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
});

test.describe('signed out', () => {
  test('a terminal route bounces to sign-in carrying where it came from', async ({ page }) => {
    await page.goto('/dashboard');
    await expect(page).toHaveURL('/login?next=%2Fdashboard');
  });

  test('the next param keeps the query string, encoded', async ({ page }) => {
    await page.goto('/option-chain?symbol=NIFTY&expiry=nearest');
    await expect(page).toHaveURL('/login?next=%2Foption-chain%3Fsymbol%3DNIFTY%26expiry%3Dnearest');
  });

  test('a public route renders without the guard running', async ({ page }) => {
    const response = await page.goto('/login');
    expect(response?.status()).toBe(200);
  });
});

test.describe('signed in', () => {
  test.beforeEach(async ({ context, baseURL }) => {
    await context.addCookies([
      { name: 'mc_session', value: 'test', url: baseURL ?? 'http://localhost:4173' }
    ]);
  });

  test('/ sends a signed-in visitor straight past the marketing page', async ({ page }) => {
    await page.goto('/');
    await expect(page).toHaveURL('/dashboard');
  });

  test('a settings page renders nested inside both layouts', async ({ page }) => {
    const response = await page.goto('/settings/profile');
    expect(response?.status()).toBe(200);
    await expect(page).toHaveURL('/settings/profile');
    await expect(page).toHaveTitle('Personal Info · Settings · MarketCompass');
  });
});

test('an unknown path renders the error boundary', async ({ page }) => {
  await page.goto('/definitely-not-a-route');
  await expect(page).toHaveTitle('404 · MarketCompass');
  await expect(page.getByRole('heading', { name: 'Page not found' })).toBeVisible();
});

test('the security headers survive into production', async ({ request }) => {
  const response = await request.get('/login');
  const csp = response.headers()['content-security-policy'];
  expect(csp).toContain("frame-ancestors 'none'");
  expect(csp).toMatch(/script-src 'self' 'nonce-[a-f0-9]+'/);
  expect(response.headers()['x-request-id']).toBeTruthy();
});

test('a stored theme is applied before first paint', async ({ page, context }) => {
  await context.addInitScript(() => {
    localStorage.setItem('mc-theme', 'light');
    localStorage.setItem('mc-pref-callput', 'inverted');
  });

  await page.goto('/login');
  // Sampled before the network settles: the bootstrap runs synchronously in
  // <head>, so a light-theme user never sees the dark default flash.
  expect(await page.evaluate(() => document.documentElement.dataset.theme)).toBe('light');
  expect(await page.evaluate(() => document.documentElement.dataset.callput)).toBe('inverted');

  await page.waitForLoadState('networkidle');
  // …and hydration does not undo it.
  expect(await page.evaluate(() => document.documentElement.dataset.theme)).toBe('light');
});

test('the container healthcheck endpoint answers', async ({ request }) => {
  const response = await request.get('/healthz');
  expect(response.status()).toBe(200);
  expect(await response.text()).toBe('ok');
});
