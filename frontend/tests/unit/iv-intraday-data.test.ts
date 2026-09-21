import { describe, expect, it } from 'vitest';
import {
  atmIv,
  csvFilename,
  defaultExpiries,
  fmtIv,
  futureSeries,
  intradayCsv,
  isFlatCurve,
  ivSeries,
  MAX_EXPIRIES,
  shortExpiry,
  termCsv,
  toggleExpiry,
  type TermPoint
} from '../../app/routes/terminal/options/iv-intraday/iv-intraday-data';
import type {
  SkewFrame,
  SkewView
} from '../../app/routes/terminal/options/volatility-skew/volatility-skew-data';

/**
 * Two views over two sources, and the tests split the same way: the intraday
 * half is about reading the money off a frame without quietly substituting a
 * neighbouring strike, and the term-structure half is about the expiry
 * selection and about noticing a curve that is flat because nothing varied it.
 */

const STRIKES = [24_500, 24_550, 24_600, 24_650, 24_700];

function frame(overrides: Partial<SkewFrame> = {}): SkewFrame {
  return {
    t: '2026-09-03T04:00:00Z',
    spot: 24_610,
    atm: 24_600,
    future: 24_640,
    ce_iv: [18, 14, 11, 13, 17],
    pe_iv: [20, 16, 13, 14, 19],
    call_oi: [100, 200, 300, 400, 500],
    put_oi: [500, 400, 300, 200, 100],
    ...overrides
  };
}

function view(frames: SkewFrame[]): SkewView {
  return {
    instrument_id: 'NIFTY',
    symbol: 'NIFTY',
    expiry_date: '2026-09-08',
    lot_size: 75,
    spot: 24_610,
    atm_strike: 24_600,
    open_ts: frames[0]?.t ?? '',
    now_ts: frames.at(-1)?.t ?? '',
    data_quality: 'intraday',
    open_is_estimated: false,
    iv_coverage: 1,
    strikes: STRIKES,
    t: frames.map((f) => f.t),
    frames
  };
}

describe('atmIv', () => {
  it('averages the call and the put at the money', () => {
    expect(atmIv(frame(), STRIKES)).toBe(12);
  });

  it('falls back to whichever side was quoted', () => {
    expect(atmIv(frame({ ce_iv: [18, 14, null, 13, 17] }), STRIKES)).toBe(13);
    expect(atmIv(frame({ pe_iv: [20, 16, null, 14, 19] }), STRIKES)).toBe(11);
  });

  it('is null when neither side was quoted at the money', () => {
    const blind = frame({ ce_iv: [18, 14, null, 13, 17], pe_iv: [20, 16, null, 14, 19] });
    expect(atmIv(blind, STRIKES)).toBeNull();
  });

  it('never substitutes a neighbouring strike for a missing one', () => {
    // The strike beside the money is a different contract; quietly using it
    // would draw a curve of numbers that were never the ATM volatility.
    const blind = frame({ ce_iv: [18, 14, null, 13, 17], pe_iv: [20, 16, null, 14, 19] });
    expect(atmIv(blind, STRIKES)).not.toBe(14);
    expect(atmIv(blind, STRIKES)).not.toBe(13);
  });

  it('is null on a capture with no recorded ATM', () => {
    expect(atmIv(frame({ atm: null }), STRIKES)).toBeNull();
  });

  it('is null when the ATM strike is not on the axis', () => {
    expect(atmIv(frame({ atm: 99_000 }), STRIKES)).toBeNull();
  });
});

describe('the intraday series', () => {
  it('gives one volatility and one future per capture', () => {
    const v = view([frame(), frame({ t: '2026-09-03T04:01:00Z', future: 24_655 })]);
    expect(ivSeries(v)).toEqual([12, 12]);
    expect(futureSeries(v)).toEqual([24_640, 24_655]);
  });

  it('leaves a gap rather than a zero where a capture had no reading', () => {
    const blind = frame({ ce_iv: [18, 14, null, 13, 17], pe_iv: [20, 16, null, 14, 19] });
    expect(ivSeries(view([frame(), blind]))).toEqual([12, null]);
  });

  it('carries a null future through rather than substituting spot itself', () => {
    // The service already decides that fallback; doing it again here would
    // hide a capture that genuinely recorded neither.
    expect(futureSeries(view([frame({ future: null })]))).toEqual([null]);
  });
});

