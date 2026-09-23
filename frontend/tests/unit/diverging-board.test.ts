import { describe, expect, it } from 'vitest';
import {
  pairRows,
  sharedScale,
  type BoardRow
} from '../../app/routes/terminal/future-lab/analysis/components/DivergingBoard';

/**
 * The two pieces of arithmetic behind the diverging board.
 *
 * Both fail silently on screen rather than throwing: a dropped tail row just
 * looks like a shorter list, and a per-side scale looks like a perfectly
 * ordinary chart that happens to be lying about which side moved more.
 */

function row(symbol: string, value: number): BoardRow {
  return { symbol, value, hover: symbol };
}

describe('pairRows', () => {
  it('pairs the n-th riser with the n-th faller', () => {
    const rows = pairRows([row('A', 10), row('B', 5)], [row('X', -8), row('Y', -2)]);

    expect(rows).toHaveLength(2);
    expect(rows[0]!.up?.symbol).toBe('A');
    expect(rows[0]!.down?.symbol).toBe('X');
    expect(rows[1]!.up?.symbol).toBe('B');
    expect(rows[1]!.down?.symbol).toBe('Y');
  });

  it('keeps every name when one side is longer', () => {
    /* A market almost never has as many names down as up. Truncating to the
       shorter side would drop real movers from a board that claims to show
       all of them. */
    const rows = pairRows([row('A', 10), row('B', 5), row('C', 1)], [row('X', -8)]);

    expect(rows).toHaveLength(3);
    expect(rows[2]!.up?.symbol).toBe('C');
    expect(rows[2]!.down).toBeNull();
  });

  it('handles a longer falling side just as well', () => {
    const rows = pairRows([row('A', 10)], [row('X', -8), row('Y', -3)]);

    expect(rows).toHaveLength(2);
    expect(rows[1]!.up).toBeNull();
    expect(rows[1]!.down?.symbol).toBe('Y');
  });

  it('is empty when nothing could be priced', () => {
    expect(pairRows([], [])).toEqual([]);
  });

  it('preserves the order the server ranked them in', () => {
    const rows = pairRows([row('A', 10), row('B', 5)], []);
    expect(rows.map((entry) => entry.up?.symbol)).toEqual(['A', 'B']);
  });
});

describe('sharedScale', () => {
  it('is the largest absolute value across both sides', () => {
    expect(sharedScale([row('A', 10)], [row('X', -8)])).toBe(10);
  });

  it('lets the falling side set it when the falls are bigger', () => {
    /* The point of one scale: on a day the scope fell, the red bars have to be
       the long ones. */
    expect(sharedScale([row('A', 4)], [row('X', -12)])).toBe(12);
  });

  it('never returns zero, so a flat board still divides', () => {
    expect(sharedScale([], [])).toBeGreaterThan(0);
  });
});
