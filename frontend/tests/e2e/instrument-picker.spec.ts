import { expect, test, type Page } from '@playwright/test';

/**
 * The Options Lab instrument picker.
 *
 * Every page here used to cycle three hardcoded symbols with ‹ › arrows, and
 * held the choice in its own `useState`. So the other ~218 contracts were
 * unreachable, and walking from one tab to the next quietly put you back on
 * NIFTY. These tests pin the two halves of the fix: the whole catalog is
 * reachable, and a choice survives the walk.
 */

const STUB_API = `http://localhost:${process.env.STUB_API_PORT ?? 8099}`;

// The settings sidebar collapses below the tablet breakpoint.
test.skip(({ isMobile }) => Boolean(isMobile), 'the settings sidebar needs a desktop viewport');

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
      // These tests navigate, and a request still in flight when the page
      // leaves has its response disposed underneath us.
      await route.abort().catch(() => {});
    }
  });
});

/** Open the sidebar picker and choose `symbol` through the search box. */
async function choose(page: Page, symbol: string) {
  await page.getByRole('button', { name: /Previous instrument/ }).waitFor();
  // The trigger carries the current ticker; the cyclers sit beside it.
  await page.locator('button[aria-haspopup="listbox"]').first().click();
  const search = page.getByRole('combobox', { name: 'Search instruments' });
  await search.fill(symbol);
  await page
    .getByRole('option', { name: new RegExp(`^${symbol}\\b`) })
    .first()
    .click();
}

test('reaches a stock the hardcoded three never offered', async ({ page }) => {
  await page.goto('/options/open-interest');

  await choose(page, 'ITC');

  await expect(page).toHaveURL(/\/options\/open-interest\?symbol=ITC$/);
  await expect(page.locator('button[aria-haspopup="listbox"]').first()).toContainText('ITC');
});

test('groups the list into indices and stocks', async ({ page }) => {
  await page.goto('/options/open-interest');

  await page.locator('button[aria-haspopup="listbox"]').first().click();

  await expect(page.getByText('Indices', { exact: true })).toBeVisible();
  await expect(page.getByText(/^Stocks — \(\d+\)$/)).toBeVisible();
});

test('finds an instrument by company name, not just ticker', async ({ page }) => {
  await page.goto('/options/open-interest');

  await page.locator('button[aria-haspopup="listbox"]').first().click();
  await page.getByRole('combobox', { name: 'Search instruments' }).fill('RELIANCE INDUSTRIES');

  await expect(page.getByRole('option').first()).toContainText('RELIANCE');
});

/**
 * The reason the selection moved out of per-page `useState`: a reader who has
 * chosen ITC is studying ITC, and the next tab should know that.
 */
test('the choice follows you to another Options Lab tab', async ({ page }) => {
  await page.goto('/options/open-interest');
  await choose(page, 'ITC');

  // Through the real menu, as a reader would — not by typing a URL.
  await page.locator('summary', { hasText: 'Options Lab' }).click();
  await page.getByRole('link', { name: /^Put-Call Ratio/ }).click();

  await expect(page).toHaveURL(/\/options\/pcr(\?symbol=ITC)?$/);
  await expect(page.locator('button[aria-haspopup="listbox"]').first()).toContainText('ITC');
});

test('the choice survives a reload', async ({ page }) => {
  await page.goto('/options/open-interest');
  await choose(page, 'ITC');

  await page.goto('/options/max-pain');

  await expect(page.locator('button[aria-haspopup="listbox"]').first()).toContainText('ITC');
});

/**
 * Honesty about the data behind a stock.
 *
 * Gamma is computed from archived chain snapshots and only indices are
 * archived, so this panel is empty for ITC and always will be under the
 * current ingest settings. Telling the reader it "fills in shortly" — which is
 * what every page said before — leaves them waiting for nothing.
 */
test('a capture-only page says why it is empty for a stock', async ({ page }) => {
  await page.goto('/options/gamma-exposure?symbol=ITC');

  // Scoped to the message itself: "Open Interest" is also a nav label.
  const message = page.getByText(/only indices are captured/);
  await expect(message).toBeVisible();
  await expect(message).toContainText('ITC');
  // It must point somewhere useful rather than just refusing.
  await expect(message).toContainText('Open Interest');
  await expect(page.getByText(/fills in as the ingest worker/)).toBeHidden();
});

test('an index still reads as waiting for today, not as unsupported', async ({ page }) => {
  await page.goto('/options/gamma-exposure?symbol=NIFTY');

  // NIFTY has captures in the stub, so the profile draws rather than explaining
  // itself — the empty copy must not have leaked onto the index path.
  await expect(page.getByText(/only indices are captured/)).toBeHidden();
});
