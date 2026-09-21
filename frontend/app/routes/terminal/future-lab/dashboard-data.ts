import type { BuildupState, FuturesRow } from '$contexts/futures-analytics/types';

/** Formatting and labelling for the Future Dashboard. */

/**
 * Comparison windows the board can be measured over.
 *
 * Only `prev` works today. The backend derives every percentage from each
 * contract's own previous close and previous open interest, which needs no
 * stored history. The intraday windows need a snapshot archive of the whole
 * board that does not exist yet — so they are listed and disabled rather than
 * quietly missing, because the gap is a roadmap item and not an oversight.
 */
export const COMPARE_WINDOWS = [
  { id: 'prev', label: 'Prev', available: true },
  { id: '3m', label: '3m', available: false },
  { id: '5m', label: '5m', available: false },
  { id: '15m', label: '15m', available: false },
  { id: '1h', label: '1h', available: false }
] as const;

export type CompareWindow = (typeof COMPARE_WINDOWS)[number]['id'];

export const PENDING_WINDOW_HINT =
  'Intraday comparison needs a stored board history, which is not captured yet.';

/** Panel headings, in the order the reference terminal shows them. */
/**
 * The six panels, in two rows of three.
 *
 * Ordered by `tone`, not by pairs: the top row is every state where price is
 * rising — gainers, longs being added, shorts being covered — and the bottom
 * row every state where it is falling. Read down a column and the two rows
 * answer the same question from opposite sides, which a Gainers/Losers/Long
 * Buildup first row would have chopped in half.
 */
export const PANELS: { key: PanelKey; title: string; tone: PanelTone }[] = [
  { key: 'top_gainers', title: 'Top Gainers', tone: 'up' },
  { key: 'long_buildup', title: 'Long Buildup', tone: 'up' },
  { key: 'short_covering', title: 'Short Covering', tone: 'up' },
  { key: 'top_losers', title: 'Top Losers', tone: 'down' },
  { key: 'short_buildup', title: 'Short Buildup', tone: 'down' },
  { key: 'long_unwinding', title: 'Long Unwinding', tone: 'down' }
];

export type PanelKey =
  | 'top_gainers'
  | 'top_losers'
  | 'long_buildup'
  | 'short_buildup'
  | 'short_covering'
  | 'long_unwinding';

export type PanelTone = 'up' | 'down';

const STATE_LABELS: Record<BuildupState, string> = {
  long_buildup: 'Long Buildup',
  short_buildup: 'Short Buildup',
  short_covering: 'Short Covering',
  long_unwinding: 'Long Unwinding',
  neutral: 'Neutral'
};

export function stateLabel(state: BuildupState): string {
  return STATE_LABELS[state] ?? state;
}

const price = new Intl.NumberFormat('en-IN', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2
});

export function fmtPrice(value: string | number | null): string {
  const n = toNumber(value);
  return n === null ? '—' : price.format(n);
}

/**
 * A signed percentage, or an em dash.
 *
 * The dash is load-bearing: the API returns null when a contract had no prior
 * close to measure against, and rendering that as "0.00%" would assert that it
 * did not move — a claim nobody made.
 */
export function fmtPercent(value: string | number | null): string {
  const n = toNumber(value);
  if (n === null) return '—';
  return `${n >= 0 ? '+' : ''}${n.toFixed(2)}%`;
}

export function fmtOi(value: number | null): string {
  if (value === null || value === undefined) return '—';
  if (Math.abs(value) >= 1e7) return `${(value / 1e7).toFixed(2)}Cr`;
  if (Math.abs(value) >= 1e5) return `${(value / 1e5).toFixed(2)}L`;
  if (Math.abs(value) >= 1e3) return `${(value / 1e3).toFixed(1)}K`;
  return String(value);
}

/** Direction for colouring, or null when there is nothing to colour. */
export function direction(value: string | number | null): 'up' | 'down' | null {
  const n = toNumber(value);
  if (n === null || n === 0) return null;
  return n > 0 ? 'up' : 'down';
}

export function toNumber(value: string | number | null | undefined): number | null {
  if (value === null || value === undefined || value === '') return null;
  const n = typeof value === 'number' ? value : Number(value);
  return Number.isFinite(n) ? n : null;
}

/** Sectors present in the data, for the filter. Empty until sectors are seeded. */
export function sectorsIn(rows: FuturesRow[]): string[] {
  const seen = new Set<string>();
  for (const row of rows) {
    if (row.sector) seen.add(row.sector);
  }
  return [...seen].sort((a, b) => a.localeCompare(b));
}
