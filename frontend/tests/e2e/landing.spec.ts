import { expect, test } from '@playwright/test';

/**
 * The landing page at `/`.
 *
 * Most of it is static marketing that a test would only re-type. What is worth
 * pinning is the machinery: the drawer's accessibility contract, the CTA
 * destinations, the one piece of cross-widget state, and two structural rules
 * that are invisible until they break.
 */

test.describe('nav drawer', () => {
  // Below 62rem/992px, where the hamburger replaces the desktop row. Playwright
  // defaults to 1280px, at which the hamburger is correctly hidden.
  //
  // The drawer also needs JavaScript, so every test here waits for hydration
  // before clicking: a click landing on the server-rendered button before React
  // attaches its handler is dropped, which shows up as "dialog not found".
  test.beforeEach(async ({ page }) => {
    await page.setViewportSize({ width: 800, height: 900 });
    await page.goto('/', { waitUntil: 'networkidle' });
  });

  test('the hamburger reports and toggles its state', async ({ page }) => {
    const trigger = page.getByRole('button', { name: 'Menu', exact: true });

    await expect(trigger).toHaveAttribute('aria-expanded', 'false');
    await trigger.click();
    await expect(trigger).toHaveAttribute('aria-expanded', 'true');
    await expect(page.getByRole('dialog', { name: 'Site navigation' })).toBeVisible();
  });

  test('Escape closes it and focus returns to the hamburger', async ({ page }) => {
    const trigger = page.getByRole('button', { name: 'Menu', exact: true });

    await trigger.click();
    await page.keyboard.press('Escape');

    await expect(page.getByRole('dialog', { name: 'Site navigation' })).toBeHidden();
    await expect(trigger).toHaveAttribute('aria-expanded', 'false');
    await expect(trigger).toBeFocused();
  });

  test('clicking the backdrop closes it', async ({ page }) => {
    await page.getByRole('button', { name: 'Menu', exact: true }).click();
    await expect(page.getByRole('dialog', { name: 'Site navigation' })).toBeVisible();

    // A raw mouse click on the far left, which is backdrop — the panel is on
    // the right. `locator.click()` on the dialog runs actionability checks
    // against an element that fills the viewport, which is flaky under load.
    await page.mouse.click(8, 200);
    await expect(page.getByRole('dialog', { name: 'Site navigation' })).toBeHidden();
  });

  test('page scroll is locked while open and restored after', async ({ page }) => {
    const overflow = () => page.evaluate(() => document.body.style.overflow);

    await page.getByRole('button', { name: 'Menu', exact: true }).click();
    await expect.poll(overflow).toBe('hidden');

    await page.keyboard.press('Escape');
    await expect(page.getByRole('dialog', { name: 'Site navigation' })).toBeHidden();
    // Polled, not sampled once: Escape closes the dialog natively and React
    // only then re-renders and runs the effect cleanup that restores this, so a
    // single read races the unlock rather than testing it.
    await expect.poll(overflow).not.toBe('hidden');
  });

  test('following a link navigates and leaves the drawer closed', async ({ page }) => {
    const drawer = page.getByRole('dialog', { name: 'Site navigation' });

    await page.getByRole('button', { name: 'Menu', exact: true }).click();
    // Scoped to the drawer: "Sign in" also appears in the hero, the closing
    // band and the footer.
    await drawer.getByRole('link', { name: 'Sign in' }).click();

    await expect(page).toHaveURL('/login');
    await expect(drawer).toBeHidden();
  });
});

test('the calls to action point at register and sign-in', async ({ page }) => {
  await page.goto('/');
  const hero = page.locator('section').first();

  await expect(hero.getByRole('link', { name: 'Create free account' })).toHaveAttribute(
    'href',
    '/register'
  );
  await expect(hero.getByRole('link', { name: 'Sign in' })).toHaveAttribute('href', '/login');
});

test('switching index moves the chain in the hero', async ({ page }) => {
  // Also a click, so also after hydration — see the drawer block above.
  await page.goto('/', { waitUntil: 'networkidle' });

  const pcr = page.getByText('PCR (OI)').locator('..');
  const before = await pcr.innerText();

  await page.getByRole('tab', { name: 'BANK NIFTY' }).click();
  await expect(page.getByRole('tab', { name: 'BANK NIFTY' })).toHaveAttribute(
    'aria-selected',
    'true'
  );
  await expect(pcr).not.toHaveText(before);
});

test.describe('desktop navigation', () => {
  test.beforeEach(async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.goto('/', { waitUntil: 'networkidle' });
  });

  test('shows the links inline and hides the hamburger', async ({ page }) => {
    await expect(page.getByRole('button', { name: 'Menu', exact: true })).toBeHidden();
    await expect(page.getByRole('link', { name: 'Dashboard' }).first()).toBeVisible();
  });

  // Scoped to the nav throughout: the footer links to the same five tools.
  test('the tools menu opens, and Escape closes it', async ({ page }) => {
    const nav = page.getByRole('navigation', { name: 'Primary' });
    const item = nav.getByRole('link', { name: 'Gamma Exposure' });

    await nav.getByText('Options Lab', { exact: true }).click();
    await expect(item).toBeVisible();

    await page.keyboard.press('Escape');
    await expect(item).toBeHidden();
  });

  test('clicking outside closes the tools menu', async ({ page }) => {
    const nav = page.getByRole('navigation', { name: 'Primary' });
    const item = nav.getByRole('link', { name: 'Max Pain' });

    await nav.getByText('Options Lab', { exact: true }).click();
    await expect(item).toBeVisible();

    await page.locator('h1').click();
    await expect(item).toBeHidden();
  });
});

test('an FAQ row expands when clicked', async ({ page }) => {
  await page.goto('/', { waitUntil: 'networkidle' });

  const question = page.getByText('Can it place trades for me?');
  const answer = page.getByText(/there is no order, position or funds path/);

  await expect(answer).toBeHidden();
  await question.click();
  await expect(answer).toBeVisible();
});

test('the demo data is labelled simulated', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByText('Simulated').first()).toBeVisible();
});

/**
 * `root.tsx` renders `<main id="main">` around every route, so a route that
 * renders its own <main> nests two of them — an accessibility violation that
 * looks like nothing on screen.
 */
test('the page does not nest a second main landmark', async ({ page }) => {
  await page.goto('/');
  await expect(page.locator('#main main')).toHaveCount(0);
});

/** The dark-only pin has to hold under a stored light theme. */
test('it stays dark when the visitor has chosen a light theme', async ({ page, context }) => {
  await context.addInitScript(() => localStorage.setItem('mc-theme', 'light'));
  await page.goto('/');

  const background = await page
    .locator('#main > div')
    .first()
    .evaluate((el) => getComputedStyle(el).backgroundColor);

  // --mc-landing-bg #18191e. If the pin failed this would be the light theme's
  // near-white, and the headline would be near-black on near-black.
  expect(background).toBe('rgb(24, 25, 30)');
});
