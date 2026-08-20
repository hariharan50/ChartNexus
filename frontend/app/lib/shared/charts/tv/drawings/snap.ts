import type { Candle } from '../LwChart';

/**
 * The magnet: pulls a raw price to whichever of that bar's O/H/L/C it is
 * closest to.
 *
 * Only the price is snapped — the time already comes off the chart's own
 * crosshair, which is already pinned to a bar, so there is no "nearest time"
 * decision left to make here.
 */
export function snapToCandle(price: number, candle: Candle | undefined): number {
  if (!candle) return price;
  const candidates = [candle.open, candle.high, candle.low, candle.close];
  return candidates.reduce((closest, value) =>
    Math.abs(value - price) < Math.abs(closest - price) ? value : closest
  );
}

/**
 * The candle whose bar a given time falls in — nearest by `time`, not exact match.
 *
 * Binary search, not a scan: with the magnet on this is called on every
 * crosshair move, i.e. once per pointer frame, against a series that can run to
 * thousands of bars. `candles` is ascending by construction — `toCandles` sorts
 * it and `LwChart` refuses to draw anything else.
 */
export function candleAt(candles: Candle[], time: number): Candle | undefined {
  if (candles.length === 0) return undefined;

  let lo = 0;
  let hi = candles.length - 1;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (candles[mid]!.time < time) lo = mid + 1;
    else hi = mid;
  }

  // `lo` is the first bar at or after `time`; its predecessor can still be the
  // closer of the two.
  const after = candles[lo]!;
  const before = candles[lo - 1];
  if (!before) return after;
  return Math.abs(after.time - time) < Math.abs(before.time - time) ? after : before;
}

/** How many bars fall within `[from, to]` — the measure tool's bar count, in log time. */
export function barsBetween(candles: Candle[], from: number, to: number): number {
  if (candles.length === 0) return 0;
  return lowerBound(candles, to + 1) - lowerBound(candles, from);
}

/** Index of the first candle whose time is >= `time`, or `candles.length`. */
function lowerBound(candles: Candle[], time: number): number {
  let lo = 0;
  let hi = candles.length;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (candles[mid]!.time < time) lo = mid + 1;
    else hi = mid;
  }
  return lo;
}
