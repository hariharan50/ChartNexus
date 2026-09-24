import { describe, expect, it } from 'vitest';
import type { Quote } from '../../app/lib/contexts/broker-connections/types';
import { FLAT_GAP_PERCENT, gapReading } from '../../app/lib/contexts/market-data/derive';

/**
 * The dashboard's gap card.
 *
 * The temptation this pins down is deriving the gap from `change`: that figure
 * is the *last price* against the previous close, so using it would make the
 * card restate the day's move and call it an opening gap. Only `day_open` and
 * `previous_close` answer the question, and when the broker omits either one
 * the reading has to be absent rather than approximated.
 */
function quote(dayOpen: string | null, previousClose: string | null): Quote {
  return {
    instrument: 'NIFTY',
    price: '24500',
    change: '10',
    change_percent: '0.04',
    day_open: dayOpen,
    previous_close: previousClose,
    provenance: {
      source: 'mock',
      fetched_at: '2026-09-24T03:45:00Z',
      age_seconds: 0,
      is_stale: true
    }
  };
}

describe('gapReading', () => {
  it('reads an open above the previous close as a gap up', () => {
    const reading = gapReading('NIFTY 50', quote('24600', '24500'));

    expect(reading?.signal).toBe('gap_up');
    expect(reading?.points).toBe(100);
    expect(reading?.percent).toBeCloseTo(0.408, 3);
    expect(reading?.label).toBe('NIFTY 50');
  });

  it('reads an open below the previous close as a gap down', () => {
    const reading = gapReading('NIFTY 50', quote('24380', '24500'));

    expect(reading?.signal).toBe('gap_down');
    expect(reading?.points).toBe(-120);
    expect(reading?.percent).toBeLessThan(0);
  });

  it('calls a move inside the dead-zone flat rather than directional', () => {
    // 24 points on 24,500 is 0.098% — real, but not a gap anyone trades.
    const reading = gapReading('NIFTY 50', quote('24524', '24500'));

    expect(Math.abs(reading?.percent ?? 0)).toBeLessThan(FLAT_GAP_PERCENT);
    expect(reading?.signal).toBe('flat');
  });

  it('treats the threshold itself as a gap, so the two states cannot both claim it', () => {
    const atThreshold = 24500 * (1 + FLAT_GAP_PERCENT / 100);
    const reading = gapReading('NIFTY 50', quote(String(atThreshold), '24500'));

    expect(reading?.signal).toBe('gap_up');
  });

  it('has no reading when the broker sent no opening print', () => {
    expect(gapReading('NIFTY 50', quote(null, '24500'))).toBeUndefined();
    expect(gapReading('NIFTY 50', quote('24600', null))).toBeUndefined();
  });

  it('has no reading before the spot query resolves', () => {
    expect(gapReading('NIFTY 50', undefined)).toBeUndefined();
  });

  it('refuses to divide by a zero previous close', () => {
    expect(gapReading('NIFTY 50', quote('24600', '0'))).toBeUndefined();
  });
});
