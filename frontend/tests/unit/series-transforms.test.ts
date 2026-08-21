import { describe, expect, it } from 'vitest';
import {
  boxSize,
  heikinAshi,
  lineBreak,
  preservesBars,
  rangeBars,
  renko,
  transformCandles
} from '../../app/lib/shared/charts/tv/series-transforms';
import type { Candle } from '../../app/lib/shared/charts/tv/LwChart';

/**
 * The derived chart types are the ones that can be subtly wrong without looking
 * wrong: a Renko brick in the right place for the wrong reason still draws a
 * plausible chart. These pin the arithmetic.
 */

const bar = (time: number, open: number, high: number, low: number, close: number): Candle => ({
  time,
  open,
  high,
  low,
  close
});

/** A flat series that closes at each given price, with a 1-wide range each bar. */
const closes = (values: number[]): Candle[] =>
  values.map((close, i) => bar(i * 60, close, close + 0.5, close - 0.5, close));

describe('heikinAshi', () => {
  it('averages the close over the whole bar', () => {
    const out = heikinAshi([bar(0, 10, 20, 5, 15)]);
    expect(out[0]!.close).toBe((10 + 20 + 5 + 15) / 4);
  });

  it('seeds the first open from its own body, then averages the previous HA bar', () => {
    const out = heikinAshi([bar(0, 10, 20, 5, 15), bar(60, 15, 25, 12, 20)]);
    expect(out[0]!.open).toBe(12.5); // (10 + 15) / 2
    expect(out[1]!.open).toBe((out[0]!.open + out[0]!.close) / 2);
  });

  it('widens high and low to contain the averaged body', () => {
    const out = heikinAshi([bar(0, 10, 11, 9, 10.5)]);
    const ha = out[0]!;
    expect(ha.high).toBeGreaterThanOrEqual(Math.max(ha.open, ha.close));
    expect(ha.low).toBeLessThanOrEqual(Math.min(ha.open, ha.close));
  });

  it('keeps one bar per input bar, at its original time', () => {
    const input = closes([100, 101, 102]);
    const out = heikinAshi(input);
    expect(out).toHaveLength(3);
    expect(out.map((b) => b.time)).toEqual([0, 60, 120]);
  });
});

describe('renko', () => {
  it('emits one brick per box of movement', () => {
    // 100 -> 130 with a box of 10 is three bricks, whatever route it took.
    const out = renko(closes([100, 110, 120, 130]), 10);
    expect(out).toHaveLength(3);
    expect(out.map((b) => b.close)).toEqual([110, 120, 130]);
  });

  it('draws nothing while price stays inside the box', () => {
    expect(renko(closes([100, 104, 97, 103, 100]), 10)).toHaveLength(0);
  });

  it('emits several bricks off a single bar that gaps', () => {
    const out = renko(closes([100, 140]), 10);
    expect(out).toHaveLength(4);
  });

  it('needs two boxes to reverse, and starts the reversal one box back', () => {
    // Up to 110, then down to 89: a one-box pullback draws nothing, and the
    // reversal brick spans 100 -> 90 rather than 110 -> 100.
    const out = renko(closes([100, 110, 105, 89]), 10);
    expect(out[0]!.close).toBe(110);
    const reversal = out[1]!;
    expect(reversal.open).toBe(100);
    expect(reversal.close).toBe(90);
  });

  it('gives every brick a strictly ascending time', () => {
    const out = renko(closes([100, 140]), 10);
    const times = out.map((b) => b.time);
    expect(times).toEqual([...times].sort((a, b) => a - b));
    expect(new Set(times).size).toBe(times.length);
  });

  it('returns nothing rather than looping forever on a zero box', () => {
    expect(renko(closes([100, 110]), 0)).toEqual([]);
  });
});

describe('rangeBars', () => {
  it('closes a bar once high minus low reaches the range', () => {
    const out = rangeBars([bar(0, 100, 100, 100, 100), bar(60, 100, 110, 100, 110)], 10);
    expect(out).toHaveLength(1);
    expect(out[0]!.high - out[0]!.low).toBeCloseTo(10);
  });

  it('holds a bar open while the range is unmet', () => {
    expect(rangeBars([bar(0, 100, 103, 99, 102)], 10)).toHaveLength(0);
  });

  it('splits one violent bar into several', () => {
    const out = rangeBars([bar(0, 100, 100, 100, 100), bar(60, 100, 135, 100, 135)], 10);
    expect(out.length).toBeGreaterThan(1);
    for (const b of out) expect(b.high - b.low).toBeCloseTo(10);
  });

  it('opens each bar where the last one closed', () => {
    const out = rangeBars([bar(0, 100, 100, 100, 100), bar(60, 100, 135, 100, 135)], 10);
    for (let i = 1; i < out.length; i += 1) expect(out[i]!.open).toBe(out[i - 1]!.close);
  });

  it('returns nothing rather than looping forever on a zero range', () => {
    expect(rangeBars(closes([100, 200]), 0)).toEqual([]);
  });
});

describe('lineBreak', () => {
  it('adds a line only when the close clears the last three', () => {
    // Rises to 103, then a pullback to 101 is inside the last three lines.
    const out = lineBreak(closes([100, 101, 102, 103, 101]));
    expect(out.map((b) => b.close)).toEqual([100, 101, 102, 103]);
  });

  it('reverses once the close breaks below all three', () => {
    const out = lineBreak(closes([100, 101, 102, 103, 99]));
    expect(out[out.length - 1]!.close).toBe(99);
    expect(out[out.length - 1]!.open).toBe(102);
  });

  it('draws each line from the previous line body, leaving no gap', () => {
    const out = lineBreak(closes([100, 101, 102, 103]));
    for (let i = 1; i < out.length; i += 1) {
      expect(out[i]!.open).toBe(out[i - 1]!.close);
    }
  });
});

describe('boxSize', () => {
  it('scales with the instrument, via average true range', () => {
    const small = boxSize(closes([100, 101, 102, 103]));
    const large = boxSize([bar(0, 100, 200, 100, 150), bar(60, 150, 260, 140, 200)]);
    expect(large).toBeGreaterThan(small);
  });

  it('falls back to a fraction of price on a flat series', () => {
    const flat = Array.from({ length: 5 }, (_, i) => bar(i * 60, 100, 100, 100, 100));
    expect(boxSize(flat)).toBeCloseTo(0.1);
  });

  it('gives up rather than returning a negative or absurd box', () => {
    expect(boxSize([])).toBe(0);
    expect(boxSize([bar(0, 0, 0, 0, 0)])).toBe(0);
  });
});

describe('transformCandles', () => {
  const input = closes([100, 101, 102]);

  it('passes the untransformed types straight through, by identity', () => {
    for (const type of ['candle', 'bar', 'hollow', 'line', 'area', 'baseline'] as const) {
      expect(transformCandles(type, input)).toBe(input);
    }
  });

  it('derives the transformed ones', () => {
    expect(transformCandles('heikin', input)).not.toBe(input);
  });

  it('survives an empty series', () => {
    for (const type of ['heikin', 'renko', 'range', 'linebreak'] as const) {
      expect(transformCandles(type, [])).toEqual([]);
    }
  });
});

describe('preservesBars', () => {
  it('is false exactly for the types that emit a bar per price move', () => {
    expect(preservesBars('renko')).toBe(false);
    expect(preservesBars('range')).toBe(false);
    expect(preservesBars('linebreak')).toBe(false);
    // Heikin Ashi is one-for-one, so its volume pane still lines up.
    expect(preservesBars('heikin')).toBe(true);
    expect(preservesBars('candle')).toBe(true);
  });
});
