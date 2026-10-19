import { expect, test } from '@playwright/test';

/**
 * Every page that is still a placeholder, plus the ones that have since been
 * built. Two loops, but together they prove the whole `routes.ts` is wired: a
 * typo in any path here 404s instead of rendering, and the titles catch a
 * `meta` export that went missing in the port.
 *
 * A page graduating from the first list to the second is the expected churn
 * here — the module gets built, and the entry moves rather than disappearing,
 * so the path keeps its coverage.
 */

const PLACEHOLDERS: Array<{ path: string; heading: string; title?: string }> = [
  { path: '/future-lab', heading: 'Future Lab' },
  {
    path: '/options/intraday-booster',
    heading: 'Intraday Booster',
    title: 'Intraday Booster · ChartNexus'
  },
  { path: '/options/iv-grid', heading: 'IV Grid', title: 'IV Grid · ChartNexus' },
  {
    path: '/options/multi-straddle',
    heading: 'Multi-Straddle Chart',
    title: 'Multi-Straddle Chart · ChartNexus'
  },
  { path: '/options/oi-crossover', heading: 'OI Crossover', title: 'OI Crossover · ChartNexus' },
  {
    path: '/options/option-triggers',
    heading: 'Option Triggers',
    title: 'Option Triggers · ChartNexus'
  },
  {
    path: '/options/strategy-chart',
    heading: 'Strategy Chart',
    title: 'Strategy Chart · ChartNexus'
  }
];

/**
 * Built since. Only the route contract is asserted — status, URL and title —
 * because each of these has, or deserves, a spec of its own for its behaviour.
 */
const BUILT: Array<{ path: string; title: string }> = [
  { path: '/future-lab/dashboard', title: 'Future Dashboard · Future Lab · ChartNexus' },
  { path: '/future-lab/heatmap', title: 'Future Heatmap · Future Lab · ChartNexus' },
  { path: '/future-lab/market-movers', title: 'Market Movers · Future Lab · ChartNexus' },
  { path: '/future-lab/price-vs-oi', title: 'Price vs OI · Future Lab · ChartNexus' },
  { path: '/options/atm-straddle', title: 'ATM Straddle Chart · Options Lab' },
  { path: '/options/smart-oi', title: 'Smart OI · Options Lab' },
  { path: '/options/vega-analysis', title: 'Vega Analysis · Options Lab' }
];

test.describe('placeholder pages', () => {
  test.beforeEach(async ({ context, baseURL }) => {
    await context.addCookies([
      { name: 'cn_session', value: 'test', url: baseURL ?? 'http://localhost:4173' }
    ]);
  });

  for (const { path, heading, title } of PLACEHOLDERS) {
    test(`${path} renders its placeholder`, async ({ page }) => {
      const response = await page.goto(path);
      expect(response?.status()).toBe(200);

      // `exact` matters: the Options Lab mega-menu subtitle also ends in
      // "coming soon", and a substring match would resolve to two elements.
      await expect(page.getByText('Coming soon', { exact: true })).toBeVisible();
      await expect(page.getByRole('heading', { name: heading, exact: true })).toBeVisible();

      // The pages with no `meta` export fall through to the root one, exactly
      // as they did under SvelteKit.
      await expect(page).toHaveTitle(title ?? 'ChartNexus');
    });
  }

  for (const { path, title } of BUILT) {
    test(`${path} resolves to its built module`, async ({ page }) => {
      const response = await page.goto(path);
      expect(response?.status()).toBe(200);
      await expect(page).toHaveURL(path);
      await expect(page).toHaveTitle(title);
      // The placeholder is gone, not merely covered by the real page.
      await expect(page.getByText('Coming soon', { exact: true })).toHaveCount(0);
    });
  }
});
