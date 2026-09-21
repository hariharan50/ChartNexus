/**
 * Wire type and fetch for Future Lab → Price vs OI.
 *
 * The endpoint sends two aligned lines on a shared time axis — the front-month
 * future's price and **that contract's own open interest** — plus the session
 * tier the chart captions.
 *
 * The OI here is futures open interest, not the option chain's. The Options
 * Lab serves a similar-looking series whose OI line sums every strike, because
 * when it was written the application captured no futures OI at all; it does
 * now, and the two pages answer different questions. Every label on this page
 * has to keep saying which one it means.
 *
 * Formatting helpers are shared with Multi OI & Volume rather than duplicated:
 * the two pages render the same kinds of number.
 */

import { apiFetch } from '$shared/api/client';
import { DEFAULT_INTERVAL, type Interval } from '../options/multi-oi-volume/multi-oi-data';

export {
  DEFAULT_INTERVAL,
  expiryLabel,
  fmtOi,
  fmtPrice,
  timeLabel,
  type Interval
} from '../options/multi-oi-volume/multi-oi-data';
export { feedAgeLabel, feedAgeMs } from '../options/open-interest/oi-data';

export const REFETCH_MS = 15_000;

/** What the page calls the OI line, everywhere it is named. */
export const OI_LABEL = 'Futures OI';

export interface PriceOiView {
  instrument_id: string;
  symbol: string;
  expiry_date: string | null;
  open_ts: string;
  now_ts: string;
  data_quality: 'intraday' | 'live_proxy' | 'empty';
  open_is_estimated: boolean;
  /** The bucket actually used, which may be coarser than the one requested. */
  interval: string;
  /** Where the numbers came from — a generated board must never read as live. */
  source: 'live' | 'mock';
  /** ISO timestamps, one per point. */
  t: string[];
  /** Front-month future price, aligned to `t`. */
  price: (number | null)[];
  /**
   * That contract's open interest, aligned to `t`.
   *
   * `null` where a frame fell between open-interest sweeps, which run slower
   * than price captures. A genuine gap — never coerce it to zero, which would
   * draw a cliff to the axis and back that never happened.
   */
  oi: (number | null)[];
}

/**
 * Fetch the series. `date` (ISO, e.g. `2026-09-18`) replays that archived
 * session for Historical mode; omit it for today (Live).
 */
export function getPriceOiSeries(
  instrument: string,
  opts: { interval?: Interval; date?: string | undefined } = {},
  fetcher?: typeof fetch
): Promise<PriceOiView> {
  const params: Record<string, string> = { interval: opts.interval ?? DEFAULT_INTERVAL };
  if (opts.date) params['date'] = opts.date;
  return apiFetch<PriceOiView>({
    url: `/futures/price-oi-series/${encodeURIComponent(instrument)}`,
    params,
    fetcher
  });
}

// -- instrument picker -------------------------------------------------------

/** One row in the picker, derived from the catalog rather than hardcoded. */
export interface PickerEntry {
  symbol: string;
  name: string;
  /** Two or three characters for the badge — the catalog has no logos. */
  badge: string;
}

/**
 * Narrow the universe to what someone typed.
 *
 * Symbol matches sort ahead of name matches, and a prefix ahead of a
 * mid-string hit: typing "TCS" should not bury the contract called TCS under
 * every company whose description happens to contain it.
 */
export function filterInstruments(
  entries: PickerEntry[],
  search: string,
  limit = 60
): PickerEntry[] {
  const needle = search.trim().toUpperCase();
  if (!needle) return entries.slice(0, limit);

  const scored: { entry: PickerEntry; rank: number }[] = [];
  for (const entry of entries) {
    const symbol = entry.symbol.toUpperCase();
    const name = entry.name.toUpperCase();
    if (symbol === needle) scored.push({ entry, rank: 0 });
    else if (symbol.startsWith(needle)) scored.push({ entry, rank: 1 });
    else if (symbol.includes(needle)) scored.push({ entry, rank: 2 });
    else if (name.startsWith(needle)) scored.push({ entry, rank: 3 });
    else if (name.includes(needle)) scored.push({ entry, rank: 4 });
  }
  scored.sort((a, b) => a.rank - b.rank || a.entry.symbol.localeCompare(b.entry.symbol));
  return scored.slice(0, limit).map((hit) => hit.entry);
}

/** An index sits at the top of the list; the stocks follow alphabetically. */
export function toPickerEntries(
  rows: { symbol: string; name: string; kind: string }[]
): PickerEntry[] {
  return [...rows]
    .sort((a, b) => {
      if (a.kind !== b.kind) return a.kind === 'index' ? -1 : 1;
      return a.symbol.localeCompare(b.symbol);
    })
    .map((row) => ({ symbol: row.symbol, name: row.name, badge: badgeFor(row.symbol) }));
}

function badgeFor(symbol: string): string {
  // The leading letters, not an abbreviation anyone has to learn: two of them
  // fit the circle at every symbol length, and the full ticker sits beside it.
  return symbol
    .replace(/[^A-Z0-9]/gi, '')
    .slice(0, 2)
    .toUpperCase();
}

// -- replay ------------------------------------------------------------------

/**
 * How far replay may wind forward.
 *
 * The whole session arrives in one payload, so replay is a cursor over it
 * rather than a second request. In Live mode the cursor still stops at the
 * last captured frame: winding past it would show a future the archive does
 * not contain.
 */
export function clampCursor(cursor: number, frames: number): number {
  if (frames <= 0) return 0;
  return Math.min(Math.max(cursor, 0), frames - 1);
}

/** The visible slice at a replay position. `null` cursor means "everything". */
export function sliceTo<T>(values: T[], cursor: number | null): T[] {
  if (cursor === null) return values;
  return values.slice(0, clampCursor(cursor, values.length) + 1);
}
