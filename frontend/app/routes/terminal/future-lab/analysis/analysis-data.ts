/**
 * Shared vocabulary for the six Analysis pages.
 *
 * Formatting, labels and the small derivations every page needs. Kept in one
 * module because the pages quote each other's numbers constantly — a crore on
 * the Summary page and a crore on the Cash Market page must be the same
 * string, or a reader comparing the two will think the data disagrees.
 *
 * `toNumber` and the price/percent formatters are reused from the Future Lab's
 * stocks module rather than reimplemented: the two toolkits render the same
 * kinds of number and there is no reason for them to drift.
 */

import type {
  BreadthCount,
  FlowSegment,
  IndexHeader,
  OiParticipant,
  RotationQuadrant,
  WireNumber
} from '$contexts/market-breadth/types';
import { toNumber } from '../stocks-data';

export { fmtPercent, fmtPrice, toNumber } from '../stocks-data';

/*
 * The poll cadences the status strips print, re-exported from the queries that
 * own them so the number on screen is the interval actually in force.
 */
export { FLOW_REFRESH_SECONDS, INDEX_REFRESH_SECONDS } from '$contexts/market-breadth/queries';

// -- money -------------------------------------------------------------------

const crore = new Intl.NumberFormat('en-IN', {
  minimumFractionDigits: 0,
  maximumFractionDigits: 0
});

/**
 * Rupees crore, signed, or an em dash.
 *
 * No decimals: the published figures run to five digits and the second decimal
 * place of a ₹14,238 crore number is noise that costs column width. The sign is
 * always printed — on a flow board the direction *is* the reading, and a bare
 * "2,140" beside another "2,140" of the opposite sign would be unreadable.
 */
export function fmtCrore(value: WireNumber | null | undefined): string {
  const n = toNumber(value ?? null);
  if (n === null) return '—';
  return `${n > 0 ? '+' : n < 0 ? '−' : ''}${crore.format(Math.abs(n))}`;
}

/** Rupees crore with no sign — for gross buy and sell, which are never negative. */
export function fmtGross(value: WireNumber | null | undefined): string {
  const n = toNumber(value ?? null);
  return n === null ? '—' : crore.format(Math.abs(n));
}

/**
 * Index points, signed, to two decimals.
 *
 * Two decimals because a single member's contribution is routinely under a
 * point, and rounding those to integers would show a screenful of zeros.
 */
export function fmtPoints(value: WireNumber | null | undefined): string {
  const n = toNumber(value ?? null);
  if (n === null) return '—';
  return `${n > 0 ? '+' : n < 0 ? '−' : ''}${Math.abs(n).toFixed(2)}`;
}

/** A plain percentage with no sign — weights, shares, participation. */
export function fmtShare(value: WireNumber | null | undefined, digits = 2): string {
  const n = toNumber(value ?? null);
  return n === null ? '—' : `${n.toFixed(digits)}%`;
}

// -- dates -------------------------------------------------------------------

const shortDate = new Intl.DateTimeFormat('en-IN', { day: '2-digit', month: 'short' });
const longDate = new Intl.DateTimeFormat('en-IN', {
  day: '2-digit',
  month: 'short',
  year: 'numeric'
});

/** `18 Sep` — for a dense axis. */
export function dayLabel(iso: string): string {
  const parsed = new Date(iso);
  return Number.isNaN(parsed.getTime()) ? iso : shortDate.format(parsed);
}

/** `18 Sep 2026` — for a header, where the year matters. */
export function sessionLabel(iso: string | null): string {
  if (!iso) return 'No session published';
  const parsed = new Date(iso);
  return Number.isNaN(parsed.getTime()) ? iso : longDate.format(parsed);
}

// -- flows -------------------------------------------------------------------

/** How each segment is named on screen. */
export const SEGMENT_LABELS: Record<FlowSegment, string> = {
  cash: 'Cash Market',
  index_futures: 'Index Futures',
  index_options: 'Index Options',
  stock_futures: 'Stock Futures',
  stock_options: 'Stock Options'
};

/** How each participant is named on screen. */
export const PARTICIPANT_LABELS: Record<OiParticipant, string> = {
  fii: 'FII',
  dii: 'DII',
  pro: 'Pro',
  client: 'Client'
};

/**
 * A band's heading, whichever way the board is grouped.
 *
 * One lookup over both vocabularies: the view toggle swaps which of the two
 * keys a band carries, and the table should not have to know which it got.
 */
export function bandLabel(key: string): string {
  return PARTICIPANT_LABELS[key as OiParticipant] ?? SEGMENT_LABELS[key as FlowSegment] ?? key;
}

/**
 * A run of same-side sessions, in words.
 *
 * Signed on the wire; spelled out here because "+4" beside a rupee figure
 * reads as money, which is the one thing it is not.
 */
export function streakLabel(streak: number): string {
  if (streak === 0) return 'No run';
  const days = Math.abs(streak);
  const unit = days === 1 ? 'session' : 'sessions';
  return `${days} ${unit} ${streak > 0 ? 'buying' : 'selling'}`;
}

// -- index -------------------------------------------------------------------

/**
 * What the page says about the prices it is drawing.
 *
 * The header carries `basis`, and it changes what the numbers mean: a
 * front-month future tracks its underlying closely and diverges with carry and
 * the roll. Close enough to rank contributors; not the cash print, so the page
 * names it rather than letting a reader assume.
 */
export function basisLabel(header: IndexHeader | undefined): string {
  return header?.basis === 'futures' ? 'Front-month futures' : 'Cash market';
}

