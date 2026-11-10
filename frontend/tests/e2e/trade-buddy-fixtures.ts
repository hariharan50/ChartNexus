import type { Page } from '@playwright/test';

/**
 * Browser-side fixtures for the Trade Buddy page.
 *
 * Not in `stub-api.mjs` with everything else, and the reason is worth knowing:
 * the Playwright app server runs the production build, which has no `/api`
 * proxy — in development Vite forwards `/api` to the backend, and in
 * production both sit behind one hostname. Pages that render under the e2e
 * harness do it through server loaders, which reach the stub over
 * `API_INTERNAL_URL`. This page reads everything through react-query in the
 * browser, so its requests go to the app server and 404 there however complete
 * the stub is.
 *
 * Fulfilling them in the page is therefore the only way to see this screen
 * with data at all — and it keeps the payloads next to the suite that asserts
 * on them rather than in a process that cannot serve them.
 *
 * Three states across the three indices, because the page says something
 * different about each: NIFTY marked for this session and mid-touch,
 * BANKNIFTY marked for an earlier one (the stale banner), SENSEX never marked
 * (the empty state).
 */

const SESSION = '2026-01-15';

const BANDS = {
  touch: 6,
  approach: 25,
  break_buffer: 12,
  confirm_hold_seconds: 20,
  source: 'atr',
  atr: 200,
  note: null
};

const LEVELS: Record<string, { label: string; price: number; role: string }[]> = {
  NIFTY: [
    { label: 'R2', price: 24_800, role: 'resistance' },
    { label: 'R1', price: 24_700, role: 'resistance' },
    { label: 'S1', price: 24_600, role: 'support' },
    { label: 'S2', price: 24_500, role: 'support' }
  ],
  BANKNIFTY: [
    { label: 'R1', price: 52_400, role: 'resistance' },
    { label: 'S1', price: 51_800, role: 'support' }
  ],
  SENSEX: []
};

// NIFTY sits 8 points under R1, inside the 25-point approach band: the
// state the page is really for, and the one that exercises the callout.
const PRICES: Record<string, number> = { NIFTY: 24_692, BANKNIFTY: 52_100, SENSEX: 81_000 };

/** BANKNIFTY's marks are from the session before, so nothing is watched. */
const markedOn = (symbol: string) => (symbol === 'BANKNIFTY' ? '2026-01-14' : SESSION);

const STATES: Record<string, string[]> = {
  NIFTY: ['idle', 'touched', 'idle', 'idle'],
  BANKNIFTY: ['idle', 'idle']
};

function engineState(symbol: string) {
  const marks = LEVELS[symbol] ?? [];
  const stale = symbol === 'BANKNIFTY';
  return {
    symbol,
    marked_on: marks.length ? markedOn(symbol) : null,
    levels_stale: stale,
    bands: BANDS,
    market_open: true,
    // Relative to now, so the page reports a live feed. A fixed timestamp
    // would have every screenshot showing the stale-feed treatment instead.
    last_tick_at: new Date(Date.now() - 2_000).toISOString(),
    last_price: marks.length ? (PRICES[symbol] ?? null) : null,
    whatsapp_used: 2,
    whatsapp_limit: 20,
    levels: marks.map((mark, i) => ({
      label: mark.label,
      level_price: mark.price,
      role: mark.role,
      state: stale ? 'idle' : (STATES[symbol]?.[i] ?? 'idle'),
      break_pending: false,
      alerts_remaining: 3 - (i % 3)
    }))
  };
}

function settings(symbol: string) {
  return {
    symbol,
    bands: BANDS,
    cooldown_minutes: 20,
    daily_alert_cap: 3,
    defaults: {
      touch_multiple: 0.03,
      approach_multiple: 0.125,
      break_multiple: 0.06,
      atr_period: 14,
      confirm_hold_seconds: 20,
      cooldown_minutes: 20,
      daily_alert_cap: 3,
      fallback_touch: 6,
      fallback_approach: 25,
      fallback_break_buffer: 12
    },
    overrides: {
      touch: null,
      approach: null,
      break_buffer: null,
      confirm_hold_seconds: null,
      cooldown_minutes: null,
      daily_alert_cap: null
    }
  };
}

const ALERTS = [
  {
    kind: 'touched',
    label: 'R1',
    level_price: 24_700,
    price: 24_703.2,
    role_before: 'resistance',
    role_after: 'resistance',
    at: '2026-01-15T05:16:46.000Z',
    channels: ['telegram']
  },
  {
    kind: 'break_confirmed',
    label: 'S2',
    level_price: 24_500,
    price: 24_486.5,
    role_before: 'support',
    role_after: 'resistance',
    at: '2026-01-15T04:41:12.000Z',
    channels: ['telegram', 'whatsapp']
  }
];

/** The level price is closest to, as the backend reports it. */
function nearest(state: ReturnType<typeof engineState>) {
  if (state.last_price === null || state.levels.length === 0) return null;
  const price = state.last_price;
  return state.levels
    .map((level) => ({ label: level.label, distance: Math.abs(level.level_price - price) }))
    .sort((a, b) => a.distance - b.distance)[0];
}

function watchlist() {
  return {
    instruments: ['NIFTY', 'BANKNIFTY', 'SENSEX'].map((symbol) => {
      const state = engineState(symbol);
      return {
        symbol,
        watched: state.levels.length > 0,
        market_open: state.market_open,
        last_price: state.last_price,
        last_tick_at: state.last_tick_at,
        levels_marked: state.levels.length,
        // Computed, not hard-coded: the tab strip claiming a level the table
        // disagrees with would look like a bug in the page rather than in the
        // fixture.
        nearest_label: nearest(state)?.label ?? null,
        nearest_distance: nearest(state)?.distance ?? null,
        attention: symbol === 'NIFTY' ? 'touched' : null,
        band_source: 'atr',
        levels_stale: state.levels_stale
      };
    })
  };
}

const CHANNELS = {
  channels: [
    {
      channel: 'telegram',
      configured: true,
      ready: true,
      verified: true,
      enabled: true,
      label: '@chartnexus_levels_bot',
      target: '123456789',
      masked_secret: '8123******AAH1'
    }
  ]
};

export interface TradeBuddyOverrides {
  /** Merged into every `/state` response — for the closed-market case. */
  state?: Record<string, unknown>;
}

/** Answer every Trade Buddy endpoint in the browser, for the whole page. */
export async function stubTradeBuddy(page: Page, over: TradeBuddyOverrides = {}): Promise<void> {
  await page.route('**/api/v1/trade-buddy/**', async (route) => {
    const url = new URL(route.request().url());
    const symbol = url.searchParams.get('symbol') ?? 'NIFTY';
    const path = url.pathname.replace('/api/v1/trade-buddy', '');

    if (path === '/levels') {
      const marks = LEVELS[symbol] ?? [];
      return route.fulfill({
        json: {
          symbol,
          levels: marks,
          marked_on: marks.length ? markedOn(symbol) : null
        }
      });
    }
    if (path === '/state') {
      return route.fulfill({ json: { ...engineState(symbol), ...(over.state ?? {}) } });
    }
    if (path === '/watchlist') return route.fulfill({ json: watchlist() });
    if (path === '/settings') return route.fulfill({ json: settings(symbol) });
    if (path === '/channels') return route.fulfill({ json: CHANNELS });
    if (path === '/alerts') {
      return route.fulfill({
        json: { symbol, session: SESSION, alerts: symbol === 'NIFTY' ? ALERTS : [] }
      });
    }
    return route.fulfill({ status: 404, json: { detail: 'not stubbed' } });
  });
}
