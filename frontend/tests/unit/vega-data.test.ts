import { describe, expect, it } from 'vitest';
import {
  bucketIndices,
  csvFilename,
  expiryLabel,
  fmtVega,
  frameTotals,
  pick,
  vegaCsv,
  type VegaFrame,
  type VegaRow,
  type VegaView
} from '../../app/routes/terminal/options/vega-analysis/vega-data';

/**
 * Vega Analysis applies both its strike window and its timeframe on the client,
 * so this arithmetic is everything between the payload and what the chart, the
 * table and the CSV export all show.
 */

const STRIKES = [24_500, 24_550, 24_600, 24_650, 24_700];

function frame(overrides: Partial<VegaFrame> = {}): VegaFrame {
  return {
    t: '2026-08-14T04:00:00+00:00',
    spot: 24_636,
    atm: 24_650,
    synth_future: 24_640,
    call_vega: [1, 2, 3, 4, 5],
    put_vega: [5, 4, 3, 2, 1],
    ...overrides
  };
}

describe('frameTotals', () => {
  it('sums each side only over the strikes in the window', () => {
    const totals = frameTotals(STRIKES, frame(), new Set([24_550, 24_650]));

    // call at 24_550 (2) + 24_650 (4); put at 24_550 (4) + 24_650 (2).
    expect(totals.call).toBe(6);
    expect(totals.put).toBe(6);
  });

  it('ignores strikes outside the window', () => {
    const totals = frameTotals(STRIKES, frame(), new Set([24_500]));

    expect(totals.call).toBe(1);
    expect(totals.put).toBe(5);
  });

  it('treats a missing per-strike value as zero, not NaN', () => {
    const totals = frameTotals(STRIKES, frame({ call_vega: [1, 2] }), new Set(STRIKES));

    expect(Number.isNaN(totals.call)).toBe(false);
    expect(totals.call).toBe(3);
  });
});

describe('bucketIndices', () => {
  const times = [
    '2026-08-14T04:00:00Z',
    '2026-08-14T04:01:00Z',
    '2026-08-14T04:02:00Z',
    '2026-08-14T04:03:00Z',
    '2026-08-14T04:04:00Z'
  ];

  it('keeps every point at 1m', () => {
    expect(bucketIndices(times, '1m')).toEqual([0, 1, 2, 3, 4]);
  });

  it('keeps the last point of each bucket, and always the open', () => {
    // 3-minute buckets: [0,1,2] -> 2, [3,4] -> 4; the open (0) is prepended.
    expect(bucketIndices(times, '3m')).toEqual([0, 2, 4]);
  });

  it('is empty for no captures', () => {
    expect(bucketIndices([], '5m')).toEqual([]);
  });
});

describe('pick', () => {
  it('selects the aligned values for the kept indices', () => {
    expect(pick([10, 20, 30, 40], [0, 2])).toEqual([10, 30]);
  });
});

describe('fmtVega', () => {
  it('prefixes a + on a positive delta', () => {
    expect(fmtVega(1.239)).toBe('+1.24');
  });

  it('keeps the minus on a negative delta and never a leading +', () => {
    expect(fmtVega(-9.69)).toBe('-9.69');
    expect(fmtVega(0)).toBe('0.00');
  });
});

describe('expiryLabel', () => {
  it('falls back when no expiry is known', () => {
    expect(expiryLabel(null)).toBe('Nearest expiry');
  });
});

describe('vegaCsv / csvFilename', () => {
  const rows: VegaRow[] = [
    { t: '2026-08-14T04:00:00Z', synth: 24_640, call: 0, put: 0, diff: 0 },
    { t: '2026-08-14T04:03:00Z', synth: null, call: -9.69, put: 1.24, diff: 10.93 }
  ];

  it('writes a header and one line per row, blanking a null synth', () => {
    const lines = vegaCsv(rows).split('\n');

    expect(lines[0]).toContain('put_minus_call');
    expect(lines).toHaveLength(3);
    expect(lines[2]).toBe('2026-08-14T04:03:00Z,,-9.69,1.24,10.93');
  });

  it('names the file after the day of the session', () => {
    const view = { now_ts: '2026-08-14T09:59:00Z' } as VegaView;

    expect(csvFilename('NIFTY', view)).toBe('vega-NIFTY-2026-08-14.csv');
  });
});
