import { describe, expect, it } from 'vitest';
import type { Candle, VolumeBar } from '../../app/lib/shared/charts/tv/LwChart';
import {
  bollinger,
  buildOverlays,
  ema,
  rsi,
  sma,
  vwap,
  type IndicatorId
} from '../../app/routes/terminal/analyse/indicators';

/** A close series on a 1-minute grid, opens equal to closes for simple maths. */
function series(closes: number[]): Candle[] {
  return closes.map((close, i) => ({
    time: 1_700_000_000 + i * 60,
    open: close,
    high: close + 1,
    low: close - 1,
    close
  }));
}

describe('sma', () => {
  it('starts at the period-th bar and averages the window', () => {
    const out = sma(series([1, 2, 3, 4, 5]), 3);
    expect(out).toHaveLength(3);
    expect(out[0]!.value).toBe(2); // (1+2+3)/3
    expect(out[2]!.value).toBe(4); // (3+4+5)/3
  });

  it('returns nothing when there is not enough history', () => {
    expect(sma(series([1, 2]), 5)).toEqual([]);
  });
});

describe('ema', () => {
  it('seeds on the first SMA and then decays toward recent closes', () => {
    const out = ema(series([1, 2, 3, 4, 5]), 3);
    expect(out[0]!.value).toBe(2); // seed = SMA(3) of the first three
    // 4·0.5+2·0.5 = 3, then 5·0.5+3·0.5 = 4 — above the seed, tracking upward.
    expect(out.at(-1)!.value).toBeCloseTo(4, 5);
    expect(out.at(-1)!.value).toBeGreaterThan(out[0]!.value);
  });
});

describe('bollinger', () => {
  it('brackets the mean by ±mult·sd, all three aligned', () => {
    const b = bollinger(series([1, 2, 3, 4, 5, 6]), 3, 2);
    expect(b.mid).toHaveLength(4);
    for (let i = 0; i < b.mid.length; i++) {
      expect(b.upper[i]!.value).toBeGreaterThan(b.mid[i]!.value);
      expect(b.lower[i]!.value).toBeLessThan(b.mid[i]!.value);
    }
  });
});

describe('rsi', () => {
  it('is 100 on an unbroken advance', () => {
    const closes = Array.from({ length: 16 }, (_, i) => i + 1);
    expect(rsi(series(closes), 14).at(-1)!.value).toBe(100);
  });

  it('stays within 0..100', () => {
    const out = rsi(series([5, 4, 6, 3, 7, 2, 8, 1, 9, 4, 6, 3, 7, 2, 8, 5]), 14);
    for (const point of out) {
      expect(point.value).toBeGreaterThanOrEqual(0);
      expect(point.value).toBeLessThanOrEqual(100);
    }
  });
});

describe('vwap', () => {
  it('is empty without volume (an index has none)', () => {
    expect(vwap(series([1, 2, 3]), undefined)).toEqual([]);
  });

  it('opens at the first bar’s typical price', () => {
    const candles = series([10, 20]);
    const volume: VolumeBar[] = candles.map((c) => ({ time: c.time, value: 100, rising: true }));
    const out = vwap(candles, volume);
    expect(out).toHaveLength(2);
    expect(out[0]!.value).toBeCloseTo(10, 5); // (11+9+10)/3
  });
});

describe('buildOverlays', () => {
  it('emits one spec per simple indicator and three for Bollinger', () => {
    const candles = series(Array.from({ length: 60 }, (_, i) => 100 + i));
    const overlays = buildOverlays(
      new Set<IndicatorId>(['sma20', 'boll', 'rsi']),
      candles,
      undefined
    );
    const ids = overlays.map((o) => o.id);
    expect(ids).toContain('sma20');
    expect(ids).toEqual(expect.arrayContaining(['boll-u', 'boll-m', 'boll-l']));
    // No volume → RSI drops to pane 1 rather than leaving a blank pane above it.
    expect(overlays.find((o) => o.id === 'rsi')!.paneIndex).toBe(1);
  });

  it('omits VWAP when there is no volume', () => {
    const overlays = buildOverlays(new Set<IndicatorId>(['vwap']), series([1, 2, 3]), undefined);
    expect(overlays.find((o) => o.id === 'vwap')).toBeUndefined();
  });
});
