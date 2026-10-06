/**
 * Wire types and pure derivations for the Analyse price chart.
 *
 * The backend ships candles already aggregated at the requested interval, so
 * there is nothing to resample here. What this module does own is the shape
 * change between the API and the chart library — ISO timestamps to epoch
 * seconds, decimal strings to numbers — which is the only place those two
 * vocabularies are allowed to meet.
 */

import type { DataSourceName } from '$contexts/broker-connections/types';
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
  source: DataSourceName;
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

/**
 * Bar sizes, with how much history each one opens on.
 *
 * Every intraday size reaches back **30 sessions**, so a reader scrolling left
 * finds the same month of context whichever one they are on — switching 5m to
 * 15m re-scales the bars rather than changing the period under them.
 *
 * Two deliberate exceptions. **1m stays at one session**: its ceiling is 15
 * days (`CandleInterval.max_days` on the backend, which is where the broker's
 * per-resolution limit is enforced), and even that is ~5,600 candles — a wall
 * of ticks nobody reads. **1D stays at 180**, because it already far exceeds a
 * month and cutting it to 30 bars would be a pure loss.
 */
export const INTERVALS: { label: string; value: Interval; days: number }[] = [
  { label: '1m', value: '1m', days: 1 },
  { label: '5m', value: '5m', days: 30 },
  { label: '15m', value: '15m', days: 30 },
  { label: '1H', value: '1h', days: 30 },
  { label: '1D', value: '1d', days: 180 }
];

/**
 * Price bars for the chart — real ones or none.
 *
 * `live_only` is not optional here and is the point of this function. Every
 * other surface in the app labels simulated data and draws it anyway, which is
 * right for a dashboard tile read at a glance. A price chart is different: a
 * synthetic candle is indistinguishable from a traded one once drawn, and the
 * things people do with this page — measure a range, mark a level, draw a
 * trendline and keep it — all outlive the badge that would have warned them.
 *
 * With no real data the backend answers an empty series stamped
 * `unavailable`, which {@link hasNoRealData} detects.
 */
export function getHistory(
  instrument: string,
  interval: Interval,
  days: number,
  fetcher?: typeof fetch
): Promise<HistoryView> {
  return apiFetch<HistoryView>({
    url: '/market/history',
    params: { instrument, interval, days, live_only: true },
    fetcher
  });
}

/** The backend had nothing real for this instrument and range. */
export function hasNoRealData(view: HistoryView | undefined): boolean {
  return view !== undefined && view.provenance.source === 'unavailable';
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
