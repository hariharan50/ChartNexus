import { expect, test, type Page } from '@playwright/test';

/**
 * Analyse — the candlestick price chart.
 *
 * This is the app's only TradingView Lightweight Charts page, so beyond the
 * usual DOM assertions there is one thing here worth proving directly: the
 * library mounts at all. It is imported dynamically inside an effect precisely
 * so it never loads during SSR, and a canvas appearing is the evidence that the
 * dynamic import resolved in the browser.
 *
 * The stub serves a deterministic saw around each instrument's spot, with zero
 * volume — which is what an index history really is.
 */

const STUB_API = `http://localhost:${process.env.STUB_API_PORT ?? 8099}`;

test.beforeEach(async ({ context, baseURL, page }) => {
  await context.addCookies([
    { name: 'cn_session', value: 'test', url: baseURL ?? 'http://localhost:4173' }
  ]);

  await page.route('**/api/v1/**', async (route) => {
    const url = new URL(route.request().url());
    const upstream = await route.fetch({ url: `${STUB_API}${url.pathname}${url.search}` });
    await route.fulfill({ response: upstream });
  });

  await page.goto('/analyse');
  // Generous: this page dynamically imports a charting library before it can
  // paint, and under the suite's eight parallel workers that first load can
  // genuinely take longer than the 5s default.
  await expect(page.getByRole('heading', { name: 'NIFTY', exact: true })).toBeVisible({
    timeout: 15_000
  });
});

const caption = (page: Page) => page.getByText(/bars over \d+ trading/);

/**
 * Records history requests as they are issued.
 *
 * Deliberately not `waitForRequest`: that resolves the moment a request is
 * *sent*, so the test can finish and tear the context down while the routed
 * fetch is still in flight — which fails as "Fetch response has been disposed".
 * Collecting into an array and asserting after the UI has settled has no such
 * race.
 */
function recordHistoryCalls(page: Page): string[] {
  const urls: string[] = [];
  page.on('request', (request) => {
    if (request.url().includes('/market/history')) urls.push(request.url());
  });
  return urls;
}

test('mounts the price chart', async ({ page }) => {
  // The library renders into canvases. One existing means the dynamic import
  // resolved client-side — the whole SSR strategy in one assertion.
  await expect(page.locator('canvas').first()).toBeVisible();
  await expect(page).toHaveTitle('Analyse · ChartNexus');
});

test('summarises the drawn range rather than the day', async ({ page }) => {
  // Named on screen, because on every timeframe but 1D the two differ and a
  // reader would otherwise assume it was the day's move.
  await expect(page.getByText('over the drawn range')).toBeVisible();
});

test('the interval pills change the timeframe and refetch', async ({ page }) => {
  const calls = recordHistoryCalls(page);
  await expect(caption(page)).toContainText('5m bars over 3 trading days');

  await page.getByRole('button', { name: '1D', exact: true }).click();

  await expect(caption(page)).toContainText('1D bars over 180 trading days');
  await expect(page.getByRole('button', { name: '1D', exact: true })).toHaveAttribute(
    'aria-pressed',
    'true'
  );
  // Each interval is its own query key, so the switch is a real fetch and not a
  // client-side reslice of bars aggregated for a different bar size.
  await expect(() => expect(calls.some((url) => url.includes('interval=1d'))).toBe(true)).toPass();
});

test('hides the volume pane for an index and says why', async ({ page }) => {
  // An empty pane taking a fifth of the chart would read as missing data rather
  // than as absent turnover.
  await expect(caption(page)).toContainText('no volume');
});

test('labels simulated data instead of passing it off as live', async ({ page }) => {
  // The stub stamps every payload `mock`. Provenance reaching the screen is the
  // point of the API sending it at all.
  await expect(page.getByText('simulated data')).toBeVisible();
});

test('cycles to another instrument', async ({ page }) => {
  const calls = recordHistoryCalls(page);

  await page.getByRole('button', { name: 'Next instrument' }).click();

  await expect(page.getByRole('heading', { name: 'SENSEX', exact: true })).toBeVisible();
  await expect(() =>
    expect(calls.some((url) => url.includes('instrument=SENSEX'))).toBe(true)
  ).toPass();
});
