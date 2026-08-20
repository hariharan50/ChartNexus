/**
 * Wire types and pure derivations for Smart OI.
 *
 * The payload carries two axes with different lengths on purpose — see the
 * service docstring — and this module keeps them apart at the type level so a
 * caller cannot quietly zip one against the other.
 *
 * Everything here is pure and free of the chart libraries, so the derivations
 * are unit-testable without a canvas.
 */

import { apiFetch } from '$shared/api/client';
import type { Candle, VolumeBar } from '$shared/charts/tv/LwChart';

// Session, clock and formatting helpers are the Open Interest page's, imported
// rather than re-derived: the Options Lab tools have to agree about what "the
// open", "stale" and "1.2Cr" mean while sitting next to each other in one menu.
export {
  CALL_COLOR,
  OI_INSTRUMENTS,
  PUT_COLOR,
  REFETCH_MS,
  STALE_AFTER_MS,
  clockLabel,
  dateLabel,
  fmtOi,
  fmtSigned,
  freshnessLabel,
  timeLabel,
  type Instrument
} from '../open-interest/oi-data';

// -- wire -------------------------------------------------------------------

/** One price bar of the underlying, at the requested interval. */
export interface SmartOiBar {
  /** ISO 8601, UTC — the instant the bar opens. */
  t: string;
  o: number;
  h: number;
  l: number;
  c: number;
}

export interface SmartOiView {
  instrument_id: string;
  symbol: string;
  expiry_date: string | null;
  lot_size: number | null;
  atm_strike: number;
  open_ts: string;
  now_ts: string;
  data_quality: 'intraday' | 'live_proxy' | 'empty';
  open_is_estimated: boolean;
  /** The bucket actually used, which can be coarser than the one requested. */
  interval: string;
  strike_low: number | null;
  strike_high: number | null;

  // -- frame axis: the archive's capture cadence --
  t: string[];
  fut: (number | null)[];
  call_oi_chg: number[];
  put_oi_chg: number[];
  pe_ce_chg: number[];
  /** `null`, never 0, where the denominator was empty. */
  oi_pcr: (number | null)[];
  vol_pcr: (number | null)[];

  // -- bar axis: the candle grid --
  bars: SmartOiBar[];
  /** `null` where no capture landed in that bar — not the same as "nothing happened". */
  smart_oi: (number | null)[];
  call_vol: (number | null)[];
  put_vol: (number | null)[];
}

export type Interval = '1m' | '3m' | '5m' | '15m';
export const DEFAULT_INTERVAL: Interval = '5m';
export const INTERVALS: readonly { value: Interval; label: string }[] = [
  { value: '1m', label: '1m' },
  { value: '3m', label: '3m' },
  { value: '5m', label: '5m' },
  { value: '15m', label: '15m' }
];

export type StrikeMode = 'auto' | 'fixed';
export type RangeMode = 'range' | 'custom';

/**
 * Choices for the "± Range" selector, in strikes either side of ATM.
 *
 * `null` is "All" — the whole listed chain. It is the widest reading and the
 * least informative one, which is why it is not the default: a PCR computed
 * over three hundred strikes is dominated by wings nobody is trading.
 */
export const SPANS: readonly { value: number | null; label: string }[] = [
  { value: 5, label: '± 5' },
  { value: 10, label: '± 10' },
  { value: 20, label: '± 20' },
  { value: 40, label: '± 40' },
  { value: null, label: 'All' }
];
export const DEFAULT_SPAN: number | null = 10;

export interface SmartOiParams {
  interval: Interval;
  mode: StrikeMode;
  span: number | null;
  minStrike?: number | undefined;
  maxStrike?: number | undefined;
  expiry?: string | undefined;
  date?: string | undefined;
}

export function getSmartOi(
  instrument: string,
  params: SmartOiParams,
  fetcher?: typeof fetch
): Promise<SmartOiView> {
  return apiFetch<SmartOiView>({
    url: `/options-lab/smart-oi/${encodeURIComponent(instrument)}`,
    params: {
      interval: params.interval,
      mode: params.mode,
      // Omitted, not sent as a sentinel: the endpoint reads absence as "the
      // whole chain", and `span=0` would be rejected by its own bounds.
      ...(params.span === null ? {} : { span: params.span }),
      ...(params.minStrike === undefined ? {} : { min_strike: params.minStrike }),
      ...(params.maxStrike === undefined ? {} : { max_strike: params.maxStrike }),
      ...(params.expiry ? { expiry: params.expiry } : {}),
      ...(params.date ? { date: params.date } : {})
    },
    fetcher
  });
}

