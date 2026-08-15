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

export const SOCIAL: { label: string; glyph: GlyphName }[] = [
  { label: 'Facebook', glyph: 'facebook' },
  { label: 'GitHub', glyph: 'code' },
  { label: 'LinkedIn', glyph: 'link' },
  { label: 'Instagram', glyph: 'instagram' },
  { label: 'TikTok', glyph: 'music' },
  { label: 'Phone', glyph: 'phone' },
  { label: 'Chat', glyph: 'chat' }
];
