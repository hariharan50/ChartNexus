import { describe, expect, it } from 'vitest';
import {
  atmLabel,
  clampWindow,
  coverageNote,
  csvFilename,
  fmtIv,
  lowestIvStrike,
  nearestStrike,
  otmIv,
  overlayValues,
  skewBars,
  skewCsv,
  volRatio,
  type SkewFrame,
  type SkewView
} from '../../app/routes/terminal/options/volatility-skew/volatility-skew-data';

/**
 * The whole page is a projection of one payload, and the one piece of real
 * judgement in it is which of a strike's two volatilities the curve takes.
 * These pin that choice, the null handling that keeps an unquoted strike from
 * drawing as a real number, and the re-basing that makes a previous session
 * comparable to today's.
 */

const STRIKES = [24_500, 24_550, 24_600, 24_650, 24_700];
const SPOT = 24_610;

function frame(overrides: Partial<SkewFrame> = {}): SkewFrame {
  return {
    t: '2026-09-03T04:00:00Z',
    spot: SPOT,
    atm: 24_600,
    // A smile: lowest near the money, climbing into both wings.
    ce_iv: [18, 14, 11, 13, 17],
    pe_iv: [20, 16, 12, 14, 19],
    call_oi: [100, 200, 300, 400, 500],
    put_oi: [500, 400, 300, 200, 100],
    ...overrides
  };
}

function view(frames: SkewFrame[], overrides: Partial<SkewView> = {}): SkewView {
  return {
    instrument_id: 'NIFTY',
    symbol: 'NIFTY',
    expiry_date: '2026-09-08',
    lot_size: 75,
    spot: SPOT,
    atm_strike: 24_600,
    open_ts: frames[0]?.t ?? '',
    now_ts: frames.at(-1)?.t ?? '',
    data_quality: 'intraday',
    open_is_estimated: false,
    iv_coverage: 1,
    strikes: STRIKES,
    t: frames.map((f) => f.t),
    frames,
    ...overrides
  };
}

describe('otmIv', () => {
  it('takes the put below spot and the call above it', () => {
    // Spot 24610: 24500/24550/24600 are below, 24650/24700 above.
    expect(otmIv(frame(), STRIKES, SPOT)).toEqual([20, 16, 12, 13, 17]);
  });

  it('averages the two sides at a strike sitting exactly on spot', () => {
    // Neither leg is out of the money there; picking one would put a step in
    // the middle of the curve at the strike everyone reads.
    expect(otmIv(frame(), STRIKES, 24_600)[2]).toBe(11.5);
  });

  it('falls back to the quoted side when the other is missing at the money', () => {
    const f = frame({ ce_iv: [18, 14, null, 13, 17] });
    expect(otmIv(f, STRIKES, 24_600)[2]).toBe(12);
  });

  it('leaves a gap where the out-of-the-money leg was not quoted', () => {
    // The call is unquoted at 24700, which is the OTM side up there — so the
    // curve breaks rather than borrowing the deep-ITM put's wide quote.
    const f = frame({ pe_iv: [20, 16, 12, 14, null], ce_iv: [18, 14, 11, 13, null] });
    expect(otmIv(f, STRIKES, SPOT).at(-1)).toBeNull();
  });
});

describe('volRatio', () => {
  it('divides the call volatility by the put volatility', () => {
    expect(volRatio(frame(), STRIKES)[1]).toBeCloseTo(14 / 16);
  });

  it('is null unless both sides were quoted', () => {
    const f = frame({ ce_iv: [18, null, 11, 13, 17] });
    expect(volRatio(f, STRIKES)[1]).toBeNull();
  });

  it('is null rather than infinite on a zero put volatility', () => {
    const f = frame({ pe_iv: [0, 16, 12, 14, 19] });
    expect(volRatio(f, STRIKES)[0]).toBeNull();
  });
});

describe('skewBars', () => {
  it('windows the ladder inclusively at both handles', () => {
    const bars = skewBars(view([frame()]), frame(), { window: [1, 3], axis: 'strike' });
    expect(bars.map((bar) => bar.strike)).toEqual([24_550, 24_600, 24_650]);
  });

  it('labels by strike, or by position relative to the money', () => {
    const byStrike = skewBars(view([frame()]), frame(), { window: [0, 4], axis: 'strike' });
    expect(byStrike.map((bar) => bar.label)).toEqual(['24500', '24550', '24600', '24650', '24700']);

    const byAtm = skewBars(view([frame()]), frame(), { window: [0, 4], axis: 'atm' });
    expect(byAtm.map((bar) => bar.label)).toEqual(['ATM−2', 'ATM−1', 'ATM', 'ATM+1', 'ATM+2']);
  });

  it('re-bases the offsets on the shown capture, not on the latest one', () => {
    // The money moved to 24700 by this capture; the axis must follow it, or a
    // scrub back through the session labels every strike wrongly.
    const moved = frame({ atm: 24_700, spot: 24_695 });
    const bars = skewBars(view([frame(), moved]), moved, { window: [0, 4], axis: 'atm' });
    expect(bars.map((bar) => bar.label)).toEqual(['ATM−4', 'ATM−3', 'ATM−2', 'ATM−1', 'ATM']);
  });

  it('carries both raw volatilities as well as the blended curve', () => {
    const bar = skewBars(view([frame()]), frame(), { window: [0, 0], axis: 'strike' })[0]!;
    expect(bar.callIv).toBe(18);
    expect(bar.putIv).toBe(20);
    expect(bar.iv).toBe(20);
    expect(bar.callOi).toBe(100);
    expect(bar.putOi).toBe(500);
  });
});

