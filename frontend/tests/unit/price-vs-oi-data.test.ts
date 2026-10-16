import { describe, expect, it } from 'vitest';
import { clampCursor, sliceTo } from '../../app/routes/terminal/future-lab/price-vs-oi-data';

/**
 * The Future Lab Price vs OI page's replay logic.
 *
 * Its picker helpers moved to the instrument catalog when the header search
 * came to need the same ranking — they are covered by
 * `instrument-search.test.ts` now.
 */

describe('replay cursor', () => {
  it('clamps to the last captured frame', () => {
    // Winding past the end would show a future the archive does not contain.
    expect(clampCursor(99, 10)).toBe(9);
  });

  it('clamps below zero', () => {
    expect(clampCursor(-5, 10)).toBe(0);
  });

  it('stays at zero for an empty session rather than going negative', () => {
    expect(clampCursor(3, 0)).toBe(0);
  });

  it('shows the whole series when not replaying', () => {
    const values = [1, 2, 3, 4];

    expect(sliceTo(values, null)).toEqual(values);
  });

  it('shows the session up to and including the cursor', () => {
    expect(sliceTo([1, 2, 3, 4], 1)).toEqual([1, 2]);
  });

  it('never slices past the end', () => {
    expect(sliceTo([1, 2, 3], 99)).toEqual([1, 2, 3]);
  });

  it('keeps the three series the same length at every position', () => {
    // The chart pairs them by index; a shorter OI array would silently shift
    // every open-interest reading onto the wrong timestamp.
    const t = ['a', 'b', 'c', 'd'];
    const price = [1, 2, 3, 4];
    const oi = [10, null, 30, 40];

    for (const cursor of [0, 1, 2, 3]) {
      expect(sliceTo(t, cursor)).toHaveLength(cursor + 1);
      expect(sliceTo(price, cursor)).toHaveLength(cursor + 1);
      expect(sliceTo(oi, cursor)).toHaveLength(cursor + 1);
    }
  });

  it('carries open-interest gaps through a slice rather than dropping them', () => {
    expect(sliceTo([10, null, 30], 2)).toEqual([10, null, 30]);
  });
});
