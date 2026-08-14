/**
 * Wire type and fetch for Future Lab → Price vs OI.
 *
 * The endpoint sends two aligned aggregate lines on a shared time axis — the
 * tradable future price and the whole chain's total open interest — plus the
 * session tier the chart captions. Formatting helpers are shared with Multi OI &
 * Volume rather than duplicated: the two pages read the same numbers.
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

export const INSTRUMENTS = [
  { short: 'NIFTY', badge: '50', symbol: 'NIFTY' },
  { short: 'SENSEX', badge: 'BSE', symbol: 'SENSEX' },
  { short: 'BANKNIFTY', badge: 'BNK', symbol: 'BANKNIFTY' }
] as const;

export interface PriceOiView {
  instrument_id: string;
  symbol: string;
  expiry_date: string | null;
  lot_size: number | null;
  open_ts: string;
  now_ts: string;
  data_quality: 'intraday' | 'live_proxy' | 'empty';
  open_is_estimated: boolean;
  /** The bucket actually used, which may be coarser than the one requested. */
  interval: string;
  /** ISO timestamps, one per point. */
  t: string[];
  /** Tradable future, aligned to `t`; `null` on the reconstructed 09:15 frame. */
  price: (number | null)[];
  /** Total open interest across the whole chain, aligned to `t`. */
  oi: number[];
}

/**
 * Fetch the series. `date` (ISO, e.g. `2026-08-13`) replays that archived
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
    url: `/options-lab/price-oi-series/${encodeURIComponent(instrument)}`,
    params,
    fetcher
  });
}
