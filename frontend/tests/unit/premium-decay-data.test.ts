import { describe, expect, it } from 'vitest';
import {
  changeFromRef,
  csvFilename,
  firstTotal,
  fmtPremium,
  fmtSignedPremium,
  premiumDecayCsv,
  premiumTotals,
  firstBarClose,
  prevTradingDay,
  rangeLabel,
  resolveWindow,
  windowIndices,
  type Selection
} from '../../app/routes/terminal/options/premium-decay/premium-decay-data';
import type {
  StraddleFrame,
  StraddleView
} from '../../app/routes/terminal/options/atm-straddle/straddle-data';

/**
 * Premium Decay reuses the straddle payload and does all of its aggregation on
 * the client, so this arithmetic is everything between the wire and what the two
 * charts, the sidebar range label and the CSV export show.
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

const sel = (overrides: Partial<Selection> = {}): Selection => ({
  mode: 'atm',
  atmSpan: 1,
  fixedStrike: null,
  fixedSpan: 1,
  customPicks: [],
  ...overrides
});

describe('resolveWindow', () => {
  it('windows ATM ± span around the money', () => {
    const w = resolveWindow(view([frame()]), sel({ mode: 'atm', atmSpan: 1 }));
    expect(w.strikes).toEqual([24_550, 24_600, 24_650]);
    expect(w.range).toEqual([24_550, 24_650]);
  });

  it('centres the fixed window on the chosen strike', () => {
    const w = resolveWindow(
      view([frame()]),
      sel({ mode: 'fixed', fixedStrike: 24_550, fixedSpan: 1 })
    );
    expect(w.strikes).toEqual([24_500, 24_550, 24_600]);
  });

  it('falls back to the ATM anchor when the fixed strike is unset', () => {
    const w = resolveWindow(
      view([frame()]),
      sel({ mode: 'fixed', fixedStrike: null, fixedSpan: 1 })
    );
    expect(w.strikes).toEqual([24_550, 24_600, 24_650]);
  });

  it('keeps only hand-picked strikes that exist on the axis', () => {
    const w = resolveWindow(
      view([frame()]),
      sel({ mode: 'custom', customPicks: [24_500, 24_700, 99_999] })
    );
    expect(w.strikes).toEqual([24_500, 24_700]);
    expect(w.range).toEqual([24_500, 24_700]);
  });

  it('is an empty window with no picks', () => {
    const w = resolveWindow(view([frame()]), sel({ mode: 'custom', customPicks: [] }));
    expect(w.strikes).toEqual([]);
    expect(w.range).toBeNull();
  });
});

describe('windowIndices / premiumTotals', () => {
  it('maps strikes to axis positions', () => {
    expect(windowIndices(STRIKES, [24_550, 24_600, 24_650])).toEqual([1, 2, 3]);
  });

  it('sums call and put premium over the window per frame', () => {
    const v = view([
      frame(),
      frame({ ce_ltp: [190, 150, 118, 88, 58], pe_ltp: [42, 57, 78, 112, 152] })
    ]);
    const totals = premiumTotals(v, [1, 2, 3]);
    // frame 0: ce 160+120+90=370, pe 55+75+110=240; frame 1: ce 150+118+88=356, pe 57+78+112=247.
    expect(totals.ce).toEqual([370, 356]);
    expect(totals.pe).toEqual([240, 247]);
  });

  it('skips a null leg rather than reading it as zero', () => {
    const v = view([frame({ ce_ltp: [200, null, 120, 90, 60] })]);
    // index 1 is null → ce over [1,2,3] is 120+90=210, pe 55+75+110=240.
    expect(premiumTotals(v, [1, 2, 3]).ce).toEqual([210]);
  });

  it('is null on a frame with the whole window missing', () => {
    const v = view([frame({ ce_ltp: [200, null, null, null, 60] })]);
    expect(premiumTotals(v, [1, 2, 3]).ce).toEqual([null]);
  });
});

describe('firstTotal / changeFromRef', () => {
  it('firstTotal is the first non-null point — the opening premium', () => {
    expect(firstTotal([null, 370, 380])).toBe(370);
    expect(firstTotal([null, null])).toBeNull();
  });

  it('changeFromRef reads each point against a fixed reference', () => {
    // Day Open: reference is the open (370) → cumulative change from open.
    expect(changeFromRef([370, 385, 375], 370)).toEqual([0, 15, 5]);
    // 1m Close: reference is the previous close (450) → the same curve, shifted.
    expect(changeFromRef([370, 385, 375], 450)).toEqual([-80, -65, -75]);
  });

  it('keeps a null point null and voids everything on a null reference', () => {
    expect(changeFromRef([370, null, 390], 370)).toEqual([0, null, 20]);
    expect(changeFromRef([370, 385], null)).toEqual([null, null]);
  });
});

describe('firstBarClose', () => {
  const times = ['04:00:00', '04:00:30', '04:01:10', '04:02:00'].map(
    (clock) => `2026-08-14T${clock}Z`
  );

  it('takes the last total printed inside the opening bar', () => {
    // Two captures land in the first minute; the second is the bar's close.
    expect(firstBarClose([370, 365, 350, 340], times, 1)).toBe(365);
  });

  it('ignores a null inside the bar and keeps the last real print', () => {
    expect(firstBarClose([370, null, 350, 340], times, 1)).toBe(370);
  });

  it('widens with the timeframe', () => {
    // At 3m every capture is still inside the opening bar.
    expect(firstBarClose([370, 365, 350, 340], times, 3)).toBe(340);
  });

  it('falls back to the opening total when the bar holds one capture', () => {
    // With nothing to close against, a bar's open and close are one reading.
    expect(firstBarClose([370, 365], [times[0]!, '2026-08-14T04:05:00Z'], 1)).toBe(370);
  });

  it('never reaches outside today', () => {
    // The regression: this anchor used to be the *previous session's* close,
    // which compares two different contracts the moment the expiry rolls — and
    // on 6 Oct 2026 resolved to a seeded mock day 400 index points away.
    expect(firstBarClose([], [], 1)).toBeNull();
  });
});

describe('prevTradingDay', () => {
  it('steps back one weekday', () => {
    // 2026-08-14 is a Friday → Thursday the 13th.
    expect(prevTradingDay('2026-08-14')).toBe('2026-08-13');
  });

  it('skips the weekend from a Monday', () => {
    // 2026-08-17 is a Monday → the prior Friday the 14th.
    expect(prevTradingDay('2026-08-17')).toBe('2026-08-14');
  });
});

describe('formatting / range', () => {
  it('formats a premium total to two decimals', () => {
    expect(fmtPremium(370)).toBe('370.00');
  });

  it('always signs a change', () => {
    expect(fmtSignedPremium(10)).toBe('+10.00');
    expect(fmtSignedPremium(-5)).toBe('-5.00');
    expect(fmtSignedPremium(0)).toBe('+0.00');
  });

  it('labels a strike span, a single strike, and an empty window', () => {
    expect(rangeLabel([24_550, 24_650])).toBe('24550 – 24650');
    expect(rangeLabel([24_600, 24_600])).toBe('24600');
    expect(rangeLabel(null)).toBe('—');
  });
});

describe('csv', () => {
  it('writes a header and one line per capture', () => {
    const lines = premiumDecayCsv([
      { t: '2026-08-14T04:00:00Z', ce: 370, pe: 240, future: 24_640 }
    ]).split('\n');
    expect(lines[0]).toBe('time,ce_premium,pe_premium,future');
    expect(lines[1]).toBe('2026-08-14T04:00:00Z,370,240,24640');
  });

  it('names the file after the day of the session', () => {
    const v = view([frame()], { now_ts: '2026-08-14T09:59:00Z' });
    expect(csvFilename('NIFTY', v)).toBe('premium-decay-NIFTY-2026-08-14.csv');
  });
});
