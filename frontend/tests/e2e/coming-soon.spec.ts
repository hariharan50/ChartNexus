import { expect, test } from '@playwright/test';

/**
 * Every page that is still a placeholder. One loop, but it proves the whole
 * `routes.ts` is wired: a typo in any path here 404s instead of rendering, and
 * the titles catch a `meta` export that went missing in the port.
 */

const PAGES: Array<{ path: string; heading: string; title?: string }> = [
  { path: '/future-lab', heading: 'Future Lab' },
  {
    path: '/future-lab/dashboard',
    heading: 'Future Dashboard',
    title: 'Future Dashboard · ChartNexus'
  },
  {
    path: '/future-lab/heatmap',
    heading: 'Future Heatmap',
    title: 'Future Heatmap · ChartNexus'
  },
  {
    path: '/future-lab/market-movers',
    heading: 'Market Movers',
    title: 'Market Movers · ChartNexus'
  },
  { path: '/future-lab/price-vs-oi', heading: 'Price vs OI', title: 'Price vs OI · ChartNexus' },

  {
    path: '/options/atm-straddle',
    heading: 'ATM Straddle Chart',
    title: 'ATM Straddle Chart · ChartNexus'
  },
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
    path: '/options/pe-ce-difference',
    heading: 'PE-CE Difference',
    title: 'PE-CE Difference · ChartNexus'
  },
  { path: '/options/smart-oi', heading: 'Smart OI', title: 'Smart OI · ChartNexus' },
  {
    path: '/options/strategy-chart',
    heading: 'Strategy Chart',
    title: 'Strategy Chart · ChartNexus'
  },
  { path: '/options/timeseries', heading: 'Timeseries', title: 'Timeseries · ChartNexus' },
  {
    path: '/options/vega-analysis',
    heading: 'Vega Analysis',
    title: 'Vega Analysis · ChartNexus'
  }
];

test.describe('placeholder pages', () => {
  test.beforeEach(async ({ context, baseURL }) => {
    await context.addCookies([
      { name: 'cn_session', value: 'test', url: baseURL ?? 'http://localhost:4173' }
    ]);
  });

  for (const { path, heading, title } of PAGES) {
    test(`${path} renders its placeholder`, async ({ page }) => {
      const response = await page.goto(path);
      expect(response?.status()).toBe(200);

      // `exact` matters: the Options Lab mega-menu subtitle also ends in
      // "coming soon", and a substring match would resolve to two elements.
      await expect(page.getByText('Coming soon', { exact: true })).toBeVisible();
      await expect(page.getByRole('heading', { name: heading, exact: true })).toBeVisible();

      // The four pages with no <svelte:head><title> fall through to the root
      // meta, exactly as they did under SvelteKit.
      await expect(page).toHaveTitle(title ?? 'ChartNexus');
    });
  }
});
