import { expect, test } from '@playwright/test';

/**
 * Advanced Dashboard → Expiry Radar.
 *
 * The stub clock is Thursday 15 January 2026, and the three indices disagree
 * about that week on purpose: SENSEX settles today, NIFTY's Tuesday weekly is
 * five days out, and BANK NIFTY has no weekly series at all. One page load
 * therefore exercises every state the feature has — which is why the dates in
 * `stub-api.mjs` are chosen rather than arbitrary.
 *
 * Every assertion reaches for text or an accessible name, never a colour. The
 * red/amber triangles are the fastest way to read the card and also the first
 * thing to fail on a greyscale screen or for a reader who cannot separate the
 * two, so the words have to carry the same information — and a suite that can
 * only see colour would never notice if they stopped.
 */

const STUB_API = `http://localhost:${process.env.STUB_API_PORT ?? 8099}`;

test.beforeEach(async ({ context, baseURL, page }) => {
  await context.addCookies([
    { name: 'cn_session', value: 'test', url: baseURL ?? 'http://localhost:4173' }
  ]);

  // This page loads its data from the browser and the app server has no
  // `/api/v1` route, so forward those to the stub the loaders use.
  await page.route('**/api/v1/**', async (route) => {
    const url = new URL(route.request().url());
    try {
      const upstream = await route.fetch({ url: `${STUB_API}${url.pathname}${url.search}` });
      await route.fulfill({ response: upstream });
    } catch {
      // The page polls, so a request can still be in flight as the context
      // tears down. `pcr.spec.ts` guards its proxy the same way.
      await route.abort().catch(() => {});
    }
  });

  await page.goto('/advanced-dashboard');
  await expect(page.getByRole('heading', { name: 'Advanced Dashboard' })).toBeVisible({
    timeout: 15_000
  });
});

test('shows each index its own settlement calendar', async ({ page }) => {
  await expect(page.getByRole('heading', { name: 'Expiry Radar' })).toBeVisible();

  // SENSEX settles today; NIFTY's Tuesday weekly is five days out and its
  // monthly twelve. Three different answers on one screen is the point.
  await expect(page.getByLabel('SENSEX weekly expiry today, Thu 15 Jan')).toBeVisible();
  await expect(page.getByLabel('NIFTY 50 weekly expiry in 5 days, Tue 20 Jan')).toBeVisible();
  await expect(page.getByLabel('NIFTY 50 monthly expiry in 12 days, Tue 27 Jan')).toBeVisible();
});

test('states that BANK NIFTY has no weekly series', async ({ page }) => {
  // The withdrawn weekly is said outright rather than left as a blank row,
  // which would read as a feed that failed instead of a contract that is gone.
  await expect(page.getByText('No weekly series — this index settles monthly.')).toBeVisible();
  await expect(page.getByLabel('BANK NIFTY monthly expiry in 12 days, Tue 27 Jan')).toBeVisible();
});

test('claims nothing about a date the broker confirmed', async ({ page }) => {
  // The stub serves its expiry list as `live`, so no card may hedge. The
  // caveat appearing here would mean the page had silently fallen back to
  // computing dates itself.
  await expect(page.getByText(/scheduled date/i)).toHaveCount(0);
});

test('interrupts with an alert on the day itself', async ({ page }) => {
  const alert = page.getByRole('status').filter({ hasText: 'Expiry today' });
  await expect(alert).toBeVisible();
  await expect(alert).toContainText('SENSEX');

  await alert.getByRole('button', { name: 'Dismiss expiry alert' }).click();
  await expect(alert).toBeHidden();

  // Dismissal is for this session, not this render: coming back to the page
  // must not re-interrupt someone who has already acknowledged it.
  await page.reload();
  await expect(page.getByRole('heading', { name: 'Expiry Radar' })).toBeVisible();
  await expect(page.getByText('Expiry today')).toHaveCount(0);
});

test('marks the nearest expiry on the spot card itself', async ({ page }) => {
  // The radar sits below the futures and metrics rows, so the corner marker is
  // what makes the signal reachable without scrolling.
  const card = page.getByRole('button', { name: /SENSEX/ }).first();
  await expect(card).toContainText('Weekly expiry Thu 15 Jan, today');
});
