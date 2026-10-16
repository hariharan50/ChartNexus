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

/**
 * The picker helpers now live in the catalog context, because the header
 * search needs the same ranking this page established. Re-exported here so
 * this module stays the one import the page reaches for.
 */
export {
  filterInstruments,
  toPickerEntries,
  type PickerEntry
} from '$contexts/instrument-catalog/search';

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
