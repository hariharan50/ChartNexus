/**
 * Wire types and pure derivations for the ATM Straddle Chart tool.
 *
 * The endpoint ships a full session of per-strike call/put last prices in one
 * payload, so the strike selection and the timeframe are both applied here —
 * neither costs a round trip. Same trade as Gamma Exposure and Vega Analysis.
 * Everything is pure, so the arithmetic (and the indicators) is testable without
 * a canvas.
 */

import { apiFetch } from '$shared/api/client';

// Shared session/clock/window helpers, reused rather than duplicated so the
// Straddle chart reads the same session the OI-family pages do.
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
  timeLabel,
  withinWindow,
  type Instrument
} from '../open-interest/oi-data';

/** One capture's per-strike premiums, the rolling ATM straddle, the future. */
export interface StraddleFrame {
  t: string;
  spot: number;
  atm: number | null;
  future: number | null;
  /** Call + put at this frame's ATM; `null` when either ATM leg is gone. */
  atm_straddle: number | null;
  /** Aligned to {@link StraddleView.strikes}; `null` where a leg was unquoted. */
  ce_ltp: (number | null)[];
  pe_ltp: (number | null)[];
}

export interface StraddleView {
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
  strikes: number[];
  t: string[];
  frames: StraddleFrame[];
}

