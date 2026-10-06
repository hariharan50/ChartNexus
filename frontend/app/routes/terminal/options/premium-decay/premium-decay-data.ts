/**
 * Wire types and pure derivations for the Premium Decay tool.
 *
 * There is no Premium Decay endpoint: the tool reads the same
 * `/options-lab/straddle-series` payload the ATM Straddle chart does — a shared
 * strike axis plus, per capture, each strike's call and put last price and the
 * tradable future. Everything the two charts draw is a client-side aggregation
 * over that payload, so the strike window (ATM±range / fixed / custom), the
 * timeframe and the baseline all re-render without a round trip.
 *
 * The whole module is pure and keyed off the payload, so the arithmetic is
 * testable without a canvas.
 */

// The Premium Decay tool is a second reading of the Straddle session, so it
// reuses that tool's fetcher and wire types rather than restating them.
export {
  bucketIndices,
  DEFAULT_TIMEFRAME,
  expiryLabel,
  fmtPrice,
  futureSeries,
  getStraddle,
  pick,
  sma,
  TIMEFRAMES,
  type StraddleFrame,
  type StraddleView,
  type Timeframe
} from '../atm-straddle/straddle-data';

// Shared session/clock/window helpers, reused so Premium Decay reads the same
// session — and speaks the same call-green / put-red — as the OI-family pages.
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

import { inferStep, withinWindow } from '../open-interest/oi-data';
import type { StraddleView } from '../atm-straddle/straddle-data';

// -- strike selection -------------------------------------------------------

/** Which strikes the two charts aggregate over. */
export type SelectionMode = 'atm' | 'fixed' | 'custom';

export interface Selection {
  mode: SelectionMode;
  /** Steps either side of the money for the ATM window. */
  atmSpan: number;
  /** The anchor strike for the fixed window (`null` falls back to ATM). */
  fixedStrike: number | null;
  /** Steps either side of {@link fixedStrike}. */
  fixedSpan: number;
  /** Hand-picked strikes for the custom window. */
  customPicks: number[];
}

export const DEFAULT_ATM_SPAN = 3;
export const DEFAULT_FIXED_SPAN = 3;

/** The ATM strike to anchor a window on — the payload's, or the newest frame's. */
export function atmOf(view: StraddleView): number | null {
  return view.atm_strike ?? view.frames.at(-1)?.atm ?? null;
}

/** The resolved window: the strikes to total, and their span for the label. */
export interface Window {
  strikes: number[];
  /** `[low, high]` of the resolved strikes, or `null` when the window is empty. */
  range: [number, number] | null;
}

/**
 * The strikes a selection resolves to, always a subset of the payload's axis.
 *
 * A window that named a strike the session never carried would silently total
 * nothing for it, so every mode intersects with `view.strikes` — the axis the
 * per-frame `ce_ltp` / `pe_ltp` arrays are aligned to.
 */
export function resolveWindow(view: StraddleView, sel: Selection): Window {
  const axis = view.strikes;
  if (axis.length === 0) return { strikes: [], range: null };
  const step = inferStep(axis);
  const anchor = atmOf(view);

  let strikes: number[];
  if (sel.mode === 'custom') {
    const picks = new Set(sel.customPicks);
    strikes = axis.filter((s) => picks.has(s));
  } else if (sel.mode === 'fixed') {
    const base = sel.fixedStrike ?? anchor;
    strikes = base == null ? axis.slice() : withinWindow(axis, base, step, sel.fixedSpan);
  } else {
    strikes = anchor == null ? axis.slice() : withinWindow(axis, anchor, step, sel.atmSpan);
  }

  const range: [number, number] | null =
    strikes.length === 0 ? null : [strikes[0]!, strikes[strikes.length - 1]!];
  return { strikes, range };
}

/** Positions in the payload axis for a set of window strikes. */
export function windowIndices(axis: number[], windowStrikes: Iterable<number>): number[] {
  const want = new Set(windowStrikes);
  const out: number[] = [];
  for (let i = 0; i < axis.length; i++) {
    if (want.has(axis[i]!)) out.push(i);
  }
  return out;
}

// -- premium totals ---------------------------------------------------------

/** A call-side and put-side series, one value per frame. */
export interface Totals {
  ce: (number | null)[];
  pe: (number | null)[];
}

/**
 * Total call and put premium over the window, one point per frame.
 *
 * A leg quoted `null` is skipped rather than read as zero — a strike that
 * dropped off the chain for a capture should leave the total made of the legs
 * that were actually there, not dented by a phantom zero. A frame where the
 * whole window is missing totals `null`, so the line breaks rather than diving
 * to the floor.
 */
export function premiumTotals(view: StraddleView, indices: number[]): Totals {
  const ce: (number | null)[] = [];
  const pe: (number | null)[] = [];
  for (const frame of view.frames) {
    let ceSum = 0;
    let peSum = 0;
    let ceSeen = false;
    let peSeen = false;
    for (const i of indices) {
      const c = frame.ce_ltp[i];
      const p = frame.pe_ltp[i];
      if (c != null) {
        ceSum += c;
        ceSeen = true;
      }
      if (p != null) {
        peSum += p;
        peSeen = true;
      }
    }
    ce.push(ceSeen ? ceSum : null);
    pe.push(peSeen ? peSum : null);
  }
  return { ce, pe };
}

