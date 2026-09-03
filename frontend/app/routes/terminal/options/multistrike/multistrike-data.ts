/**
 * Wire types and pure derivations for the MultiStrike Chart tool.
 *
 * There is no endpoint of its own: `straddle-series` already ships a whole
 * session of per-strike call and put last prices on one shared strike axis, so
 * "the premium of 23950 CE" is an index lookup rather than a request. Picking a
 * leg, dropping one, changing the view mode and re-bucketing the timeframe are
 * therefore all free — same trade Premium Decay makes against the same payload.
 *
 * Everything below is pure, so the basket arithmetic is testable without a
 * canvas. The one rule worth stating up front is how a missing quote behaves in
 * a total: see {@link sumLegs}.
 */

// Shared session/clock/window helpers, reused rather than duplicated so this
// page reads the same session the rest of the Options Lab does.
export {
  CALL_COLOR,
  PUT_COLOR,
  OI_INSTRUMENTS,
  REFETCH_MS,
  STALE_AFTER_MS,
  clockLabel,
  dateLabel,
  freshnessLabel,
  timeLabel,
  type Instrument
} from '../open-interest/oi-data';

// The payload, its fetcher and the timeframe machinery are the Straddle
// chart's; this page reads the same endpoint through the same types.
export {
  bucketIndices,
  DEFAULT_TIMEFRAME,
  expiryLabel,
  fmtPrice,
  futureSeries,
  getStraddle,
  pick,
  TIMEFRAMES,
  type StraddleFrame,
  type StraddleView,
  type Timeframe
} from '../atm-straddle/straddle-data';

import { fmtPrice, type StraddleView } from '../atm-straddle/straddle-data';

// -- the selection ----------------------------------------------------------

export type Side = 'CE' | 'PE';

/** One selected contract: a strike and which side of it. */
export interface Leg {
  strike: number;
  side: Side;
}

/**
 * How many contracts may be plotted at once.
 *
 * Ten is the palette's length and the same cap the Multi OI contract picker
 * uses — past it the lines stop being separable by colour, which is the only
 * thing telling them apart.
 */
export const MAX_PICKS = 10;

/** Stable identity for a leg — the series id, and the React key. */
export function legKey(leg: Leg): string {
  return `${leg.strike}-${leg.side}`;
}

/** `23950 CE` — what the chip, the ladder cell and the legend all say. */
export function legLabel(leg: Leg): string {
  return `${leg.strike} ${leg.side}`;
}

/** `23950 CE Price` — the chart legend and tooltip name. */
export function legSeriesLabel(leg: Leg): string {
  return `${legLabel(leg)} Price`;
}

export function hasLeg(legs: Leg[], leg: Leg): boolean {
  return legs.some((entry) => entry.strike === leg.strike && entry.side === leg.side);
}

/**
 * Add a leg, or drop it if it is already picked. Order is pick order, which is
 * what assigns the colours — so re-adding a leg puts it at the end and it comes
 * back a different colour. Deliberate: the alternative is holding a slot open
 * for something the reader removed.
 */
export function toggleLeg(legs: Leg[], leg: Leg): Leg[] {
  if (hasLeg(legs, leg)) {
    return legs.filter((entry) => !(entry.strike === leg.strike && entry.side === leg.side));
  }
  return legs.length >= MAX_PICKS ? legs : [...legs, leg];
}

/** The ATM call and put — what the page opens on. Empty off an empty ladder. */
export function defaultLegs(view: StraddleView | undefined): Leg[] {
  const atm = view?.atm_strike;
  if (view === undefined || atm == null || !view.strikes.includes(atm)) return [];
  return [
    { strike: atm, side: 'CE' },
    { strike: atm, side: 'PE' }
  ];
}

/** Drops legs whose strike left the ladder — the axis rolls with the ATM. */
export function legsOnLadder(legs: Leg[], view: StraddleView | undefined): Leg[] {
  if (view === undefined) return legs;
  return legs.filter((leg) => view.strikes.includes(leg.strike));
}

// -- series derivations -----------------------------------------------------

/**
 * One leg's premium through the session, one value per frame.
 *
 * `null` where that leg was not quoted at that capture, and all-null for a
 * strike that is not on the axis at all — the chart draws a gap either way,
 * which is the honest reading of "nothing was recorded".
 */
export function legSeries(view: StraddleView, leg: Leg): (number | null)[] {
  const index = view.strikes.indexOf(leg.strike);
  if (index < 0) return view.frames.map(() => null);
  const side = leg.side === 'CE' ? 'ce_ltp' : 'pe_ltp';
  return view.frames.map((frame) => frame[side][index] ?? null);
}

/**
 * The total premium of a basket of legs, one value per frame.
 *
 * A frame sums the legs that *were* quoted and is `null` only when every one of
 * them is missing. This is deliberately unlike `strikeStraddleSeries`, which
 * voids a frame if either leg is gone: half a straddle is a wrong number, but a
 * basket total with one dead wing is still the premium the rest of the basket
 * carried, and blanking the whole line for it loses far more than it protects.
 *
 * An empty basket has no total at all, not a line of zeros.
 */
export function sumLegs(view: StraddleView, legs: Leg[]): (number | null)[] {
  if (legs.length === 0) return view.frames.map(() => null);
  const columns = legs.map((leg) => legSeries(view, leg));
  return view.frames.map((_, row) => {
    let total = 0;
    let quoted = false;
    for (const column of columns) {
      const value = column[row];
      if (value == null) continue;
      total += value;
      quoted = true;
    }
    return quoted ? total : null;
  });
}

// -- view mode --------------------------------------------------------------

/** How the basket is read: leg by leg, calls against puts, or as one number. */
export type ViewMode = 'individual' | 'call_put' | 'combined';

export const VIEW_MODES: readonly { value: ViewMode; label: string }[] = [
  { value: 'individual', label: 'Individual' },
  { value: 'call_put', label: 'Call vs Put' },
  { value: 'combined', label: 'Combined' }
];

export function callLegs(legs: Leg[]): Leg[] {
  return legs.filter((leg) => leg.side === 'CE');
}

export function putLegs(legs: Leg[]): Leg[] {
  return legs.filter((leg) => leg.side === 'PE');
}

// -- formatting -------------------------------------------------------------

/** A premium — points, two decimals, the way the chain quotes them. */
export function fmtPremium(value: number): string {
  return value.toFixed(2);
}

export { fmtPrice as fmtFuture };

// -- CSV export -------------------------------------------------------------

/**
 * The plotted lines as a table: one column per series, plus the future.
 *
 * Exports what is on screen — the mode's series after bucketing — rather than
 * the raw payload, so a reader who zoomed into 15m buckets gets the 15m rows.
 */
export function multistrikeCsv(
  times: string[],
  futures: (number | null)[],
  columns: { label: string; values: (number | null)[] }[]
): string {
  const header = ['time', 'future', ...columns.map((column) => csvHeader(column.label))].join(',');
  const body = times.map((time, row) =>
    [time, futures[row] ?? '', ...columns.map((column) => column.values[row] ?? '')].join(',')
  );
  return [header, ...body].join('\n');
}

function csvHeader(label: string): string {
  return label.toLowerCase().replace(/\s+/g, '_');
}

/** `multistrike-NIFTY-2026-09-03.csv` — sortable, and says which day it is. */
export function csvFilename(symbol: string, view: StraddleView | undefined): string {
  if (!view) return `multistrike-${symbol}.csv`;
  return `multistrike-${symbol}-${view.now_ts.slice(0, 10)}.csv`;
}
