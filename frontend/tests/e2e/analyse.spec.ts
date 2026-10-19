import { expect, test, type Page } from '@playwright/test';

/**
 * Analyse — the candlestick price workspace.
 *
 * This is the app's only TradingView Lightweight Charts page, so beyond the
 * usual DOM assertions there is one thing here worth proving directly: the
 * library mounts at all. It is imported dynamically inside an effect precisely
 * so it never loads during SSR, and a canvas appearing is the evidence that the
 * dynamic import resolved in the browser. (Unlike the ECharts pages, which run
 * on the SVG renderer, lightweight-charts owns its own canvas.)
 *
 * The stub serves a deterministic saw around each instrument's spot, with zero
 * volume — which is what an index history really is.
 */

const STUB_API = `http://localhost:${process.env.STUB_API_PORT ?? 8099}`;

/**
 * The chart cell, which names itself after what it is drawing.
 *
 * `aria-label` is `"<symbol> <interval>"`, built from the cell's own config, so
 * waiting on it is waiting on the chart that the toolbar claims is on screen —
 * a stronger anchor than any one heading.
 */
const cell = (page: Page, label: string) => page.getByRole('group', { name: label, exact: true });

const caption = (page: Page) => page.getByText(/· \d+ candles/);

test.beforeEach(async ({ context, baseURL, page }) => {
  await context.addCookies([
    { name: 'cn_session', value: 'test', url: baseURL ?? 'http://localhost:4173' }
  ]);

  await page.route('**/api/v1/**', async (route) => {
    const url = new URL(route.request().url());
    try {
      const upstream = await route.fetch({ url: `${STUB_API}${url.pathname}${url.search}` });
      await route.fulfill({ response: upstream });
    } catch {
      // These pages poll, so a request can still be in flight when the test
      // body finishes and the context starts tearing down — which surfaces as
      // "Fetch response has been disposed" on a test that already passed.
      // Nothing is waiting on the answer by then. `symbol-search.spec.ts`
      // guards its proxy the same way.
      await route.abort().catch(() => {});
    }
  });

  await page.goto('/analyse');
  // Generous: this page dynamically imports a charting library before it can
  // paint, and under the suite's eight parallel workers that first load can
  // genuinely take longer than the 5s default.
  await expect(cell(page, 'NIFTY 5m')).toBeVisible({ timeout: 15_000 });
});

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
  await expect(page).toHaveTitle('Chart Tools · ChartNexus');
});

test('reads the newest bar into the legend', async ({ page }) => {
  // The legend falls back to the last bar when the pointer is off the plot,
  // which is the state it spends most of its life in — so the close is on
  // screen without anyone hovering anything.
  const legend = cell(page, 'NIFTY 5m');

  await expect(legend.getByText('NIFTY', { exact: true })).toBeVisible();
  for (const key of ['O', 'H', 'L', 'C']) {
    await expect(legend.getByText(key, { exact: true })).toBeVisible();
  }
});

test('the interval menu changes the timeframe and refetches', async ({ page }) => {
  const calls = recordHistoryCalls(page);
  await expect(caption(page)).toContainText('5m ·');

  // The toolbar's interval control is a menu button labelled with the current
  // interval, not a row of pills.
  await page
    .getByRole('toolbar', { name: 'Chart controls' })
    .getByRole('button', { name: '5m' })
    .click();
  await page.getByRole('menuitemradio', { name: '1D' }).click();

  // The cell renames itself after the interval it now holds, and the caption
  // follows. `1d` in the label, `1D` in the caption: the first is the API's
  // value, the second the label a reader sees.
  await expect(cell(page, 'NIFTY 1d')).toBeVisible();
  await expect(caption(page)).toContainText('1D ·');
  // Each interval is its own query key, so the switch is a real fetch and not a
  // client-side reslice of bars aggregated for a different bar size.
  await expect(() => expect(calls.some((url) => url.includes('interval=1d'))).toBe(true)).toPass();
});

test('omits the volume row for an index', async ({ page }) => {
  // An empty pane taking a fifth of the chart would read as missing data rather
  // than as absent turnover, so an all-zero series is dropped outright — and
  // the legend's volume row goes with it.
  await expect(cell(page, 'NIFTY 5m').getByText('Volume', { exact: true })).toHaveCount(0);
});

test('labels simulated data instead of passing it off as live', async ({ page }) => {
  // The stub stamps every payload `mock`. Provenance reaching the screen is the
  // point of the API sending it at all.
  await expect(page.getByText('simulated data')).toBeVisible();
});

test('switches to another instrument through the symbol picker', async ({ page }) => {
  const calls = recordHistoryCalls(page);

  await page.getByRole('button', { name: /NIFTY\s+Click to change/ }).click();

  const picker = page.getByRole('dialog', { name: 'Choose instrument' });
  await expect(picker).toBeVisible();
  await picker.getByLabel('Search instrument').fill('SENSEX');
  await picker
    .getByRole('button', { name: /SENSEX/ })
    .first()
    .click();

  await expect(picker).toBeHidden();
  await expect(cell(page, 'SENSEX 5m')).toBeVisible();
  await expect(() =>
    expect(calls.some((url) => url.includes('instrument=SENSEX'))).toBe(true)
  ).toPass();
});
