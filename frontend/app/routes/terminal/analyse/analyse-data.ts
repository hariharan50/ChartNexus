/**
 * Wire types and pure derivations for the Analyse price chart.
 *
 * The backend ships candles already aggregated at the requested interval, so
 * there is nothing to resample here. What this module does own is the shape
 * change between the API and the chart library — ISO timestamps to epoch
 * seconds, decimal strings to numbers — which is the only place those two
 * vocabularies are allowed to meet.
 */

import { apiFetch } from '$shared/api/client';
import type { Candle, VolumeBar } from '$shared/charts/tv/LwChart';

export interface WireCandle {
  /** ISO 8601, UTC. */
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface WireProvenance {
  source: 'live' | 'cached' | 'mock';
  fetched_at: string;
  age_seconds: number;
  is_stale: boolean;
}

export interface HistoryView {
  instrument: string;
  interval: string;
  candles: WireCandle[];
  provenance: WireProvenance;
}

export type Interval = '1m' | '5m' | '15m' | '1h' | '1d';

/** Bar sizes, with how much history each one is worth showing at. */
export const INTERVALS: { label: string; value: Interval; days: number }[] = [
  // Deliberately not the interval's own maximum: a chart that opens on 15 days
  // of one-minute bars is 6,000 candles wide and unreadable. These are what
  // each bar size is comfortable at, and the backend still clamps the rest.
  { label: '1m', value: '1m', days: 1 },
  { label: '5m', value: '5m', days: 3 },
  { label: '15m', value: '15m', days: 10 },
  { label: '1H', value: '1h', days: 30 },
  { label: '1D', value: '1d', days: 180 }
];

export function getHistory(
  instrument: string,
  interval: Interval,
  days: number,
  fetcher?: typeof fetch
): Promise<HistoryView> {
  return apiFetch<HistoryView>({
    url: '/market/history',
    params: { instrument, interval, days },
    fetcher
  });
}

/**
 * Epoch seconds, which is what the chart library's `UTCTimestamp` is.
 *
 * `Date.parse` handles the ISO string the API sends; dividing rather than
 * passing milliseconds matters because the library silently mis-scales a
 * millisecond value into the year 56,000 rather than rejecting it.
 */
export function toCandles(view: HistoryView | undefined): Candle[] {
  if (!view) return [];
  // Sorted defensively: the chart library and every indicator computed off
  // this array assume strictly ascending time, and a single out-of-order bar
  // — a mock-data session-boundary edge case has produced one in practice —
  // must not corrupt an indicator's math or crash the chart it's drawn on.
  return [...view.candles]
    .sort((a, b) => Date.parse(a.time) - Date.parse(b.time))
    .map((candle) => ({
      time: Math.floor(Date.parse(candle.time) / 1000),
      open: Number(candle.open),
      high: Number(candle.high),
      low: Number(candle.low),
      close: Number(candle.close)
    }));
}

/**
 * Volume bars, coloured by whether their candle closed up.
 *
 * Returns `undefined` when every bar is zero — which is what an index history
 * is, since an index has no turnover of its own. An empty pane taking a fifth
 * of the chart would imply data that is missing rather than absent.
 */
export function toVolume(view: HistoryView | undefined): VolumeBar[] | undefined {
  if (!view) return undefined;
  const bars = view.candles;
  if (!bars.some((candle) => Number(candle.volume) > 0)) return undefined;

  // Sorted for the same reason `toCandles` is — see its comment.
  return [...bars]
    .sort((a, b) => Date.parse(a.time) - Date.parse(b.time))
    .map((candle) => ({
      time: Math.floor(Date.parse(candle.time) / 1000),
      value: Number(candle.volume),
      rising: Number(candle.close) >= Number(candle.open)
    }));
}

/** Close, and how far it moved across the whole drawn range. */
export interface RangeSummary {
  last: number;
  change: number;
  changePct: number;
  high: number;
  low: number;
}

export function summarise(candles: Candle[]): RangeSummary | null {
  const first = candles[0];
  const last = candles[candles.length - 1];
  if (!first || !last) return null;

  // Measured from the range's *open*, not the previous close: the reader is
  // being shown this window, and a change against a bar off the left edge would
  // not be checkable against anything on screen.
  const change = last.close - first.open;
  return {
    last: last.close,
    change,
    changePct: first.open === 0 ? 0 : (change / first.open) * 100,
    high: Math.max(...candles.map((candle) => candle.high)),
    low: Math.min(...candles.map((candle) => candle.low))
  };
}

/** `24,601.20` — the grouping Indian index quotes are read in. */
export function fmtPrice(value: number): string {
  return new Intl.NumberFormat('en-IN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  }).format(value);
}
