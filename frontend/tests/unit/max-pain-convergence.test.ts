import { describe, expect, it } from 'vitest';
import {
  convergence,
  type MaxPainSeriesView
} from '../../app/routes/terminal/options/max-pain/max-pain-data';

/**
 * The reading under the Intraday Max Pain chart.
 *
 * The cases that matter are the absences. A series with nothing priced, or a
 * session with only one point, must produce *no* reading — a card saying
 * "0 points, holding" looks like a finding rather than a lack of data, and on
 * a page about where the pin is drifting that is the worst thing it could say.
 */
function view(overrides: Partial<MaxPainSeriesView> = {}): MaxPainSeriesView {
  return {
    instrument_id: 'NIFTY',
    symbol: 'NIFTY',
    expiry_date: '2026-09-29',
    lot_size: 75,
    spot: 23_223,
    open_ts: '2026-09-24T03:45:00Z',
    now_ts: '2026-09-24T05:20:00Z',
    data_quality: 'intraday',
    open_is_estimated: false,
    t: ['2026-09-24T03:45:00Z', '2026-09-24T04:30:00Z', '2026-09-24T05:20:00Z'],
    fut: [23_500, 23_300, 23_223],
    max_pain: [23_500, 23_400, 23_350],
    ...overrides
  };
}

describe('convergence', () => {
  it('measures the distance from the future to the pin', () => {
    const reading = convergence(view());

    expect(reading?.maxPain).toBe(23_350);
    expect(reading?.price).toBe(23_223);
    expect(reading?.distance).toBe(-127);
    expect(reading?.distancePct).toBeCloseTo(-0.544, 3);
  });

  it('reports how far the pin has travelled and which way', () => {
    const reading = convergence(view());

    expect(reading?.openMaxPain).toBe(23_500);
    expect(reading?.shift).toBe(-150);
    expect(reading?.drift).toBe('down');
  });

  it('calls a pin that has not moved unchanged rather than drifting', () => {
    const reading = convergence(view({ max_pain: [23_400, 23_400, 23_400] }));

    expect(reading?.shift).toBe(0);
    expect(reading?.drift).toBe('unchanged');
  });

  it('reads a narrowing gap as converging', () => {
    // Opens 500 apart, ends 50 apart.
    const reading = convergence(
      view({ fut: [23_000, 23_200, 23_300], max_pain: [23_500, 23_400, 23_350] })
    );

    expect(reading?.approach).toBe('converging');
  });

  it('reads a widening gap as diverging', () => {
    const reading = convergence(
      view({ fut: [23_450, 23_200, 22_900], max_pain: [23_500, 23_500, 23_500] })
    );

    expect(reading?.approach).toBe('diverging');
  });

  it('holds steady inside the dead zone rather than flipping on noise', () => {
    // A handful of points either way is not a change of regime.
    const reading = convergence(
      view({ fut: [23_400, 23_395, 23_398], max_pain: [23_500, 23_500, 23_500] })
    );

    expect(reading?.approach).toBe('steady');
  });

  it('skips leading nulls rather than reading the open as unpriced', () => {
    // The reconstructed 09:15 frame records no future.
    const reading = convergence(view({ fut: [null, 23_300, 23_223] }));

    expect(reading?.price).toBe(23_223);
    expect(reading).toBeDefined();
  });

  it('falls back to spot when no future was recorded at all', () => {
    const reading = convergence(view({ fut: [null, null, null] }));

    expect(reading?.price).toBe(23_223);
  });

  it('has no reading when nothing could be priced', () => {
    expect(convergence(view({ max_pain: [null, null, null] }))).toBeUndefined();
  });

  it('has no reading on an empty payload', () => {
    expect(
      convergence(view({ t: [], fut: [], max_pain: [], data_quality: 'empty' }))
    ).toBeUndefined();
  });

  it('has no reading before the query resolves', () => {
    expect(convergence(undefined)).toBeUndefined();
  });
});
