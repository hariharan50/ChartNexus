import { expect, test, type Page } from '@playwright/test';

/**
 * Options Lab → Gamma Exposure.
 *
 * The profile is an ECharts canvas and opaque to Playwright, so the assertions
 * land on the DOM around it: the strike-range line, the levels row, the two
 * headline figures and the scrub label are all rendered from the same derived
 * values the chart draws. The arithmetic itself is covered by
 * `tests/unit/gex-data.test.ts`.
 *
 * The stub serves a 21-strike NIFTY ladder around ATM 24,500 at 50-point steps,
 * with the call wall pinned two strikes above and the put wall two below — so
 * every figure below is a fixed function of that payload.
 */

const STUB_API = `http://localhost:${process.env.STUB_API_PORT ?? 8099}`;

test.beforeEach(async ({ context, baseURL, page }) => {
  await context.addCookies([
    { name: 'mc_session', value: 'test', url: baseURL ?? 'http://localhost:4173' }
  ]);

  await page.route('**/api/v1/**', async (route) => {
    const url = new URL(route.request().url());
    const upstream = await route.fetch({ url: `${STUB_API}${url.pathname}${url.search}` });
    await route.fulfill({ response: upstream });
  });

  await page.goto('/options/gamma-exposure');
  // Generous: this page mounts an ECharts canvas, and under the suite's eight
  // parallel workers a first paint can genuinely take longer than the default.
  await expect(page.getByRole('heading', { name: 'Gamma Exposure', exact: true })).toBeVisible({
    timeout: 15_000
  });
});

const range = (page: Page) => page.getByText(/Showing \d+ strikes/);
const level = (page: Page, label: string) => page.getByRole('listitem').filter({ hasText: label });

test('draws the profile with both headline figures', async ({ page }) => {
  await expect(page.locator('canvas')).toBeVisible();

  // Both totals come off the scrubbed frame, in the unit the caption names.
  await expect(page.getByText(/Net GEX\s/).first()).toBeVisible();
  await expect(page.getByText(/ABS GEX\s/).first()).toBeVisible();
  await expect(page.getByText(/crore per 1% move in spot/)).toBeVisible();
});

test('reads the four levels off the current frame', async ({ page }) => {
  // The stub pins the walls two strikes either side of ATM 24,500.
  await expect(level(page, 'Call Wall')).toContainText('24,600');
  await expect(level(page, 'Put Wall')).toContainText('24,400');

  // The flip and the cross are separate levels and both are shown — collapsing
  // one into the other is the mistake this asserts against.
  await expect(level(page, 'Gamma Flip')).toContainText('24,475');
  await expect(level(page, 'Net GEX Cross')).toContainText('24,512.5');
});

test('the strike filter narrows what is drawn', async ({ page }) => {
  // Default is ±10, which spans the stub's whole 21-strike ladder.
  await expect(range(page)).toContainText('Showing 21 strikes · 24000 – 25000');

  await page.getByRole('button', { name: '5', exact: true }).click();
  await expect(range(page)).toContainText('Showing 11 strikes · 24250 – 24750');

  await page.getByRole('button', { name: 'All', exact: true }).click();
  await expect(range(page)).toContainText('Showing 21 strikes · 24000 – 25000');
});

test('switches between the three chart layouts', async ({ page }) => {
  const horizontal = page.getByRole('button', { name: 'Horizontal', exact: true });
  const vertical = page.getByRole('button', { name: 'Vertical', exact: true });
  const callPut = page.getByRole('button', { name: 'Call-Put', exact: true });

  await expect(horizontal).toHaveAttribute('aria-pressed', 'true');

  await vertical.click();
  await expect(vertical).toHaveAttribute('aria-pressed', 'true');
  await expect(horizontal).toHaveAttribute('aria-pressed', 'false');
  // The axes swap wholesale, so the chart has to survive the rebuild.
  await expect(page.locator('canvas')).toBeVisible();

  await callPut.click();
  await expect(callPut).toHaveAttribute('aria-pressed', 'true');
  await expect(page.locator('canvas')).toBeVisible();
});

