import { expect, test, type Locator, type Page } from '@playwright/test';

/**
 * Scrubbing the Open Interest timeline changes what the page shows.
 *
 * The bug this feature fixes was never in the slider — it was that the API had
 * only two data points to give it. So the assertion that matters is not "the
 * handle moved" (already covered by the component suite) but "the numbers the
 * page reports changed as a result".
 *
 * The chart is an ECharts canvas and opaque to Playwright, so the panels around
 * it stand in for it. That is a sound proxy: they are re-derived from the same
 * chosen frames as the bars, and it is far less flaky than pixel comparison.
 */

const STUB_API = `http://localhost:${process.env.STUB_API_PORT ?? 8099}`;

test.beforeEach(async ({ context, baseURL, page }) => {
  await context.addCookies([
    { name: 'mc_session', value: 'test', url: baseURL ?? 'http://localhost:4173' }
  ]);

  // `API_INTERNAL_URL` only redirects the *server's* fetches. This page loads
  // its data from the browser via react-query, and the app server has no
  // `/api/v1` route to proxy it, so those requests 404. Forward them to the same
  // stub the loaders use. `route.fetch` runs outside the page, so no CORS
  // headers are needed on the stub; fulfilling makes the response same-origin.
  await page.route('**/api/v1/**', async (route) => {
    const url = new URL(route.request().url());
    const upstream = await route.fetch({ url: `${STUB_API}${url.pathname}${url.search}` });
    await route.fulfill({ response: upstream });
  });

  await page.goto('/options/open-interest');
  await expect(page.getByRole('slider', { name: 'Baseline time' })).toBeVisible();
});

const baselineThumb = (page: Page) => page.getByRole('slider', { name: 'Baseline time' });
const asOfThumb = (page: Page) => page.getByRole('slider', { name: 'As-of time' });

/** One of the three summary panels below the chart, by its heading. */
function panel(page: Page, heading: string): Locator {
  return page
    .locator('section')
    .filter({ has: page.getByRole('heading', { name: heading, exact: true }) });
}

/**
 * Drag from one fraction of the track to another.
 *
 * Expressed as track fractions rather than "grab this thumb" for two reasons.
 * The thumbs are `pointer-events: none` — the track owns the whole gesture and
 * picks whichever handle is nearer the press — so the press has to land on the
 * side of the handle you mean. And the end thumbs overhang the track by half
 * their width, so pressing at a thumb's centre can land a pixel outside the
 * element that listens.
 *
 * Stepped rather than jumped: a single `mouse.move` can be swallowed by pointer
 * capture, which makes this flaky in exactly the way the feature it covers
 * used to be.
 */
async function drag(page: Page, from: number, to: number) {
  const track = page.locator('[role="presentation"]');
  // `page.mouse` works in viewport coordinates, and on a phone-sized viewport
  // the slider sits well below the fold — the press would land on whatever
  // happens to be on screen at that offset instead.
  await track.scrollIntoViewIfNeeded();

  const box = await track.boundingBox();
  if (!box) throw new Error('slider track has no layout');

  const y = box.y + box.height / 2;
  const at = (fraction: number) =>
    box.x + Math.min(box.width - 1, Math.max(1, box.width * fraction));

  await page.mouse.move(at(from), y);
  await page.mouse.down();
  for (let step = 1; step <= 10; step++) {
    await page.mouse.move(at(from + ((to - from) * step) / 10), y);
  }
  await page.mouse.up();
}

test('the session runs from the open to the close', async ({ page }) => {
  await expect(page.getByText('Baseline', { exact: true })).toBeVisible();
  await expect(page.getByText('As of', { exact: true })).toBeVisible();

  await expect(baselineThumb(page)).toHaveAttribute('aria-valuetext', '9:15 am');
  await expect(asOfThumb(page)).toHaveAttribute('aria-valuetext', '3:30 pm');
});

test('the hour ticks span the trading day', async ({ page }) => {
  const axis = page.locator('[aria-hidden="true"]').filter({ hasText: '9 am' });

  await expect(axis).toContainText('9 am');
  await expect(axis).toContainText('12 pm');
  await expect(axis).toContainText('3 pm');
});

test('a full session says nothing apologetic about the data', async ({ page }) => {
  // The "coarse timeline" caption is for the starved tiers only. Qualifying a
  // real session teaches people to ignore the caption.
  await expect(page.getByText(/timeline is coarse/)).toHaveCount(0);
  await expect(page.getByText(/Live estimate/)).toHaveCount(0);
});

test('moving the baseline handle changes the reported build-up', async ({ page }) => {
  // The baseline is what "change" is measured *from*, so this is the panel it
  // moves. Total OI is a property of the as-of end and is checked below.
  const changePanel = panel(page, 'Open Interest Change');
  const before = await changePanel.innerText();

  await drag(page, 0, 0.5);

  await expect(baselineThumb(page)).not.toHaveAttribute('aria-valuetext', '9:15 am');
  await expect
    .poll(async () => changePanel.innerText(), {
      message: 'the summary panels should re-derive from the new window'
    })
    .not.toBe(before);
});

test('moving the as-of handle changes the reported totals', async ({ page }) => {
  const totalPanel = panel(page, 'Total Open Interest');
  const before = await totalPanel.innerText();

  await drag(page, 1, 0.3);

  await expect
    .poll(async () => totalPanel.innerText(), {
      message: 'total OI should be read from the frame being shown'
    })
    .not.toBe(before);
});

test('moving the as-of handle rewinds the page to an earlier moment', async ({ page }) => {
  // The literal request: it is 15:30, show me how open interest stood at ~11.
  await drag(page, 1, 0.28);

  const asOf = await asOfThumb(page).getAttribute('aria-valuetext');
  expect(asOf).toMatch(/(10|11):\d\d am/);

  // The caption reads back the window, so it is the cheapest proof the whole
  // page — not just the handle — is looking at the earlier moment.
  await expect(page.getByText(new RegExp(`to ${asOf!.replace(/\s/g, '\\s')}`))).toBeVisible();
});

test('Reset returns the window to the whole session', async ({ page }) => {
  await drag(page, 1, 0.3);
  await expect(asOfThumb(page)).not.toHaveAttribute('aria-valuetext', '3:30 pm');

  await page.getByRole('button', { name: 'Reset' }).click();

  await expect(asOfThumb(page)).toHaveAttribute('aria-valuetext', '3:30 pm');
  await expect(baselineThumb(page)).toHaveAttribute('aria-valuetext', '9:15 am');
});

test('the keyboard can scrub without a pointer', async ({ page }) => {
  await asOfThumb(page).focus();
  await page.keyboard.press('PageDown');

  // Ten frames back at the 3-minute cadence is half an hour.
  await expect(asOfThumb(page)).toHaveAttribute('aria-valuetext', '3:00 pm');
});

/** The IST date-and-time span in the header readout. */
const clock = (page: Page) => page.getByText(/^\d+ \w{3}, \d+:\d\d:\d\d [ap]m IST$/);

test('the header states the date, the clock and how fresh the data is', async ({ page }) => {
  // Not decoration: a page that polls faithfully and receives identical bytes
  // looks exactly like one that has stopped. This readout is the difference.
  await expect(clock(page)).toBeVisible();
  await expect(page.getByText('15s', { exact: true })).toBeVisible();
  await expect(page.getByText(/^updated (just now|\d+[smh] ago)$/)).toBeVisible();
});

test('the clock ticks', async ({ page }) => {
  const first = await clock(page).innerText();

  await expect
    .poll(async () => clock(page).innerText(), { message: 'the IST clock should advance' })
    .not.toBe(first);
});
