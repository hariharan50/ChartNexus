/**
 * Wire types and pure derivations for Multi OI & Volume.
 *
 * The endpoint sends a shared time axis plus raw `oi` and `volume` arrays per
 * contract; everything the three charts actually plot is derived here. Keeping
 * it pure means the arithmetic is unit-testable without a canvas, and switching
 * which contracts are shown never waits on a round trip.
 */

import { apiFetch } from '$shared/api/client';

/**
 * Buckets the API will downsample to.
 *
 * `disabled` is spelled out on every entry rather than present only where it is
 * true: a union of differently-shaped literals makes the flag invisible to a
 * plain property read, which is how `1D` shipped selectable the first time.
 */
export const INTERVALS: readonly { value: Interval; label: string; disabled: boolean }[] = [
  { value: '1m', label: '1m', disabled: false },
  { value: '5m', label: '5m', disabled: false },
  { value: '15m', label: '15m', disabled: false },
  { value: '1h', label: '1h', disabled: false },
  // Needs history across sessions, which the archive does not keep yet.
  { value: '1D', label: '1D', disabled: true }
];

export type Interval = '1m' | '5m' | '15m' | '1h' | '1D';
export const DEFAULT_INTERVAL: Interval = '1m';

/** How many contracts the two top-N pickers offer. */
export const TOP_N_CHOICES = [3, 5, 8, 10] as const;

export const REFETCH_MS = 15_000;

export interface ContractSeries {
  id: string;
  strike: number;
  option_type: 'CE' | 'PE';
  oi: number[];
  volume: number[];
}

export interface OiSeriesView {
  instrument_id: string;
  symbol: string;
  expiry_date: string | null;
  atm_strike: number;
  lot_size: number | null;
  open_ts: string;
  now_ts: string;
  data_quality: 'intraday' | 'live_proxy' | 'empty';
  open_is_estimated: boolean;
  /** The bucket actually used, which may be coarser than the one requested. */
  interval: string;
  window: number;
  t: string[];
  fut: (number | null)[];
  contracts: ContractSeries[];
  default_ids: string[];
  default_vol_ids: string[];
}

export function getOiSeries(
  instrument: string,
  interval: Interval,
  fetcher?: typeof fetch
): Promise<OiSeriesView> {
  return apiFetch<OiSeriesView>({
    url: `/options-lab/oi-series/${encodeURIComponent(instrument)}`,
    params: { interval },
    fetcher
  });
}

/** Which quantity a chart plots. */
export type Metric = 'oi' | 'change' | 'volume';

/**
 * The series for one contract under one metric.
 *
 * `change` is derived rather than transmitted: index 0 is the session open, so
 * `oi[i] - oi[0]` is the change since the open — the same derivation the Open
 * Interest page makes. Sending it as a third array would double as a second
 * source of truth for a figure the two pages have to agree on.
 */
export function metricValues(contract: ContractSeries, metric: Metric): number[] {
  if (metric === 'volume') return contract.volume;
  if (metric === 'oi') return contract.oi;
  const open = contract.oi[0] ?? 0;
  return contract.oi.map((value) => value - open);
}

/** `24700 CE` — how a contract reads in the legend and the chips. */
export function contractLabel(contract: ContractSeries): string {
  return `${contract.strike} ${contract.option_type}`;
}

/** The n contracts with the largest latest reading, biggest first. */
export function topByLatest(
  contracts: ContractSeries[],
  metric: 'oi' | 'volume',
  count: number
): string[] {
  return [...contracts]
    .sort((a, b) => {
      const delta = (b[metric].at(-1) ?? 0) - (a[metric].at(-1) ?? 0);
      // Ties settle on the contract id so a refetch cannot silently reshuffle
      // the selection — and with it every colour on the page.
      return delta !== 0 ? delta : a.id.localeCompare(b.id);
    })
    .slice(0, count)
    .map((contract) => contract.id);
}

/**
 * Net put-minus-call OI change across the chosen contracts.
 *
 * Positive means puts are being written faster than calls — the classic read
 * for support building under the market.
 */
export function peMinusCe(contracts: ContractSeries[]): number[] {
  const length = contracts[0]?.oi.length ?? 0;
  const net = Array.from({ length }, () => 0);
  for (const contract of contracts) {
    const sign = contract.option_type === 'PE' ? 1 : -1;
    const change = metricValues(contract, 'change');
    for (let i = 0; i < length; i++) net[i]! += sign * (change[i] ?? 0);
  }
  return net;
}

/** Compact Indian units, or whole lots when `showLot`. */
export function fmtOi(value: number, showLot = false, lotSize = 75): string {
  if (showLot && lotSize > 0) return Math.round(value / lotSize).toLocaleString('en-IN');
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

/** `10:03 am` in IST. The axis is a trading session, not the viewer's day. */
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
