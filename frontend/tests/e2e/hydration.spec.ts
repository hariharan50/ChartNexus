import { expect, test, type Page } from '@playwright/test';

/**
 * Hydration must be silent.
 *
 * React Router hydrates the whole `document`, so the pre-paint theme script in
 * root.tsx mutates attributes on an element React owns — a mismatch React will
 * warn about and, worse, may recover from by re-rendering the tree. SvelteKit
 * never had this exposure: its `<html>` lived in `app.html`, outside the
 * hydration root.
 *
 * This asserts the console is clean both with and without a stored preference,
 * because the bug only appears once the script actually changes something.
 */

const IGNORED = [
  // The dev proxy has nothing to talk to unless the API is running; unrelated
  // to hydration and absent in CI, where the stub API answers.
  'Failed to load resource',
  'ECONNREFUSED'
];

async function consoleErrors(page: Page, path: string): Promise<string[]> {
  const errors: string[] = [];
  page.on('console', (msg) => {
    if (msg.type() !== 'error') return;
    const text = msg.text();
    if (IGNORED.some((skip) => text.includes(skip))) return;
    errors.push(text);
  });
  page.on('pageerror', (err) => errors.push(String(err)));

  await page.goto(path, { waitUntil: 'networkidle' });
  return errors;
}

test('hydrates without warnings on the server default theme', async ({ page }) => {
  const errors = await consoleErrors(page, '/login');
  expect(errors.join('\n')).toBe('');
});

test('hydrates without warnings when a stored theme differs from the server', async ({
  page,
  context
}) => {
  // The interesting case: the bootstrap rewrites <html> before React hydrates.
  await context.addInitScript(() => {
    localStorage.setItem('cn-theme', 'light');
    localStorage.setItem('cn-pref-callput', 'inverted');
  });

  const errors = await consoleErrors(page, '/login');
  expect(errors.join('\n')).toBe('');

  // …and the preference still won.
  expect(await page.evaluate(() => document.documentElement.dataset.theme)).toBe('light');
  expect(await page.evaluate(() => document.documentElement.dataset.callput)).toBe('inverted');
});

test('hydrates without warnings inside the terminal shell', async ({ page, context, baseURL }) => {
  await context.addCookies([
    { name: 'cn_session', value: 'test', url: baseURL ?? 'http://localhost:4173' }
  ]);
  await context.addInitScript(() => localStorage.setItem('cn-theme', 'terminal'));

  const errors = await consoleErrors(page, '/dashboard');
  expect(errors.join('\n')).toBe('');
});
