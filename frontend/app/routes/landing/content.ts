/**
 * Every string and link on the marketing pages, in one place.
 *
 * One file so "does the product actually do this?" is a single review. What
 * these pages MUST NOT claim, because the app contradicts it within a click:
 * AI / "smart" / predictions, real-time or streaming (the UI polls every 15s),
 * futures analytics, IV / skew / screener tools, FII/DII flows, paid plans, and
 * any order placement — MarketCompass is read-only by construction, and that is
 * a selling point.
 */

import type { GlyphName } from './components/icons';

/** The marketing nav, now one route per section rather than one scrolling page. */
export const NAV: { label: string; to: string }[] = [
  { label: 'Home', to: '/' },
  { label: 'Features', to: '/features' },
  { label: 'Coverage', to: '/coverage' },
  { label: 'How it works', to: '/how-it-works' },
  { label: 'Scope', to: '/scope' }
];

export const HERO_STATS = [
  { value: '3', caption: 'indices covered' },
  { value: '15s', caption: 'data refresh cycle' },
  { value: 'Free', caption: 'no card, no broker' }
];

export const FEATURES: { glyph: GlyphName; title: string; body: string }[] = [
  {
    glyph: 'layers',
    title: 'The full option chain',
    body: 'The CE/PE ladder around ATM with open interest, LTP and build-up — the same chain the terminal draws, for NIFTY, BANKNIFTY and SENSEX.'
  },
  {
    glyph: 'scale',
    title: 'PCR & max pain',
    body: 'Put-call ratio by open interest and by volume, plus the max-pain strike and support/resistance walls, computed from the live chain.'
  },
  {
    glyph: 'bars',
    title: 'Open-interest build-up',
    body: 'See where positions were added or unwound across strikes through the session, per contract, against the tradable future.'
  },
  {
    glyph: 'activity',
    title: 'Gamma & vega exposure',
    body: 'Per-strike dealer gamma in crore per 1% move, and aggregate vega change since the open, recomputed at every capture.'
  },
  {
    glyph: 'pulse',
    title: 'ATM straddle & price tools',
    body: 'Track the rolling ATM straddle premium and price-vs-OI through the day, with a synthetic future overlay.'
  },
  {
    glyph: 'shield',
    title: 'Provenance on every number',
    body: 'Each figure declares whether it is live, cached, last-good or simulated — and how old it is. Degraded data is labelled, not hidden.'
  }
];

export const COVERAGE = [
  'Option chain',
  'Open interest & multi-OI',
  'Put-call ratio',
  'Max pain',
  'Gamma exposure',
  'Vega analysis',
  'ATM straddle'
];

export const SCOPE = [
  {
    title: 'Instruments',
    body: 'NIFTY, BANKNIFTY and SENSEX options with canonical lot sizes and nearest-expiry chains.'
  },
  {
    title: 'Market data',
    body: 'Mock market data by default; a Fyers provider can be enabled through backend configuration and a broker connection.'
  },
  {
    title: 'Read-only by design',
    body: 'MarketCompass never places an order, holds funds, or gives advice. It reads the chain and works it out.'
  },
  {
    title: 'Provenance built in',
    body: 'Every response is tagged live, cached, last-good or simulated, with its age — so a stale number can never pass for a fresh one.'
  }
];

export const STEPS = [
  {
    n: '01',
    title: 'Create a free account',
    body: 'Register in a moment — no card, no broker connection, and no trial timer counting down.'
  },
  {
    n: '02',
    title: 'Read the option-chain desk',
    body: 'Pick an index and explore OI, PCR, max pain, gamma, vega and the ATM straddle on mock data.'
  },
  {
    n: '03',
    title: 'Connect a broker when ready',
    body: 'Optionally add Fyers credentials for live market data. Until then, everything runs on mock data.'
  }
];

export const FOOTER_COLS: { title: string; links: { label: string; to: string }[] }[] = [
  {
    title: 'Product',
    links: [
      { label: 'Features', to: '/features' },
      { label: 'Coverage', to: '/coverage' },
      { label: 'How it works', to: '/how-it-works' },
      { label: 'Scope', to: '/scope' }
    ]
  },
  {
    title: 'Company',
    links: [
      { label: 'Provenance', to: '/scope' },
      { label: 'Read-only policy', to: '/scope' }
    ]
  },
  {
    title: 'Get started',
    links: [
      { label: 'Create account', to: '/register' },
      { label: 'Sign in', to: '/login' }
    ]
  }
];

