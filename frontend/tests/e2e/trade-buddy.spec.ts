import { expect, test } from '@playwright/test';
import { stubTradeBuddy } from './trade-buddy-fixtures';

/**
 * Trade Buddy end to end, against fulfilled API responses.
 *
 * The component suite already pins what the page does with its data. What it
 * cannot see is the real build in a real browser: that the layout survives a
 * phone, that the table is the thing that scrolls sideways rather than the
 * page, and that the answers a trader needs before acting — is the watch
 * running, where is price, will an alert reach me — are all on screen at once
 * without scrolling.
 */

test.beforeEach(async ({ context, baseURL }) => {
  await context.addCookies([
    { name: 'cn_session', value: 'test', url: baseURL ?? 'http://localhost:4173' }
  ]);
});

test('puts the whole live picture above the fold on a laptop', async ({ page }) => {
  await stubTradeBuddy(page);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/tools/trade-buddy', { waitUntil: 'networkidle' });

  // Everything that has to be readable without scrolling, because each one is
  // a precondition for trusting the rest.
  for (const item of [
    page.getByRole('region', { name: 'Watcher status' }),
    page.getByText('24,692.00').first(),
    page.getByRole('button', { name: /telegram ready/i }),
    page.getByText('2/20'),
    page.getByText('Touched 24,700.00')
  ]) {
    await expect(item).toBeInViewport();
  }
});

test('states the market is closed rather than showing a stale tick', async ({ page }) => {
  await stubTradeBuddy(page, { state: { market_open: false, last_tick_at: null } });
  await page.goto('/tools/trade-buddy', { waitUntil: 'networkidle' });

  await expect(page.getByText('Market closed')).toBeVisible();
  await expect(page.getByText(/Watching resumes at 09:15 IST/)).toBeVisible();
});

test('offers a way out of stale levels rather than only naming the problem', async ({ page }) => {
  await stubTradeBuddy(page);
  await page.goto('/tools/trade-buddy?symbol=BANKNIFTY', { waitUntil: 'networkidle' });

  const banner = page.getByRole('status', { name: /stale levels/i });
  await expect(banner.getByText(/These BANKNIFTY levels are from Wed 14 Jan/)).toBeVisible();
  await expect(banner.getByRole('button', { name: /carry forward/i })).toBeEnabled();
  // Nothing is watched, so no row may claim a state.
  await expect(page.getByText('Paused').first()).toBeVisible();
});

test('holds up at 390px with only the table scrolling sideways', async ({ page }) => {
  await stubTradeBuddy(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/tools/trade-buddy', { waitUntil: 'networkidle' });

  await expect(page.getByRole('heading', { name: 'Trade Buddy' })).toBeVisible();

  const pageOverflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth
  );
  expect(pageOverflow, 'the page itself must not scroll sideways').toBeLessThanOrEqual(0);

  // The table keeps its six columns and scrolls inside its own box: a stacked
  // card per level would lose the alignment that makes the prices comparable.
  const tableOverflow = await page.evaluate(() => {
    const box = document.querySelector('table')?.parentElement;
    return box ? box.scrollWidth - box.clientWidth : -1;
  });
  expect(tableOverflow, 'the table box is what scrolls').toBeGreaterThan(0);
});