// -- baseline change --------------------------------------------------------

/**
 * What the Premium Decay chart anchors the change to.
 *
 * Both draw a cumulative "change since a reference" shape; they differ only in
 * the reference the change is read against, which is a constant per leg:
 *
 * - `day_open` reads each point against **today's opening** premium — the very
 *   first capture of the session.
 * - `min_close` reads it against the **close of the session's first bar** — the
 *   last capture inside the opening minute. The two differ only by whatever the
 *   premium did in that first minute, which is why the curves sit a few points
 *   apart and otherwise trace the same shape.
 *
 * **Both anchor inside today.** `min_close` used to read the *previous
 * session's* close, which is wrong twice over. It compares two different
 * instruments whenever the expiry rolls — on expiry day the prior session's
 * nearest contract is not this one at all — and it made the page depend on a
 * second fetch of a day the archive may hold only synthetic captures for. On
 * 6 Oct 2026 that baseline resolved to a seeded mock session 400 index points
 * away and reported a 1,785-point call "decay" that never happened.
 */
export type Baseline = 'day_open' | 'min_close';

/** The two totals a change series can be measured from. */
export interface PremiumRef {
  ce: number | null;
  pe: number | null;
}

/** The first point that actually printed a total — the session's opening premium. */
export function firstTotal(totals: (number | null)[]): number | null {
  for (const value of totals) {
    if (value != null) return value;
  }
  return null;
}

/**
 * A total series as the change against a fixed reference. A `null` point stays
 * `null`, and a `null` reference voids the whole series (the anchor is unknown).
 */
export function changeFromRef(totals: (number | null)[], ref: number | null): (number | null)[] {
  return totals.map((value) => (value == null || ref == null ? null : round2(value - ref)));
}

/**
 * The premium at the close of the session's first bar — the `min_close` anchor.
 *
 * Walks forward only while a capture still falls inside the opening bucket, and
 * keeps the last total each leg printed there. Measured on the *raw* series
 * rather than the bucketed one because bucketing deliberately keeps the
 * session's very first point as well, so the bucketed opener is the day's open
 * — which is the other baseline, not this one.
 *
 * Falls back to the first total when the opening minute carried a single
 * capture: with nothing to close against, the bar's open and close are the
 * same reading.
 */
export function firstBarClose(
  totals: (number | null)[],
  times: string[],
  minutes: number
): number | null {
  if (times.length === 0) return null;
  const origin = Date.parse(times[0]!);
  const span = Math.max(1, minutes) * 60_000;

  let last: number | null = null;
  for (let i = 0; i < times.length; i++) {
    if (Date.parse(times[i]!) - origin >= span) break;
    const value = totals[i];
    if (value != null) last = value;
  }
  return last ?? firstTotal(totals);
}

/**
 * The previous weekday before an ISO `YYYY-MM-DD` date.
 *
 * Skips Saturday and Sunday; market holidays are not modelled — a day with no
 * archived session simply comes back empty and the caller falls back to the
 * day-open reference.
 */
export function prevTradingDay(isoDate: string): string {
  const d = new Date(`${isoDate}T00:00:00Z`);
  do {
    d.setUTCDate(d.getUTCDate() - 1);
  } while (d.getUTCDay() === 0 || d.getUTCDay() === 6);
  return d.toISOString().slice(0, 10);
}

// -- running average --------------------------------------------------------

/** The default window for the Running Avg toggle, in points. */
export const RUNNING_AVG_PERIOD = 5;

// `runningAvg` is `sma` under a name that says what the toggle does; re-exported
// from the module top alongside the other straddle helpers.

// -- formatting -------------------------------------------------------------

/** A premium total — points, two decimals. */
export function fmtPremium(value: number): string {
  return value.toFixed(2);
}

/** A premium change — always signed, so a `+` reads as clearly as a `−`. */
export function fmtSignedPremium(value: number): string {
  return (value >= 0 ? '+' : '') + value.toFixed(2);
}

/** `24500 – 24700` — the strike span a window covers, for the sidebar label. */
export function rangeLabel(range: [number, number] | null): string {
  if (!range) return '—';
  const [low, high] = range;
  return low === high ? `${low}` : `${low} – ${high}`;
}

// -- CSV export -------------------------------------------------------------

/** One row of the export: a bucketed capture with both totals and the future. */
export interface PremiumCsvRow {
  t: string;
  ce: number | null;
  pe: number | null;
  future: number | null;
}

export function premiumDecayCsv(rows: PremiumCsvRow[]): string {
  const header = 'time,ce_premium,pe_premium,future';
  const body = rows.map((row) => [row.t, row.ce ?? '', row.pe ?? '', row.future ?? ''].join(','));
  return [header, ...body].join('\n');
}

/** `premium-decay-NIFTY-2026-08-14.csv` — sortable, and says which day it is. */
export function csvFilename(symbol: string, view: StraddleView | undefined): string {
  if (!view) return `premium-decay-${symbol}.csv`;
  const day = view.now_ts.slice(0, 10);
  return `premium-decay-${symbol}-${day}.csv`;
}

function round2(value: number): number {
  return Math.round(value * 100) / 100;
}