/* ── Features · module deep-dive ─────────────────────────────────────────────
   Each live module, one step below the six-card grid: a paragraph on what it is
   and two or three concrete things it puts on screen. Every claim is something
   the terminal actually draws today on mock data. */
export const MODULE_DETAILS: {
  glyph: GlyphName;
  title: string;
  body: string;
  points: string[];
}[] = [
  {
    glyph: 'layers',
    title: 'Option chain',
    body: 'The CE/PE ladder around the at-the-money strike — the same chain the terminal draws — for NIFTY, BANKNIFTY and SENSEX at the nearest expiry.',
    points: [
      'Last price, open interest and OI change per strike',
      'ATM, support and resistance strikes flagged on the ladder',
      'Spot, PCR, max pain and the ATM straddle summarised on top'
    ]
  },
  {
    glyph: 'bars',
    title: 'Open interest & multi-OI',
    body: 'Where positions were added or unwound across strikes through the session, per contract, so build-up and unwinding read at a glance rather than as a wall of numbers.',
    points: [
      'Per-strike OI and change from the session open',
      'Multi-strike OI compared side by side',
      'Bars scaled against the tradable future for context'
    ]
  },
  {
    glyph: 'scale',
    title: 'Put-call ratio',
    body: 'PCR by open interest and by volume, computed from the live chain rather than typed in — the balance of puts against calls the way positioning actually sits.',
    points: [
      'PCR by OI and by volume, side by side',
      'Recomputed at every capture from the current chain',
      'Read alongside max pain and the OI walls'
    ]
  },
  {
    glyph: 'pulse',
    title: 'Max pain',
    body: 'The strike where the most option value would expire worthless, plus the support and resistance walls the open interest builds around it.',
    points: [
      'Max-pain strike derived from the whole chain',
      'Support and resistance walls from OI concentration',
      'Updated as the chain moves through the day'
    ]
  },
  {
    glyph: 'activity',
    title: 'Gamma exposure',
    body: 'Per-strike dealer gamma in crore per 1% move, so you can see where hedging flow is likely to pin or accelerate the index.',
    points: [
      'Gamma per strike in crore per 1% move',
      'Aggregate exposure across the chain',
      'Recomputed at every capture, never cached silently'
    ]
  },
  {
    glyph: 'shield',
    title: 'Vega analysis',
    body: 'Aggregate vega and its change since the open, so a move driven by volatility reads differently from one driven by direction.',
    points: [
      'Aggregate vega across the chain',
      'Change since the session open',
      'Paired with gamma for a fuller greeks picture'
    ]
  },
  {
    glyph: 'clock',
    title: 'ATM straddle',
    body: 'The rolling at-the-money straddle premium through the day, with price-vs-OI and a synthetic future overlay to frame it.',
    points: [
      'Rolling ATM straddle premium intraday',
      'Price-vs-OI through the session',
      'Synthetic future overlay for reference'
    ]
  }
];

/* ── Provenance legend ───────────────────────────────────────────────────────
   The four states every number can carry. This is the product's core promise,
   so the copy stays precise: what the state means and how fresh it is. */
export const PROVENANCE_LEGEND: {
  label: string;
  tone: 'live' | 'cached' | 'stale' | 'sim';
  meaning: string;
}[] = [
  {
    label: 'Live',
    tone: 'live',
    meaning: 'Fetched this cycle from the configured provider. The freshest a number gets.'
  },
  {
    label: 'Cached',
    tone: 'cached',
    meaning: 'Served from a recent capture to stay within rate limits, with its age shown.'
  },
  {
    label: 'Last-good',
    tone: 'stale',
    meaning:
      'The most recent value that succeeded, kept when a refresh fails rather than blanking out.'
  },
  {
    label: 'Simulated',
    tone: 'sim',
    meaning:
      'Mock market data — the default before you connect a broker. Clearly labelled, never disguised.'
  }
];

/* ── Coverage · instrument matrix ────────────────────────────────────────────
   The three indices with their canonical lot sizes and the default data source.
   Lot sizes are the standard exchange values; source is honest about mock. */
export const COVERAGE_MATRIX: {
  index: string;
  lot: string;
  expiry: string;
  source: string;
}[] = [
  { index: 'NIFTY', lot: '75', expiry: 'Nearest weekly', source: 'Mock by default' },
  { index: 'BANKNIFTY', lot: '35', expiry: 'Nearest monthly', source: 'Mock by default' },
  { index: 'SENSEX', lot: '20', expiry: 'Nearest weekly', source: 'Mock by default' }
];

/* ── Coverage · live now vs. labelled coming-soon ────────────────────────────
   The honest split. `soon` items exist as placeholders inside the app and are
   labelled "coming soon" there — they are NOT promised as available here. */
