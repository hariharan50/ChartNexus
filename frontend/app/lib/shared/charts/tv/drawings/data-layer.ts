/**
 * Time to logical-index and back.
 *
 * The engine anchors drawings in time, and lightweight-charts positions things
 * by *logical index* — the position of a bar in the series, which is a float
 * between bars and keeps counting past the last one. That last part is the
 * reason this exists rather than `timeScale().timeToCoordinate()`: a position
 * target, a forecast and a fib time zone all live in the future, where there is
 * no bar to look up, and the library's own conversion returns null there.
 *
 * Extrapolation uses the median bar spacing rather than the mean so a weekend
 * gap or a trading halt in the middle of the series does not stretch every
 * projection past the last bar.
 */

import type { Candle } from '../LwChart';

export interface DataLayer {
  baseIndex: number;
  indexToTime(i: number): number;
  timeToIndexFloat(t: number): number;
}

export function makeDataLayer(candles: readonly Candle[]): DataLayer {
  const step = barSeconds(candles);
  const last = candles.length - 1;

  return {
    baseIndex: last,

    indexToTime(i: number): number {
      if (candles.length === 0) return 0;
      if (i <= 0) return candles[0]!.time + i * step;
      if (i >= last) return candles[last]!.time + (i - last) * step;
      const lo = Math.floor(i);
      const frac = i - lo;
      const a = candles[lo]!.time;
      const b = candles[Math.min(lo + 1, last)]!.time;
      return a + (b - a) * frac;
    },

    timeToIndexFloat(t: number): number {
      if (candles.length === 0) return 0;
      if (t <= candles[0]!.time) return (t - candles[0]!.time) / step;
      if (t >= candles[last]!.time) return last + (t - candles[last]!.time) / step;
      // Binary search for the bar at or before `t`, then interpolate across the
      // gap to the next one.
      let lo = 0;
      let hi = last;
      while (lo < hi) {
        const mid = (lo + hi + 1) >> 1;
        if (candles[mid]!.time <= t) lo = mid;
        else hi = mid - 1;
      }
      const a = candles[lo]!.time;
      const b = candles[Math.min(lo + 1, last)]!.time;
      return b === a ? lo : lo + (t - a) / (b - a);
    }
  };
}

/** The median gap between consecutive bars, in seconds. Falls back to a minute. */
export function barSeconds(candles: readonly Candle[]): number {
  if (candles.length < 2) return 60;
  const gaps: number[] = [];
  // A sample is enough, and keeps this O(1) on a long series that is re-derived
  // on every poll.
  const stride = Math.max(1, Math.floor(candles.length / 64));
  for (let i = stride; i < candles.length; i += stride) {
    const gap = candles[i]!.time - candles[i - stride]!.time;
    if (gap > 0) gaps.push(gap / stride);
  }
  if (gaps.length === 0) return 60;
  gaps.sort((a, b) => a - b);
  return gaps[Math.floor(gaps.length / 2)] ?? 60;
}
