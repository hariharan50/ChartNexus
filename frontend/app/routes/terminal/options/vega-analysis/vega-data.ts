/**
 * Wire types and pure derivations for the Vega Analysis tool.
 *
 * The endpoint ships a full session of per-strike aggregate vega in one payload,
 * so the strike window and the timeframe are both applied here — neither costs a
 * round trip. Same trade as Gamma Exposure and the Put-Call Ratio tool, for the
 * same reason: what the server sends is small enough that the client can hold it
 * all. Everything is pure, so the arithmetic is testable without a canvas.
 */

import { apiFetch } from '$shared/api/client';

// Shared session/clock/window helpers, reused rather than duplicated so Vega
// Analysis reads the same session the OI-family pages do.
export {
  CALL_COLOR,
  PUT_COLOR,
  OI_INSTRUMENTS,
  REFETCH_MS,
  STALE_AFTER_MS,
  clockLabel,
  dateLabel,
  freshnessLabel,
  inferStep,
  sessionPositions,
  sessionTicks,
  timeLabel,
  withinWindow,
  type Instrument
} from '../open-interest/oi-data';

/** One capture's aggregate-vega profile, plus the synthetic future. */
export interface VegaFrame {
  t: string;
  spot: number;
  atm: number | null;
  /** Put-call-parity forward, falling back to the tradable future; `null` rare. */
  synth_future: number | null;
  /**
   * Aligned to {@link VegaView.strikes}, in **vega per contract per one
   * volatility point** — deliberately not weighted by open interest.
   * Both sides positive — the page plots each side's change since the open, and
   * that delta is what carries the sign.
   */
  call_vega: number[];
  put_vega: number[];
}

export interface VegaView {
  instrument_id: string;
  symbol: string;
  expiry_date: string | null;
  lot_size: number | null;
  spot: number;
  atm_strike: number | null;
  open_ts: string;
  now_ts: string;
  data_quality: 'intraday' | 'empty';
  open_is_estimated: boolean;
  /** 0–1. Below 1, some legs had no quoted volatility and contributed zero. */
  iv_coverage: number;
  strikes: number[];
  t: string[];
  frames: VegaFrame[];
}

export function getVega(
  instrument: string,
  opts: { date?: string | undefined; expiry?: string | undefined } = {},
  fetcher?: typeof fetch
): Promise<VegaView> {
  return apiFetch<VegaView>({
    url: `/options-lab/vega/${encodeURIComponent(instrument)}`,
    params: {
      ...(opts.date ? { date: opts.date } : {}),
      ...(opts.expiry ? { expiry: opts.expiry } : {})
    },
    fetcher
  });
}

// -- timeframe --------------------------------------------------------------

export type Timeframe = '1m' | '3m' | '5m' | '15m';
export const DEFAULT_TIMEFRAME: Timeframe = '1m';

export const TIMEFRAMES: readonly { value: Timeframe; label: string }[] = [
  { value: '1m', label: '1m' },
  { value: '3m', label: '3m' },
  { value: '5m', label: '5m' },
  { value: '15m', label: '15m' }
];

/** Minutes each timeframe covers. */
const TIMEFRAME_MINUTES: Record<Timeframe, number> = {
  '1m': 1,
  '3m': 3,
  '5m': 5,
  '15m': 15
};

/**
 * Indices to keep when resampling to a timeframe. Client-side on purpose: the
 * whole payload is a few numbers a capture, so bucketing here makes switching
 * 1m → 15m instant rather than a round trip.
 *
 * Keeps the **last** point in each bucket, and always the first point overall —
 * the session open anchors every change on the page, so it must survive whatever
 * bucket it lands in. Vega deltas are stocks, not flows: averaging a bucket would
 * print a reading the market never showed.
 */
export function bucketIndices(times: string[], timeframe: Timeframe): number[] {
  const minutes = TIMEFRAME_MINUTES[timeframe] ?? 1;
  if (times.length === 0) return [];
  if (minutes <= 1) return times.map((_, index) => index);

  const size = minutes * 60_000;
  const origin = Date.parse(times[0]!);
  const lastOfBucket = new Map<number, number>();

  for (let index = 0; index < times.length; index++) {
    lastOfBucket.set(Math.floor((Date.parse(times[index]!) - origin) / size), index);
  }

  const kept = [...lastOfBucket.values()].sort((a, b) => a - b);
  return kept[0] === 0 ? kept : [0, ...kept];
}