describe('clampWindow', () => {
  it('keeps both handles on the ladder', () => {
    expect(clampWindow([-5, 99], 5)).toEqual([0, 4]);
  });

  it('never lets the low handle pass the high one', () => {
    expect(clampWindow([3, 1], 5)).toEqual([3, 3]);
  });

  it('collapses to nothing on an empty ladder', () => {
    expect(clampWindow([0, 4], 0)).toEqual([0, 0]);
  });
});

describe('lowestIvStrike', () => {
  it('finds the trough of the curve, which is not generally the money', () => {
    const bars = skewBars(view([frame()]), frame(), { window: [0, 4], axis: 'strike' });
    expect(lowestIvStrike(bars)).toBe(24_600);
  });

  it('is null for a curve with nothing quoted on it', () => {
    const blank = frame({
      ce_iv: [null, null, null, null, null],
      pe_iv: [null, null, null, null, null]
    });
    const bars = skewBars(view([blank]), blank, { window: [0, 4], axis: 'strike' });
    expect(lowestIvStrike(bars)).toBeNull();
  });
});

describe('overlayValues', () => {
  it('lines a prior session up by strike on the strike axis', () => {
    const prior = view([frame({ ce_iv: [1, 2, 3, 4, 5], pe_iv: [6, 7, 8, 9, 10] })]);
    const bars = skewBars(view([frame()]), frame(), { window: [0, 4], axis: 'strike' });
    // Prior spot is also 24610, so the same OTM split applies.
    expect(overlayValues(bars, prior, 'strike', 24_600)).toEqual([6, 7, 8, 4, 5]);
  });

  it('re-bases a prior session on its own money when the axis is ATM±', () => {
    // The index closed 100 points lower that day; aligned by strike the two
    // curves would be compared at different moneyness entirely.
    // Both sides equal, so the ATM average is unambiguous and this test is
    // about the shift rather than the blend.
    const priorFrame = frame({
      atm: 24_500,
      spot: 24_500,
      ce_iv: [11, 13, 17, 21, 25],
      pe_iv: [11, 13, 17, 21, 25]
    });
    const prior = view([priorFrame], { strikes: STRIKES, atm_strike: 24_500 });
    const bars = skewBars(view([frame()]), frame(), { window: [0, 4], axis: 'atm' });

    const values = overlayValues(bars, prior, 'atm', 24_600);
    // Today's ATM strike (24600) takes the prior day's own ATM (24500) value.
    expect(values[2]).toBe(11);
  });

  it('is all-null when the prior session has nothing archived', () => {
    const bars = skewBars(view([frame()]), frame(), { window: [0, 4], axis: 'strike' });
    expect(overlayValues(bars, undefined, 'strike', 24_600)).toEqual([
      null,
      null,
      null,
      null,
      null
    ]);
  });
});

describe('helpers and formatting', () => {
  it('names a strike by its distance from the money', () => {
    expect(atmLabel(24_600, 24_600, 50)).toBe('ATM');
    expect(atmLabel(24_700, 24_600, 50)).toBe('ATM+2');
    expect(atmLabel(24_500, 24_600, 50)).toBe('ATM−2');
  });

  it('falls back to the raw strike with no money to measure from', () => {
    expect(atmLabel(24_600, null, 50)).toBe('24600');
  });

  it('finds the ladder strike closest to a price', () => {
    expect(nearestStrike(STRIKES, 24_610)).toBe(24_600);
    expect(nearestStrike([], 24_610)).toBeNull();
  });

  it('quotes a volatility to one decimal', () => {
    expect(fmtIv(11.25)).toBe('11.3');
  });

  it('says nothing when every leg was priced, and warns when they were not', () => {
    expect(coverageNote(view([frame()]))).toBeNull();
    expect(coverageNote(view([frame()], { iv_coverage: 0 }))).toContain('No implied volatility');
    expect(coverageNote(view([frame()], { iv_coverage: 0.6 }))).toContain('60%');
  });

  it('exports the drawn curve, blanking what was never quoted', () => {
    const f = frame({ ce_iv: [null, 14, 11, 13, 17] });
    const bars = skewBars(view([f]), f, { window: [0, 0], axis: 'strike' });
    expect(skewCsv(bars).split('\n')).toEqual([
      'strike,iv,call_iv,put_iv,call_oi,put_oi,vol_ratio',
      '24500,20,,20,100,500,'
    ]);
  });

  it('names the download after the capture, not just the day', () => {
    expect(csvFilename('NIFTY', frame())).toBe('skew-NIFTY-2026-09-03-0400.csv');
    expect(csvFilename('NIFTY', undefined)).toBe('skew-NIFTY.csv');
  });
});
