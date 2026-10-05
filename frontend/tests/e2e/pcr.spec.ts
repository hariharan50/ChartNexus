import { expect, test, type Page } from '@playwright/test';

/**
 * Options Lab → Put-Call Ratio.
 *
 * The charts are ECharts canvases and opaque to Playwright, so the assertions
 * land on the DOM around them and on the network. Both are sound proxies: the
 * legends are built from the same derived arrays the charts draw, and the whole
 * point of resampling on the client is that it makes no request.
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
    const upstream = await route.fetch({ url: `${STUB_API}${url.pathname}${url.search}` });
    await route.fulfill({ response: upstream });
  });

  await page.goto('/options/pcr');
  // Generous: this page mounts ECharts canvases, and under the suite's eight
  // parallel workers a first paint can genuinely take longer than the 5s
  // default. A slow mount is not the same as a broken page.
  await expect(page.getByRole('heading', { name: 'Put-Call Ratio', exact: true })).toBeVisible({
    timeout: 15_000
  });
});

const panel = (page: Page, title: string) =>
  page.locator('section').filter({ has: page.getByRole('heading', { name: title, exact: true }) });

test('stacks the ratio above both call-versus-put views', async ({ page }) => {
  await expect(page.getByRole('heading', { name: 'Put-Call Ratio', exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'OI Change (Call vs Put)' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Total OI (Call vs Put)' })).toBeVisible();
});

test('each chart names its two sides and the futures overlay', async ({ page }) => {
  await expect(page.getByRole('button', { name: 'Future' })).toHaveCount(3);

  const change = panel(page, 'OI Change (Call vs Put)');
  await expect(change.getByRole('button', { name: 'Call OI Change' })).toBeVisible();
  await expect(change.getByRole('button', { name: 'Put OI Change' })).toBeVisible();

  const totals = panel(page, 'Total OI (Call vs Put)');
  await expect(totals.getByRole('button', { name: 'Call OI', exact: true })).toBeVisible();
  await expect(totals.getByRole('button', { name: 'Put OI', exact: true })).toBeVisible();
});

test('changing the timeframe resamples without a network request', async ({ page }) => {
  // The reason the endpoint sends the raw cadence at all. If this ever starts
  // refetching, the client-side bucketing has quietly stopped earning its keep.
  const calls: string[] = [];
  page.on('request', (request) => {
    if (request.url().includes('/pcr-series/')) calls.push(request.url());
  });

  await expect(page.getByText(/resampled to 1m|baseline is derived/)).toBeVisible();
  const before = calls.length;

  await page.getByLabel('Timeframe').selectOption('15m');
  await expect(page.getByText(/resampled to 15m/)).toBeVisible();

  expect(calls.length, `unexpected refetch: ${calls.slice(before).join(', ')}`).toBe(before);
});

test('1D is offered but not selectable until multi-day history exists', async ({ page }) => {
  const option = page.locator('option[value="1D"]');

  await expect(option).toHaveCount(1);
  // The attribute rather than `toBeDisabled()`: Playwright's enabled-state
  // check does not cover `<option>`.
  await expect(option).toHaveAttribute('disabled', '');
});

test('Day-wise PCR is shown but inert', async ({ page }) => {
  const button = page.getByRole('button', { name: /Day-wise PCR/ });

  await expect(button).toBeVisible();
  await expect(button).toBeDisabled();
});

test('Replay sweeps the charts and hands them back', async ({ page }) => {
  // The sweep takes ~15s by design, so this one needs more than the default.
  test.setTimeout(60_000);

  const replay = page.getByRole('checkbox', { name: 'Replay' });
  // The input is visually hidden behind its switch, so click the label — which
  // is what a person does anyway.
  const label = page.getByText('Replay', { exact: true });

  await expect(replay).not.toBeChecked();
  await label.click();
  await expect(replay).toBeChecked();

  // The sweep finishes on its own and releases the charts back to live.
  await expect(replay).not.toBeChecked({ timeout: 30_000 });
});

test('hiding a side marks its legend entry off', async ({ page }) => {
  const entry = panel(page, 'Total OI (Call vs Put)').getByRole('button', {
    name: 'Call OI',
    exact: true
  });

  await expect(entry).toHaveAttribute('aria-pressed', 'true');
  await entry.click();
  await expect(entry).toHaveAttribute('aria-pressed', 'false');
});

test('the sidebar carries no strike pickers', async ({ page }) => {
  // These are chain-wide totals; there is nothing per-strike to choose.
  const sidebar = page.locator('aside');

  await expect(sidebar.getByText('Timeframe', { exact: true })).toBeVisible();
  await expect(sidebar.getByText('High OI', { exact: true })).toHaveCount(0);
  await expect(sidebar.getByText('Custom Strikes', { exact: true })).toHaveCount(0);
});
