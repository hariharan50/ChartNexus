import type { FuturesRow } from '$contexts/futures-analytics/types';
import { toNumber } from './stocks-data';

/** Filters and sizing for the Future Heatmap. */

export type HeatmapFilterId =
  | 'all'
  | 'gainers'
  | 'losers'
  | 'oi_gainers'
  | 'oi_losers'
  | 'long_buildup'
  | 'short_buildup'
  | 'short_covering'
  | 'long_unwinding';

export interface HeatmapFilter {
  id: HeatmapFilterId;
  label: string;
  matches: (row: FuturesRow) => boolean;
}

/**
 * The chips, in the order the reference reads them: everything, then the two
 * price halves, then the two open-interest halves, then the four positioning
 * states.
 *
 * A contract that did not move is in neither half of a pair — "gainers" and
 * "losers" are directions, not a partition, so the two counts deliberately do
 * not have to sum to the board.
 */
export const HEATMAP_FILTERS: HeatmapFilter[] = [
  { id: 'all', label: 'All', matches: () => true },
  { id: 'gainers', label: 'Top Gainers', matches: (row) => above(row.price_change_percent) },
  { id: 'losers', label: 'Top Losers', matches: (row) => below(row.price_change_percent) },
  { id: 'oi_gainers', label: 'OI Gainers', matches: (row) => above(row.oi_change_percent) },
  { id: 'oi_losers', label: 'OI Losers', matches: (row) => below(row.oi_change_percent) },
  { id: 'long_buildup', label: 'Long Buildup', matches: (row) => row.state === 'long_buildup' },
  { id: 'short_buildup', label: 'Short Buildup', matches: (row) => row.state === 'short_buildup' },
  {
    id: 'short_covering',
    label: 'Short Covering',
    matches: (row) => row.state === 'short_covering'
  },
  {
    id: 'long_unwinding',
    label: 'Long Unwinding',
    matches: (row) => row.state === 'long_unwinding'
  }
];

function above(value: string | null): boolean {
  const n = toNumber(value);
  return n !== null && n > 0;
}

function below(value: string | null): boolean {
  const n = toNumber(value);
  return n !== null && n < 0;
}

/** How many rows each chip would show. Always over the whole board, never the
 *  filtered view — otherwise selecting one chip would show it as the market. */
export function filterCounts(rows: FuturesRow[]): Record<HeatmapFilterId, number> {
  const counts = {} as Record<HeatmapFilterId, number>;
  for (const filter of HEATMAP_FILTERS) {
    counts[filter.id] = rows.reduce((total, row) => total + (filter.matches(row) ? 1 : 0), 0);
  }
  return counts;
}

export function applyFilter(rows: FuturesRow[], id: HeatmapFilterId): FuturesRow[] {
  const filter = HEATMAP_FILTERS.find((entry) => entry.id === id);
  return filter ? rows.filter(filter.matches) : rows;
}

// -- sizing -----------------------------------------------------------------

export const SIZE_OPTIONS = [
  { id: 'turnover', label: 'Turnover' },
  { id: 'volume', label: 'Volume' },
  { id: 'openInterest', label: 'Open Interest' },
  { id: 'equal', label: 'Equal' }
] as const;

export type HeatmapSizeId = (typeof SIZE_OPTIONS)[number]['id'];

// -- expiry -----------------------------------------------------------------

/**
 * `21 Sep 2026, 01:26:00 pm` — the exchange-local wall clock.
 *
 * Shares `dayMonthYear` with the expiry chip on purpose: the two sit inches
 * apart in the header, and a clock reading "21 Sept" beside a chip reading
 * "29 Sep" looks like a bug in one of them.
 */
export function clockLabel(now: Date): string {
  const time = new Intl.DateTimeFormat('en-GB', {
    timeZone: IST,
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: true
  }).format(now);
  return `${dayMonthYear(now)}, ${time}`;
}

/**
 * `23 Sep, 6:38:51 pm IST` — the status strip's clock.
 *
 * Shorter than `clockLabel` in two deliberate ways. The **year** is dropped:
 * it is a live wall clock, and nobody reading one is unsure which year it is.
 * The **zone** is named instead, which is the token that actually earns its
 * place — this app is read from outside India and a bare `6:38 pm` is
 * ambiguous in a way `23 Sep 2026` never was.
 */
export function sessionClockLabel(now: Date): string {
  const time = new Intl.DateTimeFormat('en-GB', {
    timeZone: IST,
    hour: 'numeric',
    minute: '2-digit',
    second: '2-digit',
    hour12: true
  }).format(now);
  return `${dayMonth(now)}, ${time} IST`;
}

/**
 * `29 Sep 2026 (8d)` — the contract and how long it has left.
 *
 * Days are counted in IST, because an expiry is an exchange-local date and a
 * browser in another timezone must not read it as a day out.
 */
export function expiryLabel(iso: string | null | undefined, now = new Date()): string {
  const { date, days } = expiryParts(iso, now);
  return days === null ? date : `${date} (${days}d)`;
}

/**
 * The same two facts, unjoined.
 *
 * The dropdown lays the date and the days-left out as separate columns so the
 * countdowns line up down the list; joining them into one string first and
 * splitting it again would be the long way round to the same place.
 */
export function expiryParts(
  iso: string | null | undefined,
  now = new Date()
): { date: string; days: number | null } {
  if (!iso) return { date: 'Front month', days: null };
  const expiry = new Date(`${iso}T00:00:00+05:30`);
  if (Number.isNaN(expiry.getTime())) return { date: 'Front month', days: null };

  const startOfToday = new Date(
    `${new Intl.DateTimeFormat('en-CA', { timeZone: IST }).format(now)}T00:00:00+05:30`
  );
  const days = Math.round((expiry.getTime() - startOfToday.getTime()) / 86_400_000);
  return { date: dayMonthYear(expiry), days: days < 0 ? null : days };
}

const IST = 'Asia/Kolkata';

/**
 * `29 Sep 2026`, in exchange-local time.
 *
 * Assembled from parts rather than taking the locale's whole string: recent ICU
 * renders September as "Sept" in en-GB, four characters wide in a chip sized
 * for three and odd beside every other month.
 */
function dayMonth(at: Date): string {
  const parts = _parts(at);
  return `${parts('day')} ${parts('month').slice(0, 3)}`;
}

function _parts(at: Date): (type: Intl.DateTimeFormatPartTypes) => string {
  const parts = new Intl.DateTimeFormat('en-GB', {
    timeZone: IST,
    day: '2-digit',
    month: 'short',
    year: 'numeric'
  }).formatToParts(at);
  return (type) => parts.find((entry) => entry.type === type)?.value ?? '';
}

function dayMonthYear(at: Date): string {
  const parts = new Intl.DateTimeFormat('en-GB', {
    timeZone: IST,
    day: '2-digit',
    month: 'short',
    year: 'numeric'
  }).formatToParts(at);
  const part = (type: Intl.DateTimeFormatPartTypes) =>
    parts.find((entry) => entry.type === type)?.value ?? '';
  return `${part('day')} ${part('month').slice(0, 3)} ${part('year')}`;
}
