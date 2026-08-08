/**
 * Every string on the landing page.
 *
 * One file so that "does the product actually do this?" is a single review,
 * rather than a hunt through a dozen components.
 *
 * WHAT THIS PAGE MAY NOT CLAIM — each of these is a placeholder or absent in
 * the shipped product, and the app's own navigation contradicts it within a
 * click:
 *
 *   · AI, LLM, machine learning, "smart", "predicts". Every LLM provider file
 *     in the backend is empty; the dashboard's "AI summary" is a percent-change
 *     threshold; /smart-insights is a ComingSoon placeholder.
 *   · "Real-time", "streaming", "live tick". There is no websocket — the UI
 *     polls every 15 seconds. Say "updates every 15 seconds".
 *   · Futures analytics. All seven Future Lab routes are placeholders.
 *   · IV, volatility, straddle, skew or screener tools. Eighteen of the
 *     twenty-four Options Lab routes are placeholders.
 *   · FII/DII flows, alert delivery, paid plans, teams or seats.
 *   · Order placement, positions or funds. The product is read-only by
 *     construction and that is a selling point, not a gap.
 *   · Trading-holiday awareness. The calendar knows weekends and hours only.
 *
 * Anything added here should be clickable in the running app.
 */

export const HERO = {
  eyebrow: 'NSE options analytics',
  headingLead: 'Read the option chain',
  headingKeyword: 'without guessing where the numbers came from.',
  lead:
    'Open interest, put-call ratio, max pain and gamma exposure for NIFTY, BANKNIFTY and ' +
    'SENSEX — each figure stamped live, cached or simulated, with its age. Free, and it works ' +
    'before you connect a broker.',
  primary: { to: '/register', label: 'Create free account' },
  secondary: { to: '/login', label: 'Sign in' },
  note: 'No broker account needed · No card · Read-only, it cannot place an order'
} as const;

/** The cards overlapping the hero graphic. Both figures appear elsewhere. */
export const HERO_STATS = [
  { label: 'Indices', value: '3' },
  { label: 'Options Lab tools', value: '5' },
  { label: 'Orders it can place', value: '0' }
] as const;

/** Four numbers, each verifiable by clicking through the product. */
export const TRUST = [
  { value: '3', label: 'indices covered', detail: 'NIFTY · BANKNIFTY · SENSEX' },
  { value: '5', label: 'Options Lab tools', detail: 'OI, Multi OI, PCR, Max Pain, GEX' },
  { value: '100%', label: 'of payloads carry provenance', detail: 'live, cached or simulated' },
  { value: '0', label: 'orders it can place', detail: 'read-only by construction' }
] as const;

export const CHAIN_SECTION = {
  eyebrow: 'Option chain',
  lead:
    'The full ladder around ATM with open interest, OI change, LTP and implied volatility, plus ' +
    'the derived numbers you would otherwise compute by hand: put-call ratio, max pain, support ' +
    'and resistance, and a build-up classification on every strike.'
} as const;

export const SIGNAL_SECTION = {
  eyebrow: 'Derived, not asserted',
  lead:
    'Writing posture, build-up and max-pain distance are arithmetic over the chain you are ' +
    'looking at. Every one of them is a formula you can check, not a score from a model you ' +
    'cannot see.'
} as const;

export const OI_SECTION = {
  eyebrow: 'Options Lab',
  lead:
    'Five tools over an intraday archive the app captures itself: Open Interest with a ' +
    'scrubbable session timeline, Multi OI & Volume across contracts, put-call ratio through ' +
    'the day, max pain, and gamma exposure. Snapshots land every minute of the session.'
} as const;

export const PROVENANCE_SECTION = {
  eyebrow: 'Provenance',
  lead:
    'Every response says which rung of the ladder it came from — a fresh broker read, a cached ' +
    'one, the last good value, or the simulator — and how old it is. Degraded data is labelled ' +
    'rather than hidden, because a stale number that looks live is worse than no number.'
} as const;

