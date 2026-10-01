/**
 * Wire types and pure derivations for the Option Greeks tool.
 *
 * The endpoint ships a whole session of both legs' five greeks in one payload,
 * so the tab and the interval are both applied here — neither costs a round
 * trip. Same trade the Options Lab series pages make, and the bucketing helpers
 * are literally theirs rather than a second implementation that rounds its
 * buckets differently at the edges.
 */

import { apiFetch } from '$shared/api/client';

export {
  bucketIndices,
  pick,
  DEFAULT_TIMEFRAME,
  TIMEFRAMES,
  type Timeframe
} from '../../options/atm-straddle/straddle-data';

export {
  CALL_COLOR,
  PUT_COLOR,
  OI_INSTRUMENTS,
  REFETCH_MS,
  timeLabel,
  type Instrument
} from '../../options/open-interest/oi-data';

/** One leg's five series, aligned index-for-index with {@link GreeksView.t}. */
export interface GreekLeg {
  iv: (number | null)[];
  delta: (number | null)[];
  gamma: (number | null)[];
  theta: (number | null)[];
  vega: (number | null)[];
  ltp: (number | null)[];
}

export interface GreeksView {
  instrument_id: string;
  symbol: string;
  expiry_date: string | null;
  lot_size: number | null;
  /** The pinned strike every series is read at. */
  strike: number | null;
  atm_strike: number | null;
  spot: number;
  ce_symbol: string | null;
  pe_symbol: string | null;
  open_ts: string;
  now_ts: string;
  data_quality: 'intraday' | 'live' | 'empty';
  /** Share of frames, 0-1, where both legs carried a usable IV. */
  iv_coverage: number;
  t: string[];
  underlying: number[];
  ce: GreekLeg;
  pe: GreekLeg;
}

export function getGreeks(
  instrument: string,
  opts: {
    date?: string | undefined;
    expiry?: string | undefined;
    strike?: number | undefined;
  } = {},
  fetcher?: typeof fetch
): Promise<GreeksView> {
  return apiFetch<GreeksView>({
    url: `/options-lab/greeks/${encodeURIComponent(instrument)}`,
    params: {
      ...(opts.date ? { date: opts.date } : {}),
      ...(opts.expiry ? { expiry: opts.expiry } : {}),
      ...(opts.strike ? { strike: String(opts.strike) } : {})
    },
    fetcher
  });
}

// -- the five tabs ----------------------------------------------------------

export type GreekKey = 'iv' | 'delta' | 'theta' | 'vega' | 'gamma';

export interface GreekTab {
  key: GreekKey;
  label: string;
  /** What the number means, one line, shown under the charts. */
  note: string;
}

/**
 * Tab order is the reference terminal's, which is also the order a reader
 * reaches for: what volatility is doing, then direction, then the two decays.
 */
export const GREEK_TABS: readonly GreekTab[] = [
  {
    key: 'iv',
    label: 'IV',
    note: 'Implied volatility in points, as the broker quotes it — the only greek on this page that is read, not derived.'
  },
  {
    key: 'delta',
    label: 'Delta',
    note: 'Change in the option’s price per one point of the underlying. Calls run 0 to 1, puts 0 to -1.'
  },
  {
    key: 'theta',
    label: 'Theta',
    note: 'Rupees the option loses per calendar day, holding everything else still. Negative for a long position.'
  },
  {
    key: 'vega',
    label: 'Vega',
    note: 'Rupees the option gains per one-point (1%) rise in implied volatility.'
  },
  {
    key: 'gamma',
    label: 'Gamma',
    note: 'How fast delta itself moves per one point of the underlying — small on an index, largest at the money.'
  }
];

export const DEFAULT_GREEK: GreekKey = 'iv';

/** The chosen tab's series for one leg. */
export function legSeries(leg: GreekLeg, greek: GreekKey): (number | null)[] {
  return leg[greek];
}

// -- formatting -------------------------------------------------------------

/**
 * Each greek gets the precision it is read at, not a shared one.
 *
 * Gamma is 1e-3-small on an index: at four places it renders as a staircase of
 * `0.0011`, and at two it is a flat zero. IV is a percentage and says so.
 */
export function formatGreek(greek: GreekKey, value: number): string {
  if (greek === 'iv') return `${value.toFixed(2)}%`;
  if (greek === 'gamma') return value.toFixed(6);
  return value.toFixed(4);
}

export function formatPrice(value: number): string {
  return value.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

/** The most recent value that exists, or `null` when the leg never priced. */
export function latestOf(values: (number | null)[]): number | null {
  for (let index = values.length - 1; index >= 0; index--) {
    const value = values[index];
    if (value != null) return value;
  }
  return null;
}

/**
 * What the charts can say about where the data came from.
 *
 * `live` is not a degradation to hide: it means the snapshot archive has
 * nothing for this session, so there is one point rather than a session. A page
 * that drew that single point without saying so would look like a flat market.
 */
export function qualityNote(view: GreeksView | undefined): string | null {
  if (!view) return null;
  if (view.data_quality === 'empty') {
    return 'No captures for this session yet — the archive is written by the ingest worker.';
  }
  if (view.data_quality === 'live') {
    return 'One live reading: nothing was archived for this session, so there is no intraday history to draw.';
  }
  if (view.iv_coverage < 1) {
    const missing = Math.round((1 - view.iv_coverage) * 100);
    return `${missing}% of captures had no quoted volatility on one leg; those points are gaps, not zeros.`;
  }
  return null;
}
