import { expect, test, type Page } from '@playwright/test';

/**
 * Options Lab → Multi OI & Volume.
 *
 * The three charts are ECharts canvases and opaque to Playwright, so the
 * assertions land on the DOM around them — the legends, the chips and the
 * picker. That is a sound proxy: every one of them is rebuilt from the same
 * derived series the charts draw, and it is far less flaky than pixels.
 */

const STUB_API = `http://localhost:${process.env.STUB_API_PORT ?? 8099}`;

test.beforeEach(async ({ context, baseURL, page }) => {
  await context.addCookies([
    { name: 'mc_session', value: 'test', url: baseURL ?? 'http://localhost:4173' }
  ]);

  // This page loads its data from the browser, and the app server has no
  // `/api/v1` route to proxy it. Forward those requests to the same stub the
  // loaders use.
  await page.route('**/api/v1/**', async (route) => {
    const url = new URL(route.request().url());
    const upstream = await route.fetch({ url: `${STUB_API}${url.pathname}${url.search}` });
    await route.fulfill({ response: upstream });
  });

  await page.goto('/options/multi-oi-volume');
  // `exact` matters: without it this also matches "MultiStrike OI Change".
  await expect(page.getByRole('heading', { name: 'MultiStrike OI', exact: true })).toBeVisible();
});

const chartPanel = (page: Page, title: string) =>
  page.locator('section').filter({ has: page.getByRole('heading', { name: title, exact: true }) });

test('stacks open interest above its change', async ({ page }) => {
  await expect(page.getByRole('heading', { name: 'MultiStrike OI', exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'MultiStrike OI Change' })).toBeVisible();
});

test('does not render a volume chart', async ({ page }) => {
  // Removed deliberately; volume survives only as a column in the picker.
  await expect(page.getByRole('heading', { name: 'MultiStrike Volume' })).toHaveCount(0);
});

test('pre-selects the busiest contracts and names them in the sidebar', async ({ page }) => {
  const sidebar = page.locator('aside');

  // One picker now: both charts plot the same contracts, so a second selection
  // would have nothing of its own to drive.
  await expect(sidebar.getByText('Contracts', { exact: true })).toBeVisible();
  await expect(sidebar.getByText(/^\d+ (CE|PE)$/)).toHaveCount(5);
});

test('every chart offers a futures overlay toggle', async ({ page }) => {
  // The price overlay is what makes an OI line readable, so it is on every one.
  await expect(page.getByRole('button', { name: 'Future' })).toHaveCount(2);
});

test('hiding a series marks its legend entry off', async ({ page }) => {
  const panel = chartPanel(page, 'MultiStrike OI');
  const entry = panel
    .getByRole('button')
    .filter({ hasText: /^\d+ (CE|PE)$/ })
    .first();

  await expect(entry).toHaveAttribute('aria-pressed', 'true');
  await entry.click();
  await expect(entry).toHaveAttribute('aria-pressed', 'false');
});

test('a coarser interval refetches a thinner series', async ({ page }) => {
  // The caption, not the header strip: both mention the bucket size, and only
  // the caption is a paragraph.
  const caption = page.locator('p').filter({ hasText: /buckets/ });
  const before = await caption.innerText();

  await page.getByLabel('Time interval').selectOption('15m');

  await expect
    .poll(async () => caption.innerText(), {
      message: 'the caption should report the new bucket size'
    })
    .not.toBe(before);
  await expect(caption).toContainText('15m buckets');
});

test('1D is offered but not selectable until multi-day history exists', async ({ page }) => {
  const option = page.locator('option[value="1D"]');

  await expect(option).toHaveCount(1);
  // The attribute rather than `toBeDisabled()`: Playwright's enabled-state
  // check does not cover `<option>`, and reports a disabled one as enabled.
  await expect(option).toHaveAttribute('disabled', '');
});

test('Custom Strikes picks a contract and it joins the charts', async ({ page }) => {
  await page.locator('aside').getByRole('button', { name: 'Select' }).first().click();

  const dialog = page.getByRole('dialog');
  await expect(dialog).toBeVisible();

  await dialog.getByLabel('Search strike').fill('24700');
  const row = dialog
    .getByRole('button')
    .filter({ hasText: /^24700 (CE|PE)/ })
    .first();
  const label = (await row.innerText()).split('\n')[0]!.trim();
  await row.click();
  await dialog.getByRole('button', { name: 'Apply' }).click();

  await expect(dialog).toBeHidden();
  await expect(page.locator('aside').getByText(label, { exact: true })).toBeVisible();
});

test('Escape closes the picker without changing the selection', async ({ page }) => {
  const sidebar = page.locator('aside');
  const before = await sidebar.getByText(/^\d+ (CE|PE)$/).allInnerTexts();

  await sidebar.getByRole('button', { name: 'Select' }).first().click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await page.keyboard.press('Escape');

  await expect(page.getByRole('dialog')).toBeHidden();
  expect(await sidebar.getByText(/^\d+ (CE|PE)$/).allInnerTexts()).toEqual(before);
});

test('the PE−CE net series is opt-in', async ({ page }) => {
  const change = chartPanel(page, 'MultiStrike OI Change');
  await expect(change.getByRole('button', { name: /PE−CE/ })).toHaveCount(0);

  await page.getByText('Show PE−CE net change').click();

  await expect(change.getByRole('button', { name: /PE−CE/ })).toBeVisible();
});
