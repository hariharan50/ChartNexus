import { expect, test, type Page } from '@playwright/test';

/**
 * Only one nav entry may read as the current page.
 *
 * `/options` (Dashboards → Options) and `/options/*` (Options Lab) are separate
 * sections that happen to share a path prefix, so a `startsWith` match lit both
 * at once — the Dashboards submenu still highlighted "Options" while you were
 * on Open Interest.
 */

// The primary nav collapses below the tablet breakpoint, so there is no
// Dashboards summary to open and nothing here has a mobile equivalent yet.
test.skip(({ isMobile }) => Boolean(isMobile), 'the primary nav is hidden on phones');

// CSS Modules hashes the class, so match the stable part of the generated name.
const ACTIVE = /_active_/;

test.beforeEach(async ({ context, baseURL }) => {
  await context.addCookies([
    { name: 'cn_session', value: 'test', url: baseURL ?? 'http://localhost:4173' }
  ]);
});

/**
 * Opens a header menu and waits for it to stay open.
 *
 * The layout closes every `<details>` from a mount effect, so a click landing
 * before hydration opens the menu natively and hydration immediately shuts it
 * again. A human cannot click that fast; a test runner under load can, which is
 * what made these flaky. Retrying until it sticks beats a sleep.
 */
async function openMenu(page: Page, name: string) {
  const summary = page.locator('summary', { hasText: name });
  await expect(async () => {
    await summary.click();
    await expect(summary.locator('xpath=..')).toHaveAttribute('open', '', { timeout: 1000 });
  }).toPass({ timeout: 10_000 });
}

async function dashboardsOptionsEntry(page: Page) {
  await openMenu(page, 'Dashboards');
  return page.getByRole('link', { name: /^Options\b/ }).first();
}

test('a sub-page of Options Lab does not highlight Dashboards → Options', async ({ page }) => {
  await page.goto('/options/open-interest');

  const optionsEntry = await dashboardsOptionsEntry(page);
  await expect(optionsEntry).not.toHaveClass(ACTIVE);

  // The section that does own the page is still marked.
  await expect(page.locator('summary', { hasText: 'Options Lab' })).toHaveClass(ACTIVE);
});

test('the Options page itself still highlights Dashboards → Options', async ({ page }) => {
  await page.goto('/options');

  const optionsEntry = await dashboardsOptionsEntry(page);
  await expect(optionsEntry).toHaveClass(ACTIVE);

  // …and Options Lab is not, because /options is not one of its pages.
  await expect(page.locator('summary', { hasText: 'Options Lab' })).not.toHaveClass(ACTIVE);
});

test('the Dashboard page highlights only its own entry', async ({ page }) => {
  await page.goto('/dashboard');

  await page.locator('summary', { hasText: 'Dashboards' }).click();
  await expect(page.getByRole('link', { name: /^Dashboard\b/ }).first()).toHaveClass(ACTIVE);
  await expect(page.getByRole('link', { name: /^Options\b/ }).first()).not.toHaveClass(ACTIVE);
});

test('mega-menu items in a column all start at the same edge', async ({ page }) => {
  /**
   * `.primary-nav ul` was a descendant selector, so it also matched the `<ul>`
   * inside every mega-menu column and handed them `align-items: center`. The
   * items were then centred rather than stretched, and each one started at a
   * different x depending on how long its label was — a visible zig-zag.
   *
   * The same trap once hid the settings sub-nav via `.terminal nav`, so it is
   * worth a standing assertion rather than a comment.
   */
  await page.goto('/dashboard');
  await openMenu(page, 'Options Lab');

  const items = page.getByRole('link', { name: /Open Interest|Max Pain|Gamma Exposure/ });
  await expect(items).toHaveCount(3);

  const lefts = await items.evaluateAll((nodes) =>
    nodes.map((node) => Math.round(node.getBoundingClientRect().left))
  );

  expect(new Set(lefts).size, `items started at ${lefts.join(', ')}`).toBe(1);
});
