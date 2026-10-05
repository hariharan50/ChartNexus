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
    // Scoped to the drawer: "Log in" also appears in the desktop nav actions.
    await drawer.getByRole('link', { name: 'Log in' }).click();

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

    const nav = page.getByRole('navigation', { name: 'Primary' });
    await expect(nav.getByRole('link', { name: 'Features' })).toBeVisible();
    await expect(nav.getByRole('link', { name: 'Coverage' })).toBeVisible();
  });

  test('the header actions point at sign-in and register', async ({ page }) => {
    // Scoped to the header bar so the hero/footer CTAs do not match.
    const bar = page.locator('header');
    await expect(bar.getByRole('link', { name: 'Log in' })).toHaveAttribute('href', '/login');
    await expect(bar.getByRole('link', { name: 'Get started' })).toHaveAttribute(
      'href',
      '/register'
    );
  });

  test('a nav link navigates to its own page', async ({ page }) => {
    await page
      .getByRole('navigation', { name: 'Primary' })
      .getByRole('link', { name: 'Coverage' })
      .click();
    await expect(page).toHaveURL(/\/coverage$/);
    await expect(
      page.getByRole('heading', { name: 'The tools that are live, not a roadmap.' })
    ).toBeVisible();
  });
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
  await context.addInitScript(() => localStorage.setItem('cn-theme', 'light'));
  await page.goto('/');

  const background = await page
    .locator('#main > div')
    .first()
    .evaluate((el) => getComputedStyle(el).backgroundColor);

  // The landing pins its own charcoal (#131313) inside `.landing`. If the pin
  // failed this would be the light theme's near-white, and the headline would
  // be near-black on near-black.
  expect(background).toBe('rgb(19, 19, 19)');
});
