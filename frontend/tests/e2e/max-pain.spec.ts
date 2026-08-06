import { expect, test, type Page } from '@playwright/test';

/**
 * Options Lab → Max Pain.
 *
 * The pain profile is an ECharts canvas and opaque to Playwright, so the
 * assertions land on the DOM around it. That is a sound proxy here: the range
 * line, the legend and the two sentiment rows are all rendered from the same
 * derived values the chart draws, and the curve arithmetic itself is covered
 * by `tests/unit/max-pain-data.test.ts`.
 *
 * The stub serves a 21-strike NIFTY ladder — spot 24,500.25, ATM 24,500,
 * max pain 24,400 — so every figure below is a fixed function of that payload.
 */

const STUB_API = `http://localhost:${process.env.STUB_API_PORT ?? 8099}`;

test.beforeEach(async ({ context, baseURL, page }) => {
  await context.addCookies([
    { name: 'mc_session', value: 'test', url: baseURL ?? 'http://localhost:4173' }
  ]);

  // This page fetches from the browser and the app server has no `/api/v1`
  // route, so forward those to the stub the loaders use.
  await page.route('**/api/v1/**', async (route) => {
    const url = new URL(route.request().url());
    const upstream = await route.fetch({ url: `${STUB_API}${url.pathname}${url.search}` });
    await route.fulfill({ response: upstream });
  });

  await page.goto('/options/max-pain');
  // Generous: this page mounts an ECharts canvas, and under the suite's eight
  // parallel workers a first paint can genuinely take longer than the 5s
  // default. A slow mount is not the same as a broken page.
  await expect(page.getByRole('heading', { name: 'Max Pain', exact: true })).toBeVisible({
    timeout: 15_000
  });
});

/**
 * Exact heading match, deliberately: the sentiment panel is titled "Market
 * Sentiment (based on Max Pain)", so a substring match on "Max Pain" selects
 * both panels — and both now hold a canvas.
 */
const panel = (page: Page, title: string) =>
  page.locator('section').filter({ has: page.getByRole('heading', { name: title, exact: true }) });

const range = (page: Page) => page.getByText(/Showing \d+ strikes/);

test('draws the pain profile with a call and a put side', async ({ page }) => {
  const chart = panel(page, 'Max Pain');

  await expect(chart.locator('canvas')).toBeVisible();
  await expect(chart.getByText('Call Pain', { exact: true })).toBeVisible();
  await expect(chart.getByText('Put Pain', { exact: true })).toBeVisible();

  // Every candidate is priced against the whole chain, never the drawn window.
  await expect(range(page)).toContainText('priced against all 21 listed');
});

test('reads the gap between spot and max pain', async ({ page }) => {
  const sentiment = panel(page, 'Market Sentiment (based on Max Pain)');

  // 24,500.25 against 24,400 is +0.41% — just past the +0.4% edge of the
  // gauge's middle fifth, so this is the first zone above Neutral.
  await expect(sentiment.getByText('Buy', { exact: true })).toBeVisible();
  await expect(sentiment.getByText('Spot above Max Pain')).toBeVisible();
  // The gauge also prints the gap, but that lives on the canvas. The figure
  // reaches the DOM through the insight sentence asserted below — which is the
  // only form a screen reader or a find-in-page can reach either.

  // The two figures the whole panel is about, straight off the payload.
  await expect(sentiment.getByRole('term').filter({ hasText: 'Max Pain Strike' })).toBeVisible();
  await expect(sentiment.getByText('24400.00', { exact: true })).toBeVisible();
  await expect(sentiment.getByText('24500.25', { exact: true })).toBeVisible();

  await expect(sentiment.getByText(/0\.41% above max pain/)).toBeVisible();
});

test('the strike filter narrows what is drawn', async ({ page }) => {
  // Default is ±20, which reaches past both ends of a 21-strike ladder.
  await expect(range(page)).toContainText('Showing 21 strikes · 24000 – 25000');

  await page.getByRole('button', { name: '5', exact: true }).click();
  await expect(range(page)).toContainText('Showing 11 strikes · 24250 – 24750');

  await page.getByRole('button', { name: 'All', exact: true }).click();
  await expect(range(page)).toContainText('Showing 21 strikes · 24000 – 25000');
});

test('keeps the max-pain strike on the chart at every filter setting', async ({ page }) => {
  // Decision 2 of the plan, and the assertion most likely to catch a future
  // change: the window widens rather than dropping the marker.
  for (const label of ['All', '5', '10', '20']) {
    await page.getByRole('button', { name: label, exact: true }).click();

    const text = (await range(page).textContent()) ?? '';
    const [, low, high] = text.match(/·\s*(\d+)\s*–\s*(\d+)/) ?? [];
    expect(Number(low)).toBeLessThanOrEqual(24_400);
    expect(Number(high)).toBeGreaterThanOrEqual(24_400);
  }
});

test('cycles to another instrument', async ({ page }) => {
  await page.getByRole('button', { name: 'Next' }).click();

  await expect(page.getByText('SENSEX', { exact: true })).toBeVisible();
  // SENSEX: spot 80,250.75, ATM 80,300, max pain 80,100.
  await expect(
    panel(page, 'Market Sentiment (based on Max Pain)').getByText('80100.00', { exact: true })
  ).toBeVisible();
});

test('offers Live only, as the other Options Lab tools do', async ({ page }) => {
  await expect(page.getByRole('button', { name: 'Live', exact: true })).toBeEnabled();
  await expect(page.getByRole('button', { name: 'Historical', exact: true })).toBeDisabled();
});