/** Applies a bucketing to any array aligned with the time axis. */
export function pick<T>(values: T[], indices: number[]): T[] {
  return indices.map((index) => values[index]!);
}

// -- strike window ----------------------------------------------------------

/** How the vega is aggregated across the strike ladder. */
export type StrikeMode = 'auto' | 'fixed';

/** Strikes either side of ATM summed into each side's aggregate. */
export const STRIKE_SPAN = 10;

/**
 * Sum one frame's vega on each side over the strikes in `visible`.
 *
 * `visible` is a set of strike prices rather than indices so the caller can build
 * it with the same `withinWindow` the other Options Lab pages use, and the two
 * windows are guaranteed to agree.
 */
export function frameTotals(
  strikes: number[],
  frame: VegaFrame,
  visible: Set<number>,
  money: number
): { call: number; put: number } {
  // Each side is summed over the strikes it is out of the money at: calls from
  // `money` up, puts from `money` down. The strike itself belongs to both,
  // which is where the two curves meet at the open.
  //
  // Not cosmetic. Summing both sides over the *same* strikes makes the two
  // lines near-identical — vega is a property of the strike, so a call and a
  // put struck together have the same one — and the page then draws one curve
  // twice. Split, they answer the question being asked: which side of the money
  // is bleeding volatility value as spot moves away from it.
  //
  // **`money` is pinned by the caller, not read off `frame`.** This series is a
  // change since the session open, and a change is only meaningful if the two
  // buckets hold the same strikes at both ends. Re-splitting on each frame's
  // own ATM lets strikes migrate from the put bucket to the call bucket as spot
  // moves, so the delta would report that reclassification as if it were vega
  // moving — the larger effect, on a trending day, by far.
  let call = 0;
  let put = 0;
  for (let i = 0; i < strikes.length; i++) {
    const strike = strikes[i]!;
    if (!visible.has(strike)) continue;
    if (strike >= money) call += frame.call_vega[i] ?? 0;
    if (strike <= money) put += frame.put_vega[i] ?? 0;
  }
  return { call, put };
}

// -- formatting -------------------------------------------------------------

/** `+1.24`, `-9.69` — a signed vega delta in points, two decimals. */
export function fmtVega(value: number): string {
  const sign = value > 0 ? '+' : '';
  return `${sign}${value.toFixed(2)}`;
}

/** The synth-future price, grouped Indian-style with no decimals. */
export function fmtPrice(value: number): string {
  return value.toLocaleString('en-IN', { maximumFractionDigits: 0 });
}

/** `18 Aug 2026 (4d)` — the expiry with how long is left on it. */
export function expiryLabel(iso: string | null): string {
  if (!iso) return 'Nearest expiry';
  const date = new Date(iso);
  const days = Math.max(0, Math.round((date.getTime() - Date.now()) / 86_400_000));
  const label = new Intl.DateTimeFormat('en-GB', {
    day: '2-digit',
    month: 'short',
    year: 'numeric'
  }).format(date);
  return `${label} (${days === 0 ? 'today' : `${days}d`})`;
}

// -- CSV export -------------------------------------------------------------

/** One row of the table/export: a bucketed capture with both deltas. */
export interface VegaRow {
  t: string;
  synth: number | null;
  call: number;
  put: number;
  diff: number;
}

/** The visible series as a spreadsheet — what is on screen, not the whole payload. */
export function vegaCsv(rows: VegaRow[]): string {
  const header = 'time,synth_future,call_vega_delta,put_vega_delta,put_minus_call';
  const body = rows.map((row) => [row.t, row.synth ?? '', row.call, row.put, row.diff].join(','));
  return [header, ...body].join('\n');
}

/** `vega-NIFTY-2026-08-14.csv` — sortable, and says which day it is. */
export function csvFilename(symbol: string, view: VegaView | undefined): string {
  if (!view) return `vega-${symbol}.csv`;
  const day = view.now_ts.slice(0, 10);
  return `vega-${symbol}-${day}.csv`;
}
