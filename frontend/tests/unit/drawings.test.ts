import { describe, expect, it } from 'vitest';
import { fibLevelPrices } from '../../app/lib/shared/charts/tv/drawings/fib-levels';
import { barsBetween, candleAt, snapToCandle } from '../../app/lib/shared/charts/tv/drawings/snap';
import type { Candle } from '../../app/lib/shared/charts/tv/LwChart';

describe('fibLevelPrices', () => {
  it('puts the more recent point at 0% and the older one at 100%', () => {
    const levels = fibLevelPrices(100, 200);
    expect(levels.find((l) => l.level === 0)?.price).toBe(200);
    expect(levels.find((l) => l.level === 1)?.price).toBe(100);
  });

  it('places 50% exactly halfway between the anchors', () => {
    const levels = fibLevelPrices(100, 200);
    expect(levels.find((l) => l.level === 0.5)?.price).toBe(150);
  });

  it('works the same regardless of which anchor is higher', () => {
    const up = fibLevelPrices(100, 200);
    const down = fibLevelPrices(200, 100);
    expect(up.find((l) => l.level === 0.618)?.price).toBeCloseTo(200 - (200 - 100) * 0.618);
    expect(down.find((l) => l.level === 0.618)?.price).toBeCloseTo(100 - (100 - 200) * 0.618);
  });
});

const candle = (time: number, o: number, h: number, l: number, c: number): Candle => ({
  time,
  open: o,
  high: h,
  low: l,
  close: c
});

describe('snapToCandle', () => {
  it('snaps to whichever of O/H/L/C is nearest', () => {
    const bar = candle(0, 100, 110, 90, 105);
    expect(snapToCandle(107, bar)).toBe(105); // closest to close
    expect(snapToCandle(112, bar)).toBe(110); // closest to high
    expect(snapToCandle(89, bar)).toBe(90); // closest to low
    expect(snapToCandle(99, bar)).toBe(100); // closest to open
  });

  it('passes the raw price through when there is no candle to snap to', () => {
    expect(snapToCandle(123.45, undefined)).toBe(123.45);
  });
});

describe('candleAt', () => {
  const candles = [candle(100, 1, 2, 0, 1), candle(200, 2, 3, 1, 2), candle(300, 3, 4, 2, 3)];

  it('returns the candle whose time is nearest the given time', () => {
    expect(candleAt(candles, 210)).toBe(candles[1]);
    expect(candleAt(candles, 260)).toBe(candles[2]);
  });

  it('returns undefined for an empty series', () => {
    expect(candleAt([], 100)).toBeUndefined();
  });

  it('clamps to the ends rather than running off them', () => {
    expect(candleAt(candles, 0)).toBe(candles[0]);
    expect(candleAt(candles, 9_999)).toBe(candles[2]);
  });

  it('returns the exact bar when the time lands on one', () => {
    expect(candleAt(candles, 200)).toBe(candles[1]);
  });
});

describe('barsBetween', () => {
  const candles = [candle(100, 1, 2, 0, 1), candle(200, 2, 3, 1, 2), candle(300, 3, 4, 2, 3)];

  it('counts both endpoints of an inclusive range', () => {
    expect(barsBetween(candles, 100, 300)).toBe(3);
    expect(barsBetween(candles, 100, 200)).toBe(2);
    expect(barsBetween(candles, 200, 200)).toBe(1);
  });

  it('counts only the bars actually inside a range that straddles gaps', () => {
    expect(barsBetween(candles, 150, 250)).toBe(1);
    expect(barsBetween(candles, 301, 400)).toBe(0);
  });

  it('returns zero for an empty series', () => {
    expect(barsBetween([], 0, 100)).toBe(0);
  });
});
