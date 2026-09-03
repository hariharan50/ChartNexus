import { describe, expect, it } from 'vitest';
import {
  callLegs,
  csvFilename,
  defaultLegs,
  fmtPremium,
  hasLeg,
  legKey,
  legLabel,
  legSeries,
  legSeriesLabel,
  legsOnLadder,
  MAX_PICKS,
  multistrikeCsv,
  putLegs,
  sumLegs,
  toggleLeg,
  type Leg
} from '../../app/routes/terminal/options/multistrike/multistrike-data';
import type {
  StraddleFrame,
  StraddleView
} from '../../app/routes/terminal/options/atm-straddle/straddle-data';

/**
 * MultiStrike has no endpoint of its own: every line it draws is an index
 * lookup or a sum over the straddle payload. So this arithmetic is the whole
 * distance between the wire and the chart — in particular how a leg that stops
 * being quoted behaves on its own line versus inside a basket total, which are
 * deliberately different answers.
 */

const STRIKES = [24_500, 24_550, 24_600, 24_650, 24_700];

function frame(overrides: Partial<StraddleFrame> = {}): StraddleFrame {
  return {
    t: '2026-09-03T04:00:00Z',
    spot: 24_636,
    atm: 24_600,
    future: 24_640,
    atm_straddle: 195,
    ce_ltp: [200, 160, 120, 90, 60],
    pe_ltp: [40, 55, 75, 110, 150],
    ...overrides
  };
}

function view(frames: StraddleFrame[], overrides: Partial<StraddleView> = {}): StraddleView {
  return {
    instrument_id: 'NIFTY',
    symbol: 'NIFTY',
    expiry_date: '2026-09-08',
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

const ce = (strike: number): Leg => ({ strike, side: 'CE' });
const pe = (strike: number): Leg => ({ strike, side: 'PE' });

describe('leg identity', () => {
  it('keys a leg by strike and side, so the two sides never collide', () => {
    expect(legKey(ce(24_600))).toBe('24600-CE');
    expect(legKey(pe(24_600))).toBe('24600-PE');
  });

  it('labels a leg for the chip and for the chart legend', () => {
    expect(legLabel(ce(24_600))).toBe('24600 CE');
    expect(legSeriesLabel(pe(24_600))).toBe('24600 PE Price');
  });

  it('matches by value, not by object identity', () => {
    expect(hasLeg([ce(24_600)], { strike: 24_600, side: 'CE' })).toBe(true);
    expect(hasLeg([ce(24_600)], pe(24_600))).toBe(false);
  });
});

describe('legSeries', () => {
  it('reads one side of one strike off the shared strike axis', () => {
    const v = view([frame(), frame({ ce_ltp: [210, 170, 130, 95, 65] })]);
    expect(legSeries(v, ce(24_600))).toEqual([120, 130]);
    expect(legSeries(v, pe(24_500))).toEqual([40, 40]);
  });

  it('leaves a gap at a capture where the leg was not quoted', () => {
    const v = view([frame(), frame({ ce_ltp: [200, 160, null, 90, 60] })]);
    expect(legSeries(v, ce(24_600))).toEqual([120, null]);
  });

  it('is all-null for a strike that is not on the axis at all', () => {
    const v = view([frame(), frame()]);
    expect(legSeries(v, ce(99_000))).toEqual([null, null]);
  });
});

describe('sumLegs', () => {
  it('adds the picked legs at each capture', () => {
    const v = view([frame()]);
    // 120 CE + 75 PE at the money.
    expect(sumLegs(v, [ce(24_600), pe(24_600)])).toEqual([195]);
  });

  it('keeps the total of whatever is still quoted when one leg goes dark', () => {
    // A basket total with one dead wing is still what the rest of the basket
    // cost — unlike a straddle, where half the pair is a wrong number.
    const v = view([frame({ ce_ltp: [200, 160, null, 90, 60] })]);
    expect(sumLegs(v, [ce(24_600), pe(24_600)])).toEqual([75]);
  });

  it('voids a capture only when every leg in the basket is missing', () => {
    const v = view([frame({ ce_ltp: [200, 160, null, 90, 60], pe_ltp: [40, 55, null, 110, 150] })]);
    expect(sumLegs(v, [ce(24_600), pe(24_600)])).toEqual([null]);
  });

  it('has no total at all for an empty basket, rather than a line of zeros', () => {
    const v = view([frame(), frame()]);
    expect(sumLegs(v, [])).toEqual([null, null]);
  });

  it('splits into call and put totals that add back up to the combined one', () => {
    const v = view([frame()]);
    const legs = [ce(24_550), ce(24_600), pe(24_600), pe(24_650)];
    const calls = sumLegs(v, callLegs(legs))[0]!;
    const puts = sumLegs(v, putLegs(legs))[0]!;
    expect(calls).toBe(160 + 120);
    expect(puts).toBe(75 + 110);
    expect(sumLegs(v, legs)[0]).toBe(calls + puts);
  });
});

describe('selection', () => {
  it('opens on the ATM call and put', () => {
    expect(defaultLegs(view([frame()]))).toEqual([ce(24_600), pe(24_600)]);
  });

  it('opens on nothing when the chain has no ATM to centre on', () => {
    expect(defaultLegs(view([frame()], { atm_strike: null }))).toEqual([]);
    expect(defaultLegs(undefined)).toEqual([]);
  });

  it('adds a leg, and removes it when it is picked again', () => {
    expect(toggleLeg([], ce(24_600))).toEqual([ce(24_600)]);
    expect(toggleLeg([ce(24_600), pe(24_600)], ce(24_600))).toEqual([pe(24_600)]);
  });

  it('refuses a new leg at the cap but still lets one be removed', () => {
    const full: Leg[] = STRIKES.flatMap((strike) => [ce(strike), pe(strike)]).slice(0, MAX_PICKS);
    expect(full).toHaveLength(MAX_PICKS);
    expect(toggleLeg(full, ce(24_750))).toBe(full);
    expect(toggleLeg(full, full[0]!)).toHaveLength(MAX_PICKS - 1);
  });

  it('drops legs whose strike has rolled off the ladder', () => {
    const v = view([frame()]);
    expect(legsOnLadder([ce(24_600), ce(99_000)], v)).toEqual([ce(24_600)]);
  });

  it('leaves the selection alone while there is no payload to check it against', () => {
    const legs = [ce(99_000)];
    expect(legsOnLadder(legs, undefined)).toBe(legs);
  });
});

describe('formatting and export', () => {
  it('quotes a premium in points to two decimals', () => {
    expect(fmtPremium(195)).toBe('195.00');
    expect(fmtPremium(87.153)).toBe('87.15');
  });

  it('writes one CSV column per plotted line, with the future beside it', () => {
    const csv = multistrikeCsv(
      ['2026-09-03T04:00:00Z', '2026-09-03T04:01:00Z'],
      [24_640, null],
      [{ label: 'Total Call Premium', values: [280, null] }]
    );
    expect(csv.split('\n')).toEqual([
      'time,future,total_call_premium',
      '2026-09-03T04:00:00Z,24640,280',
      '2026-09-03T04:01:00Z,,'
    ]);
  });

  it('names the download after the session it holds', () => {
    expect(csvFilename('NIFTY', view([frame()]))).toBe('multistrike-NIFTY-2026-09-03.csv');
    expect(csvFilename('NIFTY', undefined)).toBe('multistrike-NIFTY.csv');
  });
});
