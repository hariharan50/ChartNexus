/**
 * Formatting and grouping for GIA.
 *
 * `toNumber` and the tone helper are reused from the Future Lab rather than
 * re-declared: a percentage on this page and a percentage on the Analysis
 * pages must round the same way, or two screens quoting the same S&P move
 * would disagree by a decimal.
 */

import type {
  BandState,
  GapSignal,
  MarketRow,
  PressureBand,
  RegionId,
  SessionBandRow,
  Verdict,
  WireNumber
} from '$contexts/global-markets/types';
import { toNumber } from '../future-lab/stocks-data';

export { toNumber } from '../future-lab/stocks-data';

/** Regions in handoff order — the order the baton actually passes. */
export const REGION_ORDER: RegionId[] = ['asia', 'europe', 'americas', 'india', 'macro'];

/**
 * An index level, grouped Indian-style.
 *
 * Two decimals throughout: the reference boards quote NASDAQ to three
 * (26,936.037) but mixing precisions down a column makes it unreadable, and
 * the third decimal of a 27,000-point index is not a number anyone trades on.
 */
export function fmtLevel(value: WireNumber | null | undefined): string {
  const n = toNumber(value ?? null);
  if (n === null) return '—';
  return n.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

/** A signed change, to two decimals. The sign is the reading. */
export function fmtChange(value: WireNumber | null | undefined): string {
  const n = toNumber(value ?? null);
  if (n === null) return '—';
  return `${sign(n)}${Math.abs(n).toLocaleString('en-IN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  })}`;
}

/** A signed percentage, to two decimals. */
export function fmtPercent(value: WireNumber | null | undefined): string {
  const n = toNumber(value ?? null);
  if (n === null) return '—';
  return `${sign(n)}${Math.abs(n).toFixed(2)}%`;
}

/** A true minus sign, not a hyphen — it lines up in a tabular column. */
function sign(n: number): string {
  return n > 0 ? '+' : n < 0 ? '−' : '';
}

/** 'up' | 'down' | null. Null when there is nothing to colour. */
export function tone(value: WireNumber | null | undefined): 'up' | 'down' | null {
  const n = toNumber(value ?? null);
  if (n === null || n === 0) return null;
  return n > 0 ? 'up' : 'down';
}

/** An ISO instant as IST clock time. */
export function fmtIst(iso: string): string {
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) return '—';
  return parsed.toLocaleTimeString('en-IN', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
    timeZone: 'Asia/Kolkata'
  });
}

/** An ISO date as `24 Sep`. */
export function fmtDay(iso: string): string {
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) return iso;
  return parsed.toLocaleDateString('en-IN', {
    day: '2-digit',
    month: 'short',
    timeZone: 'Asia/Kolkata'
  });
}

export const PRESSURE_LABELS: Record<PressureBand, string> = {
  strong_down: 'STRONG GAP-DOWN PRESSURE',
  down: 'GAP-DOWN PRESSURE',
  flat: 'NO CLEAR PRESSURE',
  up: 'GAP-UP PRESSURE',
  strong_up: 'STRONG GAP-UP PRESSURE'
};

export const SIGNAL_LABELS: Record<GapSignal, string> = {
  gap_up: 'GAP UP',
  gap_down: 'GAP DOWN',
  flat: 'FLAT'
};

export const STATE_LABELS: Record<BandState, string> = {
  pending: 'Yet to open',
  live: 'Trading now',
  closed: 'Closed'
};

/**
 * What the two reads together are saying, in one sentence.
 *
 * `disagree` is deliberately not framed as an error or a warning: the world's
 * markets pointing one way while the contract that settles to NIFTY points the
 * other is a real fact about positioning, and it is the single most useful
 * thing this page can surface.
 */
export function verdictLine(verdict: Verdict): string {
  switch (verdict) {
    case 'agree':
      return 'GIFT NIFTY and the global composite point the same way.';
    case 'disagree':
      return 'GIFT NIFTY and the global composite disagree — the contract is pricing something the indices are not.';
    default:
      return 'Not enough of a move on one side to call agreement.';
  }
}

/** Whether the pressure band leans up, down, or neither — for colouring. */
export function bandTone(band: PressureBand): 'up' | 'down' | null {
  if (band === 'up' || band === 'strong_up') return 'up';
  if (band === 'down' || band === 'strong_down') return 'down';
  return null;
}

export function signalTone(signal: GapSignal): 'up' | 'down' | null {
  if (signal === 'gap_up') return 'up';
  if (signal === 'gap_down') return 'down';
  return null;
}

/** The board's rows, grouped into the regions that have any. */
export function byRegion(markets: MarketRow[]): { region: RegionId; rows: MarketRow[] }[] {
  return REGION_ORDER.map((region) => ({
    region,
    rows: markets.filter((row) => row.region === region)
  })).filter((group) => group.rows.length > 0);
}

/**
 * Bands stacked into lanes so overlapping sessions do not draw on top of one
 * another.
 *
 * Greedy first-fit: a band goes in the first lane whose last occupant ended
 * before it starts. Europe and the US overlap by two hours and Asia opens
 * while the US is still settling, so without this the timeline would be an
 * unreadable pile rather than a relay.
 */
export function intoLanes(bands: SessionBandRow[]): SessionBandRow[][] {
  const lanes: SessionBandRow[][] = [];
  for (const band of [...bands].sort((a, b) => a.start_fraction - b.start_fraction)) {
    const lane = lanes.find((row) => {
      const last = row[row.length - 1];
      return last !== undefined && last.end_fraction <= band.start_fraction;
    });
    if (lane) lane.push(band);
    else lanes.push([band]);
  }
  return lanes;
}

/**
 * An SVG path through a series, normalised to a 0–100 by 0–100 box.
 *
 * Returns an empty string for a series too short or too flat to draw, so the
 * caller renders nothing rather than a misleading horizontal line at the
 * bottom of the box.
 */
export function sparkPath(values: WireNumber[]): string {
  const points = values.map((value) => toNumber(value)).filter((n): n is number => n !== null);
  if (points.length < 2) return '';

  const min = Math.min(...points);
  const max = Math.max(...points);
  const span = max - min;
  // A perfectly flat series has no shape to show; draw it down the middle
  // rather than dividing by zero.
  const y = (value: number) => (span === 0 ? 50 : 100 - ((value - min) / span) * 100);
  const x = (index: number) => (index / (points.length - 1)) * 100;

  return points
    .map(
      (value, index) => `${index === 0 ? 'M' : 'L'}${x(index).toFixed(2)},${y(value).toFixed(2)}`
    )
    .join(' ');
}
