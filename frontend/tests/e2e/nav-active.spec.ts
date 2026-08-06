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
    { name: 'mc_session', value: 'test', url: baseURL ?? 'http://localhost:4173' }
  ]);
});

/** Opens the Dashboards menu and returns its "Options" entry. */
async function dashboardsOptionsEntry(page: Page) {
  await page.locator('summary', { hasText: 'Dashboards' }).click();
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