// -- chart shapes -----------------------------------------------------------

/**
 * Bars as the price chart's library wants them.
 *
 * Epoch **seconds**, not milliseconds: the library silently mis-scales a
 * millisecond value into the year 56,000 rather than rejecting it, so the bug
 * presents as an empty chart with no error — the same trap the Analyse page
 * documents.
 */
export function toCandles(bars: SmartOiBar[]): Candle[] {
  return bars.map((bar) => ({
    time: Math.floor(Date.parse(bar.t) / 1000),
    open: bar.o,
    high: bar.h,
    low: bar.l,
    close: bar.c
  }));
}

/** A signed series as coloured histogram points, keeping `null` gaps intact. */
export function toFlowBars(
  bars: SmartOiBar[],
  values: (number | null)[],
  colors: { up: string; down: string }
): { time: number; value: number | null; color: string }[] {
  return bars.map((bar, index) => {
    const value = values[index] ?? null;
    return {
      time: Math.floor(Date.parse(bar.t) / 1000),
      value,
      color: (value ?? 0) >= 0 ? colors.up : colors.down
    };
  });
}

/** An unsigned series (volume) as histogram points in one fixed colour. */
export function toVolumeBars(
  bars: SmartOiBar[],
  values: (number | null)[],
  color: string
): { time: number; value: number | null; color: string }[] {
  return bars.map((bar, index) => ({
    time: Math.floor(Date.parse(bar.t) / 1000),
    value: values[index] ?? null,
    color
  }));
}

/** Satisfies the price chart's own volume prop; unused here but kept type-honest. */
export type { VolumeBar };

// -- replay -----------------------------------------------------------------

/**
 * The frame index a bar-axis head corresponds to.
 *
 * The two axes have different lengths and different cadences, so a replay head
 * cannot be shared as an index — only as an instant. Returns the last frame at
 * or before the bar, which is what the reader was looking at when that bar
 * closed. `-1` when the sweep has not reached the first capture yet.
 */
export function frameHeadFor(times: string[], bars: SmartOiBar[], head: number): number {
  const bar = bars[head];
  if (!bar) return times.length - 1;
  const at = Date.parse(bar.t);
  let found = -1;
  for (let index = 0; index < times.length; index++) {
    if (Date.parse(times[index]!) <= at) found = index;
    else break;
  }
  return found;
}

// -- formatting -------------------------------------------------------------

const inr = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 });

/** A price as the axis and legend show it. */
export function fmtPrice(value: number): string {
  return inr.format(value);
}

/** A ratio, at the three decimals the reference prints. */
export function fmtRatio(value: number): string {
  return value.toFixed(3);
}

/** `"18 Aug 2026 (4d)"` — the expiry with how long is left on it. */
export function expiryLabel(iso: string | null): string {
  if (!iso) return 'Nearest expiry';
  const at = Date.parse(iso);
  if (Number.isNaN(at)) return iso;
  const days = Math.max(0, Math.ceil((at - Date.now()) / 86_400_000));
  const label = new Intl.DateTimeFormat('en-GB', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    timeZone: 'Asia/Kolkata'
  }).format(at);
  return `${label} (${days}d)`;
}

/** `(21200 - 27200)`, or nothing at all when there is no chain to window. */
export function windowLabel(low: number | null, high: number | null): string {
  if (low === null || high === null) return '';
  return `(${inr.format(low)} - ${inr.format(high)})`;
}

// -- export -----------------------------------------------------------------

/**
 * The bar-axis series as CSV.
 *
 * The bar axis rather than the frame axis, because the bars are what the page
 * is *about* — and mixing two different-length axes into one sheet would put
 * unrelated rows side by side.
 */
export function smartOiCsv(view: SmartOiView): string {
  const header = 'time,open,high,low,close,smart_oi,call_volume,put_volume';
  const rows = view.bars.map((bar, index) =>
    [
      bar.t,
      bar.o,
      bar.h,
      bar.l,
      bar.c,
      view.smart_oi[index] ?? '',
      view.call_vol[index] ?? '',
      view.put_vol[index] ?? ''
    ].join(',')
  );
  return [header, ...rows].join('\n');
}

export function csvFilename(symbol: string, interval: string): string {
  return `smart-oi-${symbol}-${interval}-${new Date().toISOString().slice(0, 10)}.csv`;
}