/**
 * The trust section. This is where a template would put testimonials; the
 * product has no users yet, and inventing five is not an option. These are
 * mechanisms instead — each one is a thing the code actually does.
 */
export const PROOF = [
  {
    title: 'Every number says where it came from',
    body:
      'Live, cached or simulated, with an age in seconds, on every payload the API returns. The ' +
      'badge below is the same component the terminal uses.',
    wide: true
  },
  {
    title: 'Broker credentials are encrypted per tenant',
    body:
      'AES-256-GCM at rest, ciphertext bound to the tenant and broker so it cannot be replayed ' +
      'into another account. Key rotation is supported.'
  },
  {
    title: 'Sessions rotate, and reuse is detected',
    body:
      'JWT access tokens with refresh rotation. A refresh token presented twice invalidates the ' +
      'whole family rather than quietly issuing another.'
  },
  {
    title: 'It cannot place an order',
    body:
      'There is no order, position or funds path in the product. The broker connection is used ' +
      'to read market data and nothing else.'
  },
  {
    title: 'It runs before you connect anything',
    body:
      'A deterministic simulator drives the entire product end to end, so you can evaluate every ' +
      'screen without a broker account — and it is always labelled as simulated.'
  }
] as const;

/**
 * The feature grid. `glyph` names an icon the grid resolves — keeping the
 * component out of this file so it stays plain data.
 */
export const FEATURES = [
  {
    glyph: 'chart',
    title: 'The full option chain',
    body: 'Strikes around ATM with open interest, OI change, last traded price and implied volatility, for NIFTY, BANKNIFTY and SENSEX.'
  },
  {
    glyph: 'target',
    title: 'Max pain and PCR, already worked out',
    body: 'Put-call ratio by open interest and by volume, max pain, and the support and resistance the heaviest strikes imply.'
  },
  {
    glyph: 'clock',
    title: 'An intraday archive it captures itself',
    body: 'Snapshots land every minute of the session into its own store, so the Open Interest timeline can be scrubbed back through the day.'
  },
  {
    glyph: 'bolt',
    title: 'Gamma exposure',
    body: 'Dealer positioning by strike, so you can see where hedging flow is likely to dampen a move and where it stops.'
  },
  {
    glyph: 'eye',
    title: 'Build-up on every strike',
    body: 'Long build-up, short build-up, long unwinding or short covering, classified from the price and open-interest change together.'
  },
  {
    glyph: 'lock',
    title: 'Read-only, by construction',
    body: 'There is no order, position or funds path anywhere in the product. A broker connection is used to read market data and nothing else.'
  }
] as const;

/** The checklist rows. Short claims, each one checkable in the product. */
export const CHECKLIST = [
  {
    title: 'Works before you connect a broker',
    body: 'A deterministic simulator drives every screen, so you can evaluate the whole product without an account.'
  },
  {
    title: 'Every number is sourced',
    body: 'Live, cached or simulated, with an age in seconds, on every response the API returns.'
  },
  {
    title: 'Your credentials stay encrypted',
    body: 'AES-256-GCM at rest, tied to your tenant, and never readable by another account.'
  },
  {
    title: 'Sessions you can revoke',
    body: 'See every signed-in session and end any of them; a replayed refresh token invalidates the whole family.'
  },
  {
    title: 'Sign in with Google',
    body: 'Or an email and password. Either way the tokens live in httpOnly cookies, not in browser storage.'
  },
  {
    title: 'Free while it is being built',
    body: 'No card, no trial timer. Paid tiers are not live and nothing is metered today.'
  }
] as const;

export const SUPPORT = {
  heading: 'Something not adding up in the numbers?',
  body: 'The whole point of this product is that a figure can be traced back to where it came from. If one cannot, that is a bug worth reporting.',
  cta: { to: '/settings/help', label: 'Get help' }
} as const;

/**
 * FAQ. Answers stay inside the claim contract at the top of this file — in
 * particular, the polling cadence is stated rather than called "real time",
 * and nothing here promises a tool that is still a placeholder.
 */
