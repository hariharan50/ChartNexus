/**
 * Wire types and pure derivations for the IV Intraday page.
 *
 * Two views over two very different sources, and the split is not cosmetic:
 *
 * * **Intraday** reads the archive — at-the-money volatility at every capture of
 *   a session, against the future. One expiry, because one expiry is all the
 *   archive holds: the ingest worker fetches the chain with no expiry argument,
 *   so what it stores is always the nearest contract, rolling forward as each
 *   one dies.
 * * **Term Structure** reads live chains, one per expiry. It has no history and
 *   cannot have any — a term structure is several expiries priced at the *same
 *   instant*, and no archived session contains more than one.
 *
 * Everything the Intraday view draws is derived here from the Volatility Skew
 * payload, which already carries per-strike IV per frame and now the future
 * alongside it.
 */

import { apiFetch } from '$shared/api/client';

// The skew payload is this page's intraday source, and its module already
// re-exports the instrument list, the clock helpers and `expiryLabel`.
export {
  clockLabel,
  dateLabel,
  expiryLabel,
  freshnessLabel,
  getSkew,
  OI_INSTRUMENTS,
  REFETCH_MS,
  STALE_AFTER_MS,
  timeLabel,
  type Instrument,
  type SkewFrame,
  type SkewView
} from '../volatility-skew/volatility-skew-data';

// The timeframe machinery and the price formatter are the Straddle chart's.
export {
  bucketIndices,
  DEFAULT_TIMEFRAME,
  fmtPrice,
  pick,
  TIMEFRAMES,
  type Timeframe
} from '../atm-straddle/straddle-data';

import type { SkewFrame, SkewView } from '../volatility-skew/volatility-skew-data';

// -- views ------------------------------------------------------------------

export type ViewMode = 'intraday' | 'term';

export const VIEW_MODES: readonly { value: ViewMode; label: string }[] = [
  { value: 'intraday', label: 'Intraday' },
  { value: 'term', label: 'Term Structure' }
];

// -- the intraday series ----------------------------------------------------

/**
 * One capture's at-the-money implied volatility.
 *
 * The mean of the call and the put at the money, falling back to whichever side
 * was quoted, and `null` when neither was. The same blend the Volatility Skew
 * page applies at the money, so the two pages cannot disagree about what "ATM
 * IV" is on the same session.
 *
 * `null` — never a neighbouring strike's reading. The strike beside the money
 * is a different contract, and quietly substituting it would draw a curve of
 * numbers that were never the ATM volatility.
 */
export function atmIv(frame: SkewFrame, strikes: number[]): number | null {
  const atm = frame.atm;
  if (atm === null) return null;
  const index = strikes.indexOf(atm);
  if (index < 0) return null;

  const call = frame.ce_iv[index] ?? null;
  const put = frame.pe_iv[index] ?? null;
  if (call === null && put === null) return null;
  if (call === null) return put;
  if (put === null) return call;
  return (call + put) / 2;
}

/** The ATM IV line, one value per capture. */
export function ivSeries(view: SkewView): (number | null)[] {
  return view.frames.map((frame) => atmIv(frame, view.strikes));
}

/** The tradable future overlay, one value per capture. */
export function futureSeries(view: SkewView): (number | null)[] {
  return view.frames.map((frame) => frame.future);
}

// -- the term structure -----------------------------------------------------

export interface TermPoint {
  /** The expiry the broker answered with, `YYYY-MM-DD`. */
  expiry: string;
  /** Volatility points; `null` where that chain quoted none at the money. */
  atm_iv: number | null;
  days_to_expiry: number | null;
}

export interface TermStructureView {
  instrument_id: string;
  symbol: string;
  spot: number;
  as_of: string;
  points: TermPoint[];
}

export function getTermStructure(
  instrument: string,
  expiries: string[],
  fetcher?: typeof fetch
): Promise<TermStructureView> {
  return apiFetch<TermStructureView>({
    url: `/options-lab/term-structure/${encodeURIComponent(instrument)}`,
    params: { expiries: expiries.join(',') },
    fetcher
  });
}

// -- expiry selection -------------------------------------------------------

/**
 * How many expiries the term structure may draw at once.
 *
 * Five, as the reference caps it. Each one is a separate broker call, and a
 * curve is read point by point — past a handful it says less rather than more.
 */
export const MAX_EXPIRIES = 5;

/** Add an expiry, or drop it if already picked. Silently refuses past the cap. */
export function toggleExpiry(picked: string[], expiry: string): string[] {
  if (picked.includes(expiry)) return picked.filter((entry) => entry !== expiry);
  return picked.length >= MAX_EXPIRIES ? picked : [...picked, expiry];
}

/**
 * The nearest three, so the view opens on a curve rather than a single point.
 *
 * Three because two points are a line segment and say nothing about shape,
 * while five broker calls on first paint is a slow open for a default.
 */
export function defaultExpiries(expiries: string[]): string[] {
  return [...expiries].sort().slice(0, 3);
}

/** `08 Sep` — short enough for a chip, unlike the full `expiryLabel`. */
export function shortExpiry(iso: string): string {
  const date = new Date(`${iso.slice(0, 10)}T00:00:00Z`);
  if (Number.isNaN(date.getTime())) return iso;
  return new Intl.DateTimeFormat('en-GB', {
    day: '2-digit',
    month: 'short',
    timeZone: 'UTC'
  }).format(date);
}

// -- readings ---------------------------------------------------------------

/**
 * Whether every quoted point on the curve carries the same volatility.
 *
 * Worth detecting rather than drawing: a dead-flat term structure is what a
 * provider that ignores the expiry argument produces, and a reader looking at
 * one deserves to be told which of the two they are seeing.
 */
export function isFlatCurve(points: TermPoint[]): boolean {
  const quoted = points.map((point) => point.atm_iv).filter((iv): iv is number => iv !== null);
  if (quoted.length < 2) return false;
  return quoted.every((iv) => Math.abs(iv - quoted[0]!) < 1e-9);
}

/** A volatility, two decimals — what the reference's tooltip shows. */
export function fmtIv(value: number): string {
  return value.toFixed(2);
}

// -- CSV export -------------------------------------------------------------

export function intradayCsv(
  times: string[],
  iv: (number | null)[],
  future: (number | null)[]
): string {
  const header = 'time,iv,future';
  const body = times.map((time, index) => [time, iv[index] ?? '', future[index] ?? ''].join(','));
  return [header, ...body].join('\n');
}

export function termCsv(points: TermPoint[]): string {
  const header = 'expiry,atm_iv,days_to_expiry';
  const body = points.map((point) =>
    [point.expiry, point.atm_iv ?? '', point.days_to_expiry ?? ''].join(',')
  );
  return [header, ...body].join('\n');
}

/** `iv-intraday-NIFTY-2026-09-03.csv` — sortable, and says which day it is. */
export function csvFilename(symbol: string, view: ViewMode, day: string | undefined): string {
  const slug = view === 'term' ? 'term-structure' : 'iv-intraday';
  return day ? `${slug}-${symbol}-${day.slice(0, 10)}.csv` : `${slug}-${symbol}.csv`;
}
