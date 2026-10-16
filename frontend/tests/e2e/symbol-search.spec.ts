import { expect, test } from '@playwright/test';

/**
 * The header symbol search, end to end.
 *
 * The box sat in the header for months as an uncontrolled `<input>` inside a
 * form whose only handler was `preventDefault()` — it looked exactly like a
 * working search and did nothing at all. These tests are the standing proof
 * that typing a ticker reaches a chart of that ticker.
 *
 * Where a result lands depends on what it is: an index opens the Options Lab
 * view, where the OI line sums the whole chain; a stock opens Future Lab,
 * which charts the front-month future against its own open interest.
 */

// The header search is in `.nav-right`, which survives the tablet collapse,
// but the dropdown is too narrow to assert against on a phone viewport.
test.skip(({ isMobile }) => Boolean(isMobile), 'the header search needs a desktop viewport');

const SEARCH = 'Search symbol';
const STUB_API = `http://localhost:${process.env.STUB_API_PORT ?? 8099}`;

test.beforeEach(async ({ context, baseURL, page }) => {
  await context.addCookies([
    { name: 'cn_session', value: 'test', url: baseURL ?? 'http://localhost:4173' }
  ]);

  // The catalog is fetched from the browser, and the app server has no
  // `/api/v1` route to proxy it. Forward those to the same stub the loaders
  // use, as the other data-page specs do.
  await page.route('**/api/v1/**', async (route) => {
    const url = new URL(route.request().url());
    try {
      const upstream = await route.fetch({ url: `${STUB_API}${url.pathname}${url.search}` });
      await route.fulfill({ response: upstream });
    } catch {
      // Picking a symbol navigates, which is the point of this spec — and a
      // request still in flight when the page leaves has its response disposed
      // underneath us. Nothing is waiting on it by then, so swallowing it is
      // correct; letting it throw would make every test here flaky.
      await route.abort().catch(() => {});
    }
  });
});

test('typing a ticker lists it, and picking it charts it', async ({ page }) => {
  await page.goto('/dashboard');

  const box = page.getByRole('combobox', { name: SEARCH });
  await box.click();
  await box.fill('ITC');

  // The exact ticker ranks above the longer symbol that starts with it.
  const options = page.getByRole('option');
  await expect(options.first()).toContainText('ITC');
  await expect(options.first()).toContainText('ITC LTD');

  await options.first().click();

  // A stock lands on the futures view, carrying the symbol in the URL.
  await expect(page).toHaveURL(/\/future-lab\/price-vs-oi\?symbol=ITC$/);
  await expect(page.getByText('ITC LTD')).toBeVisible();
});

test('Enter opens the top hit without touching the mouse', async ({ page }) => {
  await page.goto('/dashboard');

  const box = page.getByRole('combobox', { name: SEARCH });
  await box.click();
  await box.fill('ITC');
  await expect(page.getByRole('option').first()).toBeVisible();
  await box.press('Enter');

  await expect(page).toHaveURL(/\/future-lab\/price-vs-oi\?symbol=ITC$/);
});

test('the arrow keys move the choice', async ({ page }) => {
  await page.goto('/dashboard');

  const box = page.getByRole('combobox', { name: SEARCH });
  await box.click();
  await box.fill('ITC');
  await expect(page.getByRole('option')).toHaveCount(2);

  // Down moves off the exact match onto ITCHOTELS.
  await box.press('ArrowDown');
  await expect(page.getByRole('option').nth(1)).toHaveAttribute('aria-selected', 'true');
  await box.press('Enter');

  await expect(page).toHaveURL(/\/future-lab\/price-vs-oi\?symbol=ITCHOTELS$/);
});

test('an index goes to the Options Lab view instead', async ({ page }) => {
  await page.goto('/dashboard');

  const box = page.getByRole('combobox', { name: SEARCH });
  await box.click();
  await box.fill('BANKNIFTY');
  await page.getByRole('option').first().click();

  await expect(page).toHaveURL(/\/options\/price-vs-oi\?symbol=BANKNIFTY$/);

  // The page has to actually adopt the symbol, not merely carry it in the URL.
  // This used to be an integer index into a hardcoded three, so a link could
  // not reach it at all. The sidebar reads the catalog, so it is the honest
  // assertion here — the chart itself needs a series the stub does not serve.
  await expect(page.getByTitle('NIFTYBANK')).toHaveText('BANKNIFTY');
});

test('a symbol nobody trades says so rather than going quiet', async ({ page }) => {
  await page.goto('/dashboard');

  const box = page.getByRole('combobox', { name: SEARCH });
  await box.click();
  await box.fill('DOGECOIN');

  await expect(page.getByText(/Nothing matches/)).toBeVisible();
  await expect(page.getByRole('option')).toHaveCount(0);
});

test('Escape closes the list and leaves the page alone', async ({ page }) => {
  await page.goto('/dashboard');

  const box = page.getByRole('combobox', { name: SEARCH });
  await box.click();
  await box.fill('ITC');
  await expect(page.getByRole('option').first()).toBeVisible();

  await box.press('Escape');

  await expect(page.getByRole('option')).toHaveCount(0);
  await expect(page).toHaveURL(/\/dashboard$/);
});

/**
 * The link has to work on its own, not just as the search's last step —
 * that is the whole point of putting the symbol in the URL rather than in
 * component state.
 */
test('a pasted link opens straight onto that symbol', async ({ page }) => {
  await page.goto('/future-lab/price-vs-oi?symbol=ITC');

  await expect(page.getByText('ITC LTD')).toBeVisible();
});