/**
 * Coverage, as the caption under a chart.
 *
 * Both halves matter: 48 of 50 names is a strong claim, and so is the 96% of
 * index weight they carry — a board missing two heavyweights and one missing
 * two minnows have the same member count and very different worth.
 */
export function coverageLabel(header: IndexHeader | undefined): string {
  if (!header) return '';
  const weight = toNumber(header.covered_weight_percent);
  const share = weight === null ? '' : ` · ${weight.toFixed(1)}% of index weight`;
  return `${header.covered} of ${header.universe} members priced${share}`;
}

/** Advances per decline as a reading, with the "nothing declined" case named. */
export function ratioLabel(count: BreadthCount | undefined): string {
  if (!count) return '—';
  const ratio = toNumber(count.ratio);
  if (ratio === null) return count.advancing > 0 ? 'All advancing' : '—';
  return `${ratio.toFixed(2)} : 1`;
}

// -- rotation ----------------------------------------------------------------

export interface QuadrantMeta {
  id: RotationQuadrant;
  label: string;
  /** What being in this quadrant means, for the legend and the hover card. */
  hint: string;
}

/**
 * The four quadrants, in reading order around the plot.
 *
 * The names are the relative-rotation convention and they carry the right
 * meaning here — strength with participation is leading, participation without
 * strength yet is improving, and so on. What the page must not imply is that
 * this is a classical RRG: the vertical axis is participation, not momentum,
 * and there is no multi-week tail. Each page that draws this prints that.
 */
export const QUADRANTS: QuadrantMeta[] = [
  { id: 'leading', label: 'Leading', hint: 'Ahead of the index, and broadly' },
  { id: 'improving', label: 'Improving', hint: 'Broad participation, not yet ahead' },
  { id: 'weakening', label: 'Weakening', hint: 'Ahead of the index on few names' },
  { id: 'lagging', label: 'Lagging', hint: 'Behind the index, and narrowly' }
];

export function quadrantMeta(quadrant: RotationQuadrant): QuadrantMeta {
  return QUADRANTS.find((entry) => entry.id === quadrant) ?? QUADRANTS[3]!;
}

// -- categorical grouping ----------------------------------------------------

/**
 * How many categories a categorical palette may carry before the tail folds.
 *
 * Eight is the palette's size, and a ninth slice is never a generated hue — it
 * would either repeat a colour already on the plot or land outside the
 * validated set. Seven named sectors plus "Other" keeps every slice inside the
 * palette and keeps the smallest one large enough to hover.
 */
export const CATEGORY_SLOTS = 8;

/** The bucket everything past the slots is folded into. */
export const OTHER_LABEL = 'Other';

export interface Slice<T> {
  label: string;
  value: number;
  /** The rows this slice stands for — one for a named slice, many for Other. */
  rows: T[];
}

/**
 * Largest categories first, with the tail folded into one "Other" slice.
 *
 * Returns at most `CATEGORY_SLOTS` entries. Folding rather than truncating
 * matters: a donut whose slices do not sum to the whole is not a share chart.
 */
export function foldToSlots<T>(
  rows: T[],
  label: (row: T) => string,
  value: (row: T) => number
): Slice<T>[] {
  const ranked = [...rows].sort((a, b) => value(b) - value(a));
  if (ranked.length <= CATEGORY_SLOTS) {
    return ranked.map((row) => ({ label: label(row), value: value(row), rows: [row] }));
  }

  const named = ranked.slice(0, CATEGORY_SLOTS - 1);
  const tail = ranked.slice(CATEGORY_SLOTS - 1);
  return [
    ...named.map((row) => ({ label: label(row), value: value(row), rows: [row] })),
    {
      label: OTHER_LABEL,
      value: tail.reduce((total, row) => total + value(row), 0),
      rows: tail
    }
  ];
}

// -- open interest -----------------------------------------------------------

/**
 * Lakhs above a lakh, plain counts below it.
 *
 * Contracts span four orders of magnitude across this board — an index
 * futures net in the tens of thousands beside a stock futures net in the
 * millions — and a column of raw integers at that spread is unreadable. One
 * lakh is the threshold because that is where the Indian reading of a number
 * changes anyway.
 *
 * Unsigned except for the minus: a net is a position, and a leading `+` on
 * every long reads as a change rather than a level. Use `fmtOiChange` where
 * the number *is* a change.
 */
export function fmtOiNet(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—';
  const abs = Math.abs(value);
  if (abs >= 100_000) return `${(value / 100_000).toFixed(2)} L`;
  return contracts.format(value);
}

/**
 * The same scale, always signed.
 *
 * A change of zero prints as a bare `0`: it is neither a gain nor a loss, and
 * `+0` would claim a direction that the arithmetic does not support.
 */
export function fmtOiChange(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—';
  if (value === 0) return '0';
  const abs = Math.abs(value);
  const sign = value > 0 ? '+' : '−';
  if (abs >= 100_000) return `${sign}${(abs / 100_000).toFixed(2)} L`;
  return `${sign}${contracts.format(abs)}`;
}

const contracts = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 });

/**
 * Residual below which a segment's four nets count as balanced.
 *
 * They must cancel exactly — every long is somebody's short — and on the
 * exchange's own file they very nearly do: the published participant rows
 * occasionally disagree with the published total by a contract or two, which
 * is the file's rounding and not a missing participant. Warning on that would
 * put a standing "this board is incomplete" notice under a board that is
 * complete, and a reader who learns to ignore the notice will ignore it on the
 * day it means something.
 */
export const OI_IMBALANCE_TOLERANCE = 10;

/** A plain contract count with no scaling — for the expanded leg breakdown. */
export function fmtContracts(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—';
  return contracts.format(value);
}