export const FAQ = [
  {
    q: 'Do I need a broker account to use it?',
    a: 'No. A deterministic simulator drives every screen, and it is always labelled as simulated, so you can judge the product before connecting anything. Connecting FYERS swaps the simulator for live data.'
  },
  {
    q: 'Can it place trades for me?',
    a: 'No, and it never will by accident — there is no order, position or funds path in the product at all. The broker connection is read-only.'
  },
  {
    q: 'How current is the data?',
    a: 'Screens refresh every 15 seconds, and the intraday archive records a snapshot a minute through the session. Each response tells you whether it came from the broker, from cache, or from the simulator, and how old it is.'
  },
  {
    q: 'Which instruments does it cover?',
    a: 'NIFTY, BANKNIFTY and SENSEX options, plus the tradable future as an overlay on the intraday charts.'
  },
  {
    q: 'What does it cost?',
    a: 'Nothing today. Billing is not live, there are no paid tiers to choose between, and nothing is metered.'
  },
  {
    q: 'Is this investment advice?',
    a: 'No. MarketCompass is analytics software, not a SEBI-registered investment adviser. It shows you what the option chain is doing and leaves the conclusions to you.'
  }
] as const;

/** Real integrations, in place of borrowed press logos. */
export const STACK = ['NSE', 'FYERS', 'Google SSO', 'PostgreSQL', 'Redis'] as const;

export const CLOSING = {
  eyebrow: 'Get started',
  headingLead: 'Open the terminal',
  headingKeyword: 'and see today’s chain.',
  lead: 'Free while the product is in development. No card, and no broker account to begin with.'
} as const;

export const NAV_LINKS = [
  { to: '/dashboard', label: 'Dashboard' },
  { to: '/option-chain', label: 'Option chain' },
  { to: '/analyse', label: 'Price analysis' }
] as const;

/** Only shipped tools. The other nineteen Options Lab routes are placeholders. */
export const NAV_TOOLS = [
  { to: '/options/open-interest', label: 'Open Interest' },
  { to: '/options/multi-oi-volume', label: 'Multi OI & Volume' },
  { to: '/options/pcr', label: 'Put-Call Ratio' },
  { to: '/options/max-pain', label: 'Max Pain' },
  { to: '/options/gamma-exposure', label: 'Gamma Exposure' }
] as const;

export const FOOTER: readonly { title: string; links: readonly { to: string; label: string }[] }[] =
  [
    {
      title: 'Terminal',
      links: [
        { to: '/dashboard', label: 'Dashboard' },
        { to: '/advanced-dashboard', label: 'Advanced dashboard' },
        { to: '/option-chain', label: 'Option chain' },
        { to: '/analyse', label: 'Price analysis' }
      ]
    },
    {
      title: 'Options Lab',
      links: [
        { to: '/options', label: 'Overview' },
        { to: '/options/open-interest', label: 'Open Interest' },
        { to: '/options/multi-oi-volume', label: 'Multi OI & Volume' },
        { to: '/options/pcr', label: 'Put-Call Ratio' },
        { to: '/options/max-pain', label: 'Max Pain' },
        { to: '/options/gamma-exposure', label: 'Gamma Exposure' }
      ]
    },
    {
      title: 'Account',
      links: [
        { to: '/register', label: 'Create account' },
        { to: '/login', label: 'Sign in' },
        { to: '/settings/broker', label: 'Connect a broker' },
        { to: '/settings/security', label: 'Sessions & security' }
      ]
    },
    {
      title: 'Support',
      links: [
        { to: '/settings/help', label: 'Help' },
        { to: '/settings', label: 'Plans' },
        { to: '/settings/global', label: 'Preferences' }
      ]
    }
  ];

export const DISCLAIMER =
  'For educational and informational purposes only. MarketCompass is analytics software and ' +
  'not a SEBI-registered investment adviser. Nothing here is investment advice, a ' +
  'recommendation, or a solicitation to buy or sell any security. Markets carry risk.';