export const LIVE_VS_SOON: { live: string[]; soon: string[] } = {
  live: [
    'Option chain',
    'Open interest & multi-OI',
    'Put-call ratio',
    'Max pain',
    'Gamma exposure',
    'Vega analysis',
    'ATM straddle'
  ],
  soon: [
    'Live streaming feed (data polls, it does not stream)',
    'IV, skew and volatility tools',
    'Screeners and alerts',
    'FII/DII flow analytics'
  ]
};

/* ── How it works · what you need vs. what you don't ─────────────────────────*/
export const NEEDS: { need: string[]; skip: string[] } = {
  need: [
    'An email address',
    'A few minutes to look around',
    'Optionally, Fyers credentials for live data'
  ],
  skip: [
    'A credit or debit card',
    'A funded broker account',
    'A trial timer counting down',
    'Any trading experience'
  ]
};

/* ── How it works · FAQ ──────────────────────────────────────────────────────
   Honest answers only. If the app polls every ~15s, the FAQ says so. */
export const FAQ: { q: string; a: string }[] = [
  {
    q: 'Is MarketCompass free?',
    a: 'Yes. There is no card, no plan and no trial timer. Create an account with an email and read the desk on mock data straight away.'
  },
  {
    q: 'Do I need a broker account?',
    a: 'No. Everything runs on mock data by default. Connecting Fyers is an optional last step for live market data in a configured environment.'
  },
  {
    q: 'Is the data real-time?',
    a: 'No — MarketCompass polls on a short cycle (about every 15 seconds), it does not stream. Every number is stamped with its age so you always know how fresh it is.'
  },
  {
    q: 'Can it place trades for me?',
    a: 'Never. MarketCompass is read-only by construction: it cannot place an order, modify a position or hold funds. It reads the chain and works it out.'
  },
  {
    q: 'Which instruments are covered?',
    a: 'NIFTY, BANKNIFTY and SENSEX options at the nearest expiry, with canonical lot sizes.'
  },
  {
    q: 'What does “provenance” mean here?',
    a: 'Every figure declares whether it is live, cached, last-good or simulated, and how old it is. A stale number can never quietly pass for a fresh one.'
  },
  {
    q: 'Is my money at risk?',
    a: 'No. MarketCompass never holds funds and never connects to a payments rail. There is nothing to fund and nothing to withdraw.'
  }
];

/* ── Scope · read-only guarantees ────────────────────────────────────────────*/
export const GUARANTEES: { glyph: GlyphName; title: string; body: string }[] = [
  {
    glyph: 'ban',
    title: 'Never places an order',
    body: 'No order entry, no modification, no cancellation. The app has no path to the order book — by design, not by policy.'
  },
  {
    glyph: 'wallet',
    title: 'Never holds funds',
    body: 'No wallet, no margin, no payments rail. There is nothing to deposit and nothing to withdraw.'
  },
  {
    glyph: 'chat',
    title: 'Never gives advice',
    body: 'MarketCompass shows what the chain says. It does not tell you what to trade and gives no SEBI-regulated advice.'
  },
  {
    glyph: 'shield',
    title: 'Provenance on every number',
    body: 'Live, cached, last-good or simulated — with its age. Degraded data is labelled, not hidden.'
  }
];

/* ── Home · teaser cards linking deeper ──────────────────────────────────────*/
export const HOME_HIGHLIGHTS: { glyph: GlyphName; title: string; body: string; to: string }[] = [
  {
    glyph: 'layers',
    title: 'Everything, already worked out',
    body: 'Chain, PCR, max pain, OI build-up, gamma and vega — the modules that are live today.',
    to: '/features'
  },
  {
    glyph: 'database',
    title: 'What you can read today',
    body: 'The tools that work right now on mock data, and an honest line on what is still coming.',
    to: '/coverage'
  },
  {
    glyph: 'refresh',
    title: 'From stranger to the chain in three steps',
    body: 'Create a free account, read the desk, and connect a broker only when you are ready.',
    to: '/how-it-works'
  }
];

export const SOCIAL: { label: string; glyph: GlyphName }[] = [
  { label: 'Facebook', glyph: 'facebook' },
  { label: 'GitHub', glyph: 'code' },
  { label: 'LinkedIn', glyph: 'link' },
  { label: 'Instagram', glyph: 'instagram' },
  { label: 'TikTok', glyph: 'music' },
  { label: 'Phone', glyph: 'phone' },
  { label: 'Chat', glyph: 'chat' }
];
