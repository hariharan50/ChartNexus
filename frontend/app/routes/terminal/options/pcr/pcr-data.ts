/**
 * Wire types and pure derivations for the Put-Call Ratio tool.
 *
 * The endpoint sends chain-wide totals at the capture cadence and nothing else;
 * the timeframe is applied here. That is the opposite of Multi OI & Volume,
 * which downsamples server-side — deliberately, see {@link bucket}.
 */

import { apiFetch } from '$shared/api/client';

/** Timeframes the sidebar offers. `1D` needs history the archive does not keep. */
export const TIMEFRAMES: readonly { value: Timeframe; label: string; disabled: boolean }[] = [
  { value: '1m', label: '1m', disabled: false },
  { value: '5m', label: '5m', disabled: false },
  { value: '15m', label: '15m', disabled: false },
  { value: '1h', label: '1h', disabled: false },
  { value: '1D', label: '1D', disabled: true }
];

export type Timeframe = '1m' | '5m' | '15m' | '1h' | '1D';
export const DEFAULT_TIMEFRAME: Timeframe = '1m';

/** Minutes each timeframe covers. `1D` never reaches the bucketer. */
const TIMEFRAME_MINUTES: Record<Timeframe, number> = {
  '1m': 1,
  '5m': 5,
  '15m': 15,
  '1h': 60,
  '1D': 60 * 24
};

export const REFETCH_MS = 15_000;

export interface PcrSeriesView {
  instrument_id: string;
  symbol: string;
  expiry_date: string | null;
  lot_size: number | null;
  open_ts: string;
  now_ts: string;
  data_quality: 'intraday' | 'live_proxy' | 'empty';
  open_is_estimated: boolean;
  t: string[];
  /** The tradable future; `null` on the reconstructed 09:15 frame. */
  fut: (number | null)[];
  /** `null` where there was no call interest to divide by — never 0. */
  pcr: (number | null)[];
  call_oi: number[];
  put_oi: number[];
  call_oi_chg: number[];
  put_oi_chg: number[];
}

export function getPcrSeries(
  instrument: string,
  opts: { date?: string | undefined; expiry?: string | undefined } = {},
  fetcher?: typeof fetch
): Promise<PcrSeriesView> {
  return apiFetch<PcrSeriesView>({
    url: `/options-lab/pcr-series/${encodeURIComponent(instrument)}`,
    params: {
      ...(opts.date ? { date: opts.date } : {}),
      ...(opts.expiry ? { expiry: opts.expiry } : {})
    },
    fetcher
  });
}

/**
 * Indices to keep when resampling to a timeframe.
 *
 * Client-side on purpose. The whole payload is six numbers a capture — about
 * 15 KB for a session — so bucketing here makes switching 1m → 15m instant
 * rather than a round trip. Multi OI & Volume does the same job on the server
 * because its payload is ~80 contracts wide and the interval is the only real
 * lever on its size; the asymmetry is about payload, not preference.
 *
 * Keeps the **last** point in each bucket, and always the first point overall.
 * PCR and open interest are stocks, not flows: averaging a bucket would print
 * a reading the market never showed, and the final bucket would lag the live
 * figure beside it.
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
  // The session open anchors every change on the page; it must survive whatever
  // bucket it happens to land in.
  return kept[0] === 0 ? kept : [0, ...kept];
}

/** Applies a bucketing to any array aligned with the time axis. */
export function pick<T>(values: T[], indices: number[]): T[] {
  return indices.map((index) => values[index]!);
}

/** `0.95` — two decimals, because the third never changes a decision. */
export function fmtRatio(value: number): string {
  return value.toFixed(2);
}

/** Compact Indian units for the OI axes. */
export function fmtOi(value: number): string {
  const abs = Math.abs(value);
  const sign = value < 0 ? '-' : '';
  if (abs >= 1e7) return `${sign}${(abs / 1e7).toFixed(2)}Cr`;
  if (abs >= 1e5) return `${sign}${(abs / 1e5).toFixed(2)}L`;
  if (abs >= 1e3) return `${sign}${(abs / 1e3).toFixed(2)}K`;
  return `${sign}${Math.round(abs)}`;
}

export function fmtPrice(value: number): string {
  return value.toLocaleString('en-IN', { maximumFractionDigits: 0 });
}

/** `10:03 am` in IST — the axis is a trading session, not the viewer's day. */
export function timeLabel(iso: string): string {
  return new Intl.DateTimeFormat('en-US', {
    timeZone: 'Asia/Kolkata',
    hour: 'numeric',
    minute: '2-digit',
    hour12: true
  })
    .format(new Date(iso))
    .toLowerCase();
}

/** `11 Aug 2026 (5d)` — the expiry with how long is left on it. */
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
