import { describe, expect, it } from 'vitest';
import {
  bucketIndices,
  fmtOi,
  fmtRatio,
  pick,
  TIMEFRAMES
} from '../../app/routes/terminal/options/pcr/pcr-data';

/**
 * Client-side resampling for the Put-Call Ratio tool.
 *
 * The endpoint sends the raw capture cadence and the timeframe is applied here,
 * so this arithmetic is the only thing between the archive and what the three
 * charts draw.
 */

/** A session at one-minute captures, as ISO strings. */
function minutes(count: number): string[] {
  const start = Date.parse('2026-08-04T03:45:00Z'); // 09:15 IST
  return Array.from({ length: count }, (_, i) => new Date(start + i * 60_000).toISOString());
}

describe('bucketIndices', () => {
  it('keeps every point at the native cadence', () => {
    expect(bucketIndices(minutes(5), '1m')).toEqual([0, 1, 2, 3, 4]);
  });

  it('keeps the last point of each bucket, not the first', () => {
    // PCR and open interest are stocks, not flows. The last reading in a bucket
    // is the one the market actually showed at the end of it; a mean would be a
    // number nobody saw, and the final bucket would lag the live figure.
    //
    // Index 0 rides along because the open is always kept — see the next test.
    expect(bucketIndices(minutes(10), '5m')).toEqual([0, 4, 9]);
  });

  it('always keeps the session open, whatever bucket it lands in', () => {
    // Every change on the page is measured from the open; losing it to a
    // bucket boundary would silently move the baseline.
    const kept = bucketIndices(minutes(12), '5m');
    expect(kept[0]).toBe(0);
    expect(kept).toEqual([0, 4, 9, 11]);
  });

  it('collapses a whole session into one bucket at an hour', () => {
    expect(bucketIndices(minutes(45), '1h')).toEqual([0, 44]);
  });

  it('handles a session shorter than one bucket', () => {
    expect(bucketIndices(minutes(3), '15m')).toEqual([0, 2]);
  });

  it('returns nothing for an empty session', () => {
    expect(bucketIndices([], '5m')).toEqual([]);
  });
});

describe('pick', () => {
  it('applies a bucketing to any aligned array', () => {
    expect(pick([10, 20, 30, 40, 50], [0, 2, 4])).toEqual([10, 30, 50]);
  });

  it('carries nulls through rather than dropping them', () => {
    // An undefined ratio has to survive resampling. Losing it would silently
    // join the line across a gap the market genuinely had.
    expect(pick([1, null, 3], [0, 1, 2])).toEqual([1, null, 3]);
  });

  it('keeps a null that lands on a bucket boundary', () => {
    const values = [0.9, 0.91, null, 0.93, 0.94];
    expect(pick(values, bucketIndices(minutes(5), '1m'))).toEqual(values);
  });
});

describe('fmtRatio', () => {
  it('shows two decimals, because the third never changes a decision', () => {
    expect(fmtRatio(0.9534)).toBe('0.95');
    expect(fmtRatio(1)).toBe('1.00');
    expect(fmtRatio(1.207)).toBe('1.21');
  });
});

describe('fmtOi', () => {
  it('uses Indian units', () => {
    expect(fmtOi(13_770_000)).toBe('1.38Cr');
    expect(fmtOi(4_897_000)).toBe('48.97L');
    expect(fmtOi(5_200)).toBe('5.20K');
  });

  it('keeps the sign on a decrease', () => {
    expect(fmtOi(-1_780_000)).toBe('-17.80L');
  });
});

describe('timeframes', () => {
  it('offers 1D but never lets it be chosen', () => {
    // It needs one reading per session across days, and the archive holds two.
    const day = TIMEFRAMES.find((option) => option.value === '1D');
    expect(day?.disabled).toBe(true);
    expect(TIMEFRAMES.filter((option) => !option.disabled).map((o) => o.value)).toEqual([
      '1m',
      '5m',
      '15m',
      '1h'
    ]);
  });
});
