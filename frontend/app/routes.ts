import { type RouteConfig, index, layout, prefix, route } from '@react-router/dev/routes';

/**
 * The route tree, declared explicitly rather than by file convention.
 *
 * SvelteKit route groups — `(public)`, `(terminal)` — have no filename
 * equivalent in React Router's flat-file convention, and an explicit config is
 * the only form that can be read side by side with the old `src/routes` tree.
 *
 * Mapping rules:
 *   `(group)/+layout.svelte`      → layout(file, children)          [pathless]
 *   `dir/+layout.svelte` + pages  → route('dir', file, [index(…)])  [pathful]
 *
 * Deliberately absent: every directory under `src/routes` that holds only a
 * `.gitkeep` and no `+page.svelte` — the whole `(admin)` group, plus
 * `(public)/disclosures`, `(terminal)/{copilot,futures,institutional,signals}`
 * and `settings/{api-keys,billing,organization,preferences}`. They are not
 * routes today and must not become routes here.
 */
export default [
  // `/` is the marketing landing page. It was a bare redirect to `/dashboard`
  // during the migration, when the app had no marketing homepage; its loader
  // now keeps that redirect for signed-in visitors only.
  // The marketing site: one page per section, sharing nav/CTA/footer chrome.
  layout('routes/landing/layout.tsx', [
    index('routes/landing/home.tsx'),
    route('features', 'routes/landing/features.tsx'),
    route('coverage', 'routes/landing/coverage.tsx'),
    route('how-it-works', 'routes/landing/how-it-works.tsx'),
    route('scope', 'routes/landing/scope.tsx')
  ]),
  route('healthz', 'routes/healthz.ts'),

  // ── (public) ──────────────────────────────────────────────────────────────
  layout('routes/public/layout.tsx', [
    route('login', 'routes/public/login.tsx'),
    route('register', 'routes/public/register.tsx'),
    route('forgot-password', 'routes/public/forgot-password.tsx')
  ]),

  // Ungrouped in SvelteKit too: the OAuth landing page renders its own chrome.
  route('auth/google/callback', 'routes/auth/google-callback.tsx'),

  // ── (terminal) ────────────────────────────────────────────────────────────
  layout('routes/terminal/layout.tsx', [
    route('dashboard', 'routes/terminal/dashboard/route.tsx'),
    route('advanced-dashboard', 'routes/terminal/advanced-dashboard/route.tsx'),
    route('option-chain', 'routes/terminal/option-chain/route.tsx'),
    route('analyse', 'routes/terminal/analyse/route.tsx'),
    route('smart-insights', 'routes/terminal/smart-insights.tsx'),

    // The AI Console is two pages: the guidance read-out and the Hella chat.
    // `/ai-console` keeps resolving to the analysis page it always was.
    ...prefix('ai-console', [
      index('routes/terminal/ai-console/analysis/route.tsx'),
      route('agent', 'routes/terminal/ai-console/agent/route.tsx')
    ]),

    ...prefix('options', [
      index('routes/terminal/options/index.tsx'),
      route('open-interest', 'routes/terminal/options/open-interest/route.tsx'),
      route('atm-straddle', 'routes/terminal/options/atm-straddle/route.tsx'),
      route('gamma-exposure', 'routes/terminal/options/gamma-exposure/route.tsx'),
      route('intraday-booster', 'routes/terminal/options/intraday-booster.tsx'),
      route('iv-grid', 'routes/terminal/options/iv-grid.tsx'),
      route('iv-hv', 'routes/terminal/options/iv-hv.tsx'),
      route('iv-hv-ivp', 'routes/terminal/options/iv-hv-ivp.tsx'),
      route('iv-intraday', 'routes/terminal/options/iv-intraday.tsx'),
      route('max-pain', 'routes/terminal/options/max-pain/route.tsx'),
      route('multi-oi-volume', 'routes/terminal/options/multi-oi-volume/route.tsx'),
      route('multi-straddle', 'routes/terminal/options/multi-straddle.tsx'),
      route('multistrike', 'routes/terminal/options/multistrike.tsx'),
      route('oi-crossover', 'routes/terminal/options/oi-crossover.tsx'),
      route('option-triggers', 'routes/terminal/options/option-triggers.tsx'),
      route('pcr', 'routes/terminal/options/pcr/route.tsx'),
      route('pe-ce-difference', 'routes/terminal/options/pe-ce-difference.tsx'),
      route('premium-decay', 'routes/terminal/options/premium-decay.tsx'),
      route('price-vs-oi', 'routes/terminal/options/price-vs-oi.tsx'),
      route('smart-oi', 'routes/terminal/options/smart-oi.tsx'),
      route('strategy-chart', 'routes/terminal/options/strategy-chart.tsx'),
      route('timeseries', 'routes/terminal/options/timeseries.tsx'),
      route('vega-analysis', 'routes/terminal/options/vega-analysis/route.tsx'),
      route('volatility-skew', 'routes/terminal/options/volatility-skew.tsx')
    ]),

    ...prefix('future-lab', [
      index('routes/terminal/future-lab/index.tsx'),
      route('dashboard', 'routes/terminal/future-lab/dashboard.tsx'),
      route('heatmap', 'routes/terminal/future-lab/heatmap.tsx'),
      route('intraday', 'routes/terminal/future-lab/intraday.tsx'),
      route('market-movers', 'routes/terminal/future-lab/market-movers.tsx'),
      route('price-vs-oi', 'routes/terminal/future-lab/price-vs-oi.tsx'),
      route('sentiment-cycle', 'routes/terminal/future-lab/sentiment-cycle.tsx')
    ]),

    // settings/+layout.svelte is a *pathful* layout: it owns the /settings
    // segment as well as the nav chrome.
    route('settings', 'routes/terminal/settings/layout.tsx', [
      index('routes/terminal/settings/plans.tsx'),
      route('profile', 'routes/terminal/settings/profile.tsx'),
      route('security', 'routes/terminal/settings/security.tsx'),
      route('notifications', 'routes/terminal/settings/notifications.tsx'),
      route('layout', 'routes/terminal/settings/appearance.tsx'),
      route('global', 'routes/terminal/settings/global.tsx'),
      route('help', 'routes/terminal/settings/help.tsx'),
      route('broker', 'routes/terminal/settings/broker/route.tsx'),
      route('broker/callback', 'routes/terminal/settings/broker/callback.tsx')
    ])
  ])
] satisfies RouteConfig;
