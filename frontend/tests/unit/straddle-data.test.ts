import { describe, expect, it } from 'vitest';
import {
  atmStraddleSeries,
  bollinger,
  bucketIndices,
  csvFilename,
  ema,
  fmtStraddle,
  futureSeries,
  selectedSeries,
  sma,
  straddleCsv,
  strikeStraddleSeries,
  strikeTable,
  type StraddleFrame,
  type StraddleView
} from '../../app/routes/terminal/options/atm-straddle/straddle-data';

/**
 * The Straddle chart applies both its strike selection and its timeframe on the
 * client, so this arithmetic is everything between the payload and what the
 * chart, the strike table and the CSV export all show.
 */

const STRIKES = [24_500, 24_550, 24_600, 24_650, 24_700];

function frame(overrides: Partial<StraddleFrame> = {}): StraddleFrame {
  return {
    t: '2026-08-14T04:00:00Z',
    spot: 24_636,
    atm: 24_600,
    future: 24_640,
    atm_straddle: 190,
    ce_ltp: [200, 160, 120, 90, 60],
    pe_ltp: [40, 55, 75, 110, 150],
    ...overrides
  };
}

function view(frames: StraddleFrame[], overrides: Partial<StraddleView> = {}): StraddleView {
  return {
    instrument_id: 'NIFTY',
    symbol: 'NIFTY',
    expiry_date: '2026-08-18',
    lot_size: 75,
    spot: 24_636,
    atm_strike: 24_600,
    open_ts: frames[0]?.t ?? '',
    now_ts: frames.at(-1)?.t ?? '',
    data_quality: 'intraday',
    open_is_estimated: false,
    strikes: STRIKES,
    t: frames.map((f) => f.t),
    frames,
    ...overrides
  };
}

describe('strikeStraddleSeries', () => {
  it('sums call and put at the chosen strike across frames', () => {
    const v = view([
      frame(),
      frame({ ce_ltp: [190, 150, 118, 88, 58], pe_ltp: [42, 57, 78, 112, 152] })
    ]);

    // 24_600 is index 2: 120+75 then 118+78.
    expect(strikeStraddleSeries(v, 24_600)).toEqual([195, 196]);
  });

  it('is null on a frame where either leg was unquoted', () => {
    const v = view([frame({ ce_ltp: [200, 160, null, 90, 60] })]);

    expect(strikeStraddleSeries(v, 24_600)).toEqual([null]);
  });

  it('is all-null for a strike not on the axis', () => {
    const v = view([frame()]);

    expect(strikeStraddleSeries(v, 99_999)).toEqual([null]);
  });
});

describe('selectedSeries', () => {
  it('rolls the ATM straddle for auto', () => {
    const v = view([frame({ atm_straddle: 190 }), frame({ atm_straddle: 210 })]);

    expect(selectedSeries(v, 'auto')).toEqual({ label: 'ATM Straddle', values: [190, 210] });
  });

  it('labels a fixed strike selection', () => {
    const v = view([frame()]);

    expect(selectedSeries(v, 24_600).label).toBe('24600 Straddle');
  });
});

describe('atmStraddleSeries / futureSeries', () => {
  it('reads the per-frame scalars', () => {
    const v = view([
      frame({ atm_straddle: 190, future: 24_640 }),
      frame({ atm_straddle: 205, future: 24_655 })
    ]);

    expect(atmStraddleSeries(v)).toEqual([190, 205]);
    expect(futureSeries(v)).toEqual([24_640, 24_655]);
  });
});

describe('strikeTable', () => {
  it('windows around the money and marks the ATM row', () => {
    const rows = strikeTable(view([frame()]), 100);

    // ±100 of ATM 24_600 keeps 24_500..24_700.
    expect(rows.map((r) => r.strike)).toEqual([24_500, 24_550, 24_600, 24_650, 24_700]);
    const atm = rows.find((r) => r.atm);
    expect(atm?.strike).toBe(24_600);
    expect(atm?.straddle).toBe(195); // 120 + 75
  });

  it('drops strikes outside the window', () => {
    const rows = strikeTable(view([frame()]), 50);

    expect(rows.map((r) => r.strike)).toEqual([24_550, 24_600, 24_650]);
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

  it('keeps the last point of each bucket, and always the open', () => {
    expect(bucketIndices(times, '3m')).toEqual([0, 2, 4]);
  });
});

describe('sma', () => {
  it('is null until the window fills, then the moving mean', () => {
    expect(sma([1, 2, 3, 4], 2)).toEqual([null, 1.5, 2.5, 3.5]);
  });

  it('voids any window spanning a null', () => {
    expect(sma([1, null, 3, 4], 2)).toEqual([null, null, null, 3.5]);
  });
});

describe('ema', () => {
  it('seeds on the first full window and then recurses', () => {
    const out = ema([2, 4, 6, 8], 2);
    // seed at index1 = mean(2,4)=3; k=2/3; index2 = 6*2/3 + 3*1/3 = 5; index3 = 8*2/3 + 5*1/3 = 7.
    expect(out[0]).toBeNull();
    expect(out[1]).toBeCloseTo(3);
    expect(out[2]).toBeCloseTo(5);
    expect(out[3]).toBeCloseTo(7);
  });
});

describe('bollinger', () => {
  it('brackets the moving average by k population deviations', () => {
    const { upper, lower } = bollinger([2, 4, 6], 2, 1);
    // window (2,4): mean 3, sd 1 -> [4,2]; window (4,6): mean 5, sd 1 -> [6,4].
    expect(upper).toEqual([null, 4, 6]);
    expect(lower).toEqual([null, 2, 4]);
  });
});

describe('formatting / csv', () => {
  it('formats a straddle premium to two decimals', () => {
    expect(fmtStraddle(190.5)).toBe('190.50');
  });

  it('writes a header naming the plotted series and one line per row', () => {
    const lines = straddleCsv(
      [{ t: '2026-08-14T04:00:00Z', straddle: 190, future: 24_640 }],
      'ATM Straddle'
    ).split('\n');

    expect(lines[0]).toBe('time,atm_straddle,future');
    expect(lines[1]).toBe('2026-08-14T04:00:00Z,190,24640');
  });

  it('names the file after the day of the session', () => {
    const v = view([frame()], { now_ts: '2026-08-14T09:59:00Z' });

    expect(csvFilename('NIFTY', v)).toBe('straddle-NIFTY-2026-08-14.csv');
  });
});
