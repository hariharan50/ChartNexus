import { describe, expect, it } from 'vitest';
import type { Quote, SessionGap } from '../../app/lib/contexts/broker-connections/types';
import { gapReading } from '../../app/lib/contexts/market-data/derive';

/**
 * The dashboard's gap card.
 *
 * This used to compute `day_open - previous_close` itself, and that was the
 * bug: those two fields carry whatever the latest fifteen-second poll returned,
 * so a poll that degraded to the mock provider brought a different open *and* a
 * different previous close, and the card flipped between a gap up of ~125 and a
 * gap down of ~120 as the broker's circuit breaker opened and reset.
 *
 * The opening print is a fact of the session, so the backend now decides it
 * once and latches it. What these tests pin is that the client reads that
 * verdict and does not second-guess it — including when the live fields sitting
 * beside it disagree, which is exactly the degraded case.
 */
function gap(overrides: Partial<SessionGap> = {}): SessionGap {
  return {
    opened_at: '24600',
    reference_close: '24500',
    points: '100.00',
    percent: '0.41',
    signal: 'gap_up',
    source: 'live',
    observed_at: '2026-09-28T03:45:30Z',
    settled: true,
    ...overrides
  };
}

function quote(
  sessionGap: SessionGap | null,
  fields: Partial<Pick<Quote, 'day_open' | 'previous_close'>> = {}
): Quote {
  return {
    instrument: 'NIFTY',
    price: '24510',
    change: '10',
    change_percent: '0.04',
    day_open: '24600',
    previous_close: '24500',
    gap: sessionGap,
    provenance: {
      source: 'live',
      fetched_at: '2026-09-28T04:45:00Z',
      age_seconds: 0,
      is_stale: false
    },
    ...fields
  };
}

describe('gapReading', () => {
  it('reads the latched verdict, points and percent straight off the wire', () => {
    const reading = gapReading('NIFTY 50', quote(gap()));

    expect(reading?.label).toBe('NIFTY 50');
    expect(reading?.signal).toBe('gap_up');
    expect(reading?.open).toBe(24600);
    expect(reading?.previousClose).toBe(24500);
    expect(reading?.points).toBe(100);
    expect(reading?.percent).toBeCloseTo(0.41, 2);
  });

  it('keeps the latched gap when the poll it arrived on has degraded', () => {
    // The regression. The broker tripped, so `day_open` and `previous_close`
    // are now the mock's seeded pair — 141 points the other way. The gap must
    // not move: it was observed live and the session opened only once.
    const reading = gapReading(
      'NIFTY 50',
      quote(gap(), { day_open: '23976.50', previous_close: '24117.24' })
    );

    expect(reading?.signal).toBe('gap_up');
    expect(reading?.points).toBe(100);
    expect(reading?.open).toBe(24600);
  });

  it('carries the provenance of the pair, not of the quote around it', () => {
    const reading = gapReading('NIFTY 50', quote(gap({ source: 'mock' })));

    expect(reading?.source).toBe('mock');
  });

  it('reports a gap down as the backend classified it', () => {
    const reading = gapReading(
      'NIFTY 50',
      quote(gap({ opened_at: '24380', points: '-120.00', percent: '-0.49', signal: 'gap_down' }))
    );

    expect(reading?.signal).toBe('gap_down');
    expect(reading?.points).toBe(-120);
  });

  it('does not re-derive a flat reading into a directional one', () => {
    // 24 points on 24,500 is 0.098% — inside the dead zone. The client must
    // take `flat` at its word rather than applying a threshold of its own.
    const reading = gapReading(
      'NIFTY 50',
      quote(gap({ opened_at: '24524', points: '24.00', percent: '0.10', signal: 'flat' }))
    );

    expect(reading?.signal).toBe('flat');
  });

  it('marks a reading taken before the opening auction as unsettled', () => {
    const reading = gapReading('NIFTY 50', quote(gap({ settled: false })));

    expect(reading?.settled).toBe(false);
  });

  it('has no reading when the session has no believable pair yet', () => {
    // Not a zero gap: a zero renders as "the market opened flat", which is a
    // claim nobody can make before the open.
    expect(gapReading('NIFTY 50', quote(null))).toBeUndefined();
  });

  it('has no reading before the spot query resolves', () => {
    expect(gapReading('NIFTY 50', undefined)).toBeUndefined();
  });

  it('refuses a pair it cannot parse', () => {
    expect(gapReading('NIFTY 50', quote(gap({ opened_at: 'n/a' })))).toBeUndefined();
  });
});