export function getStraddle(
  instrument: string,
  opts: { date?: string | undefined } = {},
  fetcher?: typeof fetch
): Promise<StraddleView> {
  return apiFetch<StraddleView>({
    url: `/options-lab/straddle-series/${encodeURIComponent(instrument)}`,
    params: opts.date ? { date: opts.date } : {},
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

const TIMEFRAME_MINUTES: Record<Timeframe, number> = {
  '1m': 1,
  '3m': 3,
  '5m': 5,
  '15m': 15
};

/**
 * Indices to keep when resampling to a timeframe. Client-side on purpose: the
 * whole payload is one session, so switching 1m → 15m is instant rather than a
 * round trip. Keeps the last point of each bucket, and always the open.
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

// -- series selection -------------------------------------------------------

/** What the chart plots: the rolling ATM straddle, or one fixed strike. */
export type Selection = 'auto' | number;

/** The rolling ATM straddle line, one value per frame. */
export function atmStraddleSeries(view: StraddleView): (number | null)[] {
  return view.frames.map((frame) => frame.atm_straddle);
}

/** The tradable future overlay, one value per frame. */
export function futureSeries(view: StraddleView): (number | null)[] {
  return view.frames.map((frame) => frame.future);
}

/**
 * One fixed strike's straddle through the session: `ce_ltp + pe_ltp` at that
 * strike, `null` on any frame where either leg was unquoted.
 */
export function strikeStraddleSeries(view: StraddleView, strike: number): (number | null)[] {
  const index = view.strikes.indexOf(strike);
  if (index < 0) return view.frames.map(() => null);
  return view.frames.map((frame) => {
    const call = frame.ce_ltp[index];
    const put = frame.pe_ltp[index];
    return call == null || put == null ? null : call + put;
  });
}

/** The plotted series for the current selection, plus a label for it. */
export function selectedSeries(
  view: StraddleView,
  selection: Selection
): { label: string; values: (number | null)[] } {
  if (selection === 'auto') {
    return { label: 'ATM Straddle', values: atmStraddleSeries(view) };
  }
  return {
    label: `${selection} Straddle`,
    values: strikeStraddleSeries(view, selection)
  };
}

// -- the sidebar strike table -----------------------------------------------

export interface StrikeRow {
  strike: number;
  call: number | null;
  put: number | null;
  straddle: number | null;
  atm: boolean;
}

/**
 * The strike table's rows from the latest frame, windowed around the money.
 *
 * The newest frame is the live chain the table describes; a strike outside the
 * shown window is dropped so the sidebar stays a readable dozen rows rather than
 * the whole ±25 axis the payload carries for selection.
 */
export function strikeTable(view: StraddleView, span: number): StrikeRow[] {
  const frame = view.frames.at(-1);
  if (!frame) return [];
  const atm = frame.atm ?? view.atm_strike;
  const rows: StrikeRow[] = [];
  for (let i = 0; i < view.strikes.length; i++) {
    const strike = view.strikes[i]!;
    if (atm != null && Math.abs(strike - atm) > span) continue;
    const call = frame.ce_ltp[i] ?? null;
    const put = frame.pe_ltp[i] ?? null;
    rows.push({
      strike,
      call,
      put,
      straddle: call == null || put == null ? null : call + put,
      atm: atm != null && strike === atm
    });
  }
  return rows;
}

// -- indicators (pure) ------------------------------------------------------

/**
 * Simple moving average over `period` points.
 *
 * `null` until the window first fills, and any `null` input voids the windows
 * that span it — an average that quietly skipped gaps would draw a smooth line
 * across a stretch the market never printed.
 */
export function sma(values: (number | null)[], period: number): (number | null)[] {
  return values.map((_, i) => {
    if (i + 1 < period) return null;
    let sum = 0;
    for (let j = i - period + 1; j <= i; j++) {
      const v = values[j];
      if (v == null) return null;
      sum += v;
    }
    return sum / period;
  });
}

/**
 * Exponential moving average, seeded with the first full `period` window's mean.
 *
 * Restarts after a `null`: the recurrence has no defined value to carry across a
 * gap, so it re-seeds once enough real points follow.
 */
export function ema(values: (number | null)[], period: number): (number | null)[] {
  const out: (number | null)[] = new Array(values.length).fill(null);
  const k = 2 / (period + 1);
  let prev: number | null = null;
  let run = 0;
  let seed = 0;
  for (let i = 0; i < values.length; i++) {
    const v = values[i];
    if (v == null) {
      prev = null;
      run = 0;
      seed = 0;
      continue;
    }
    if (prev == null) {
      run += 1;
      seed += v;
      if (run === period) {
        prev = seed / period;
        out[i] = prev;
      }
      continue;
    }
    prev = v * k + prev * (1 - k);
    out[i] = prev;
  }
  return out;
}

export interface Bands {
  upper: (number | null)[];
  lower: (number | null)[];
}

/**
 * Bollinger bands: the `period` SMA plus and minus `k` population deviations.
 *
 * Population, not sample, standard deviation — the band is a description of the
 * window in hand, not an estimate of a wider one.
 */
export function bollinger(values: (number | null)[], period: number, k: number): Bands {
  const mid = sma(values, period);
  const upper: (number | null)[] = new Array(values.length).fill(null);
  const lower: (number | null)[] = new Array(values.length).fill(null);
  for (let i = 0; i < values.length; i++) {
    const mean = mid[i];
    if (mean == null) continue;
    let variance = 0;
    let bad = false;
    for (let j = i - period + 1; j <= i; j++) {
      const v = values[j];
      if (v == null) {
        bad = true;
        break;
      }
      variance += (v - mean) * (v - mean);
    }
    if (bad) continue;
    const sd = Math.sqrt(variance / period);
    upper[i] = mean + k * sd;
    lower[i] = mean - k * sd;
  }
  return { upper, lower };
}

// -- formatting -------------------------------------------------------------

/** The straddle premium — points, two decimals. */
export function fmtStraddle(value: number): string {
  return value.toFixed(2);
}

/** The index/future price, grouped Indian-style with no decimals. */
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

/** One row of the export: a bucketed capture with the plotted straddle. */
export interface StraddleCsvRow {
  t: string;
  straddle: number | null;
  future: number | null;
}

export function straddleCsv(rows: StraddleCsvRow[], label: string): string {
  const header = `time,${label.toLowerCase().replace(/\s+/g, '_')},future`;
  const body = rows.map((row) => [row.t, row.straddle ?? '', row.future ?? ''].join(','));
  return [header, ...body].join('\n');
}

/** `straddle-NIFTY-2026-08-14.csv` — sortable, and says which day it is. */
export function csvFilename(symbol: string, view: StraddleView | undefined): string {
  if (!view) return `straddle-${symbol}.csv`;
  const day = view.now_ts.slice(0, 10);
  return `straddle-${symbol}-${day}.csv`;
}
