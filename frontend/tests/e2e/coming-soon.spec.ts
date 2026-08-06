import { expect, test } from '@playwright/test';

/**
 * Every page that is still a placeholder. One loop, but it proves the whole
 * `routes.ts` is wired: a typo in any path here 404s instead of rendering, and
 * the titles catch a `meta` export that went missing in the port.
 */

const PAGES: Array<{ path: string; heading: string; title?: string }> = [
  { path: '/analyse', heading: 'Analyse' },
  { path: '/smart-insights', heading: 'Smart Insights' },

  { path: '/future-lab', heading: 'Future Lab' },
  {
    path: '/future-lab/dashboard',
    heading: 'Future Dashboard',
    title: 'Future Dashboard · MarketCompass'
  },
  {
    path: '/future-lab/heatmap',
    heading: 'Future Heatmap',
    title: 'Future Heatmap · MarketCompass'
  },
  {
    path: '/future-lab/intraday',
    heading: 'Future Intraday',
    title: 'Future Intraday · MarketCompass'
  },
  {
    path: '/future-lab/market-movers',
    heading: 'Market Movers',
    title: 'Market Movers · MarketCompass'
  },
  { path: '/future-lab/price-vs-oi', heading: 'Price vs OI', title: 'Price vs OI · MarketCompass' },
  {
    path: '/future-lab/sentiment-cycle',
    heading: 'Future Sentiment Cycle',
    title: 'Future Sentiment Cycle · MarketCompass'
  },

  {
    path: '/options/atm-straddle',
    heading: 'ATM Straddle Chart',
    title: 'ATM Straddle Chart · MarketCompass'
  },
  {
    path: '/options/gamma-exposure',
    heading: 'Gamma Exposure',
    title: 'Gamma Exposure · MarketCompass'
  },
  {
    path: '/options/intraday-booster',
    heading: 'Intraday Booster',
    title: 'Intraday Booster · MarketCompass'
  },
  { path: '/options/iv-grid', heading: 'IV Grid', title: 'IV Grid · MarketCompass' },
  { path: '/options/iv-hv', heading: 'IV - HV', title: 'IV - HV · MarketCompass' },
  {
    path: '/options/iv-hv-ivp',
    heading: 'IV/HV/IVP Chart',
    title: 'IV/HV/IVP Chart · MarketCompass'
  },
  {
    path: '/options/iv-intraday',
    heading: 'IV - Intraday',
    title: 'IV - Intraday · MarketCompass'
  },
  { path: '/options/max-pain', heading: 'Max Pain', title: 'Max Pain · MarketCompass' },
  {
    path: '/options/multi-oi-volume',
    heading: 'Multi OI & Volume',
    title: 'Multi OI & Volume · MarketCompass'
  },
  {
    path: '/options/multi-straddle',
    heading: 'Multi-Straddle Chart',
    title: 'Multi-Straddle Chart · MarketCompass'
  },
  {
    path: '/options/multistrike',
    heading: 'MultiStrike Chart',
    title: 'MultiStrike Chart · MarketCompass'
  },
  { path: '/options/oi-crossover', heading: 'OI Crossover', title: 'OI Crossover · MarketCompass' },
  {
    path: '/options/option-triggers',
    heading: 'Option Triggers',
    title: 'Option Triggers · MarketCompass'
  },
  { path: '/options/pcr', heading: 'Put-Call Ratio', title: 'Put-Call Ratio · MarketCompass' },
  {
    path: '/options/pe-ce-difference',
    heading: 'PE-CE Difference',
    title: 'PE-CE Difference · MarketCompass'
  },
  {
    path: '/options/premium-decay',
    heading: 'Premium Decay',
    title: 'Premium Decay · MarketCompass'
  },
  { path: '/options/price-vs-oi', heading: 'Price vs OI', title: 'Price vs OI · MarketCompass' },
  { path: '/options/smart-oi', heading: 'Smart OI', title: 'Smart OI · MarketCompass' },
  {
    path: '/options/strategy-chart',
    heading: 'Strategy Chart',
    title: 'Strategy Chart · MarketCompass'
  },
  { path: '/options/timeseries', heading: 'Timeseries', title: 'Timeseries · MarketCompass' },
  {
    path: '/options/vega-analysis',
    heading: 'Vega Analysis',
    title: 'Vega Analysis · MarketCompass'
  },
  {
    path: '/options/volatility-skew',
    heading: 'Volatility Skew',
    title: 'Volatility Skew · MarketCompass'
  }
];

test.describe('placeholder pages', () => {
  test.beforeEach(async ({ context, baseURL }) => {
    await context.addCookies([
      { name: 'mc_session', value: 'test', url: baseURL ?? 'http://localhost:4173' }
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
      await expect(page).toHaveTitle(title ?? 'MarketCompass');
    });
  }
});