describe('expiry selection', () => {
  const listed = [
    '2026-09-08',
    '2026-09-15',
    '2026-09-22',
    '2026-09-29',
    '2026-10-06',
    '2026-10-13'
  ];

  it('opens on the nearest three, so the curve has a shape', () => {
    expect(defaultExpiries(listed)).toEqual(['2026-09-08', '2026-09-15', '2026-09-22']);
  });

  it('sorts before taking the nearest, whatever order they arrive in', () => {
    expect(defaultExpiries(['2026-10-06', '2026-09-08', '2026-09-15'])).toEqual([
      '2026-09-08',
      '2026-09-15',
      '2026-10-06'
    ]);
  });

  it('adds an expiry, and removes it when picked again', () => {
    expect(toggleExpiry([], '2026-09-08')).toEqual(['2026-09-08']);
    expect(toggleExpiry(['2026-09-08', '2026-09-15'], '2026-09-08')).toEqual(['2026-09-15']);
  });

  it('refuses a sixth but still lets one be removed', () => {
    const full = listed.slice(0, MAX_EXPIRIES);
    expect(full).toHaveLength(MAX_EXPIRIES);
    expect(toggleExpiry(full, '2026-10-13')).toBe(full);
    expect(toggleExpiry(full, full[0]!)).toHaveLength(MAX_EXPIRIES - 1);
  });

  it('opens on fewer than three when fewer are listed', () => {
    expect(defaultExpiries(['2026-09-08'])).toEqual(['2026-09-08']);
    expect(defaultExpiries([])).toEqual([]);
  });
});

describe('isFlatCurve', () => {
  const point = (expiry: string, atm_iv: number | null): TermPoint => ({
    expiry,
    atm_iv,
    days_to_expiry: 5
  });

  it('spots a curve where nothing varied by expiry', () => {
    // What a provider that ignores the expiry argument produces — worth naming
    // rather than drawing as if it were a market reading.
    expect(isFlatCurve([point('a', 12), point('b', 12), point('c', 12)])).toBe(true);
  });

  it('is false as soon as one expiry differs', () => {
    expect(isFlatCurve([point('a', 12), point('b', 12.5)])).toBe(false);
  });

  it('ignores expiries with no reading when judging flatness', () => {
    expect(isFlatCurve([point('a', 12), point('b', null), point('c', 12)])).toBe(true);
  });

  it('says nothing about a curve too short to be flat', () => {
    expect(isFlatCurve([point('a', 12)])).toBe(false);
    expect(isFlatCurve([])).toBe(false);
  });
});

describe('formatting and export', () => {
  it('shortens an expiry enough for a chip', () => {
    // `en-GB` abbreviates September to "Sept", which is what `expiryLabel`
    // already renders everywhere else in the app.
    expect(shortExpiry('2026-09-08')).toBe('08 Sept');
    expect(shortExpiry('2026-10-06')).toBe('06 Oct');
  });

  it('quotes a volatility to two decimals', () => {
    expect(fmtIv(9.6)).toBe('9.60');
  });

  it('exports the intraday series, blanking what was never quoted', () => {
    const csv = intradayCsv(
      ['2026-09-03T04:00:00Z', '2026-09-03T04:01:00Z'],
      [12, null],
      [24_640, null]
    );
    expect(csv.split('\n')).toEqual([
      'time,iv,future',
      '2026-09-03T04:00:00Z,12,24640',
      '2026-09-03T04:01:00Z,,'
    ]);
  });

  it('exports the term structure with its days to expiry', () => {
    const csv = termCsv([
      { expiry: '2026-09-08', atm_iv: 12, days_to_expiry: 5 },
      { expiry: '2026-09-15', atm_iv: null, days_to_expiry: 12 }
    ]);
    expect(csv.split('\n')).toEqual([
      'expiry,atm_iv,days_to_expiry',
      '2026-09-08,12,5',
      '2026-09-15,,12'
    ]);
  });

  it('names the download after the view it came from', () => {
    expect(csvFilename('NIFTY', 'intraday', '2026-09-03T04:00:00Z')).toBe(
      'iv-intraday-NIFTY-2026-09-03.csv'
    );
    expect(csvFilename('NIFTY', 'term', '2026-09-03T04:00:00Z')).toBe(
      'term-structure-NIFTY-2026-09-03.csv'
    );
    expect(csvFilename('NIFTY', 'term', undefined)).toBe('term-structure-NIFTY.csv');
  });
});