test('the wall and flip toggles start off and can be switched on', async ({ page }) => {
  const walls = page.getByRole('checkbox', { name: 'Show Walls' });
  const flip = page.getByRole('checkbox', { name: 'Show Flip' });

  await expect(walls).not.toBeChecked();
  await expect(flip).not.toBeChecked();

  // Clicked by their labels: the inputs are visually hidden so the switch can
  // be drawn, which is also what makes them unclickable directly.
  await page.getByText('Show Walls', { exact: true }).click();
  await page.getByText('Show Flip', { exact: true }).click();

  await expect(walls).toBeChecked();
  await expect(flip).toBeChecked();
  // The levels stay legible whichever way the toggles sit — that is the whole
  // reason the row exists beside the canvas.
  await expect(level(page, 'Call Wall')).toContainText('24,600');
});

test('the eye chips hide and restore each series', async ({ page }) => {
  const net = page.getByRole('button', { name: /Net GEX \(Cr\)/ });
  const abs = page.getByRole('button', { name: /ABS GEX \(Cr\)/ });

  await expect(net).toHaveAttribute('aria-pressed', 'true');
  await expect(abs).toHaveAttribute('aria-pressed', 'true');

  await net.click();
  await expect(net).toHaveAttribute('aria-pressed', 'false');
  await expect(page.locator('canvas')).toBeVisible();

  await net.click();
  await expect(net).toHaveAttribute('aria-pressed', 'true');
});

test('the timeline spans the trading session, not just what was recorded', async ({ page }) => {
  // The left edge is the bell, always. An index-positioned track would label
  // it with the first capture, so a day that started archiving at 1 pm would
  // read as a complete session.
  await expect(page.getByText('9:15 am', { exact: true })).toBeVisible();
  await expect(page.getByText(/timeline spans the 9:15 am – 3:30 pm session/)).toBeVisible();

  const hours = page.locator('[class*="tickLabel"]');
  await expect(hours).toHaveText(['10 am', '11 am', '12 pm', '1 pm', '2 pm', '3 pm']);
});

test('scrubbing the timeline moves the as-of reading, and Reset returns to live', async ({
  page
}) => {
  const scrub = page.getByRole('slider', { name: 'As-of time' });
  // Single-handle: there is no baseline thumb to grab by mistake.
  await expect(page.getByRole('slider', { name: 'Baseline time' })).toHaveCount(0);

  const live = await scrub.getAttribute('aria-valuenow');

  await scrub.focus();
  await page.keyboard.press('Home');
  await expect(scrub).toHaveAttribute('aria-valuenow', '0');
  expect(await scrub.getAttribute('aria-valuenow')).not.toBe(live);

  await page.getByRole('button', { name: 'Reset' }).click();
  await expect(scrub).toHaveAttribute('aria-valuenow', String(live));
});

test('collapses and restores the settings sidebar', async ({ page }) => {
  const settings = page.getByRole('heading', { name: 'Settings' });
  await expect(settings).toBeVisible();

  await page.getByRole('button', { name: 'Collapse settings' }).click();
  await expect(settings).toBeHidden();

  await page.getByRole('button', { name: 'Show settings' }).click();
  await expect(settings).toBeVisible();
});

test('exports the visible strikes as CSV', async ({ page }) => {
  await page.getByRole('button', { name: '5', exact: true }).click();
  await expect(range(page)).toContainText('Showing 11 strikes');

  const [download] = await Promise.all([
    page.waitForEvent('download'),
    page.getByRole('button', { name: '↓ CSV' }).click()
  ]);

  expect(download.suggestedFilename()).toMatch(/^gex-NIFTY-\d{4}-\d{2}-\d{2}-\d{4}\.csv$/);

  const stream = await download.createReadStream();
  const chunks: Buffer[] = [];
  for await (const chunk of stream) chunks.push(Buffer.from(chunk));
  const lines = Buffer.concat(chunks).toString('utf8').trim().split('\n');

  // The export follows the filter, not the payload: a stamp, a header and the
  // eleven rows currently on screen.
  expect(lines[1]).toBe('strike,call_gex_cr,put_gex_cr,net_gex_cr,abs_gex_cr');
  expect(lines).toHaveLength(13);
});

test('cycles to another instrument', async ({ page }) => {
  await page.getByRole('button', { name: 'Next' }).click();

  await expect(page.getByText('SENSEX', { exact: true })).toBeVisible();
  // SENSEX ladders at 100 points, so its walls sit 200 either side of 80,300.
  await expect(level(page, 'Call Wall')).toContainText('80,500');
});

test('offers Live only, as the other Options Lab tools do', async ({ page }) => {
  await expect(page.getByRole('button', { name: 'Live', exact: true })).toBeEnabled();
  await expect(page.getByRole('button', { name: 'Historical', exact: true })).toBeDisabled();
});
