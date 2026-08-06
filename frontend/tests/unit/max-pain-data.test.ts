import { describe, expect, it } from 'vitest';
import type { OiStrike } from '../../app/routes/terminal/options/open-interest/oi-data';
import {
  fmtPain,
  maxPainBias,
  maxPainStrike,
  painCurve,
  visibleCurve,
  windowWidened,
  zoneAt
} from '../../app/routes/terminal/options/max-pain/max-pain-data';

/**
 * The Max Pain tool derives its whole chart on the client from the Open
 * Interest payload, so this arithmetic is the only thing between the archive
 * and what the page draws.
 */

/** An `OiStrike` carrying only the two fields the curve reads. */
function strike(at: number, callOi: number, putOi: number): OiStrike {
  return {
    strike: at,
    call_oi_open: callOi,
    call_oi_now: callOi,
    call_oi_chg: 0,
    call_oi_chg_pct: 0,
    put_oi_open: putOi,
    put_oi_now: putOi,
    put_oi_chg: 0,
    put_oi_chg_pct: 0
  };
}

describe('painCurve', () => {
  it('prices a two-strike chain the way the formula reads', () => {
    // 100: 10 calls, 0 puts.  200: 0 calls, 5 puts.
    const curve = painCurve([strike(100, 10, 0), strike(200, 0, 5)]);

    // Settling at 100: the calls at 100 are at the money (worth nothing), and
    // the puts at 200 are 100 in the money on 5 lots of OI.
    expect(curve[0]).toEqual({ strike: 100, callPain: 0, putPain: 500, total: 500 });
    // Settling at 200: the calls at 100 are now 100 in the money on 10.
    expect(curve[1]).toEqual({ strike: 200, callPain: 1000, putPain: 0, total: 1000 });
  });

  it('sorts by strike whatever order the payload arrived in', () => {
    const curve = painCurve([strike(200, 1, 1), strike(100, 1, 1), strike(150, 1, 1)]);
    expect(curve.map((p) => p.strike)).toEqual([100, 150, 200]);
  });

  it('charges nothing to calls at the lowest strike, nor to puts at the highest', () => {
    const curve = painCurve([strike(100, 7, 7), strike(150, 7, 7), strike(200, 7, 7)]);

    // No call can be in the money at the bottom of the ladder, and no put at
    // the top — the guard against an off-by-one in the two comparisons.
    expect(curve[0]!.callPain).toBe(0);
    expect(curve[2]!.putPain).toBe(0);
    expect(curve[0]!.putPain).toBeGreaterThan(0);
    expect(curve[2]!.callPain).toBeGreaterThan(0);
  });

  it('leaves a strike with no open interest beyond it costing nothing', () => {
    const curve = painCurve([strike(100, 0, 0), strike(200, 0, 0)]);
    expect(curve.every((p) => p.total === 0)).toBe(true);
  });

  it('returns nothing for an empty chain', () => {
    expect(painCurve([])).toEqual([]);
  });
});

describe('maxPainStrike', () => {
  it('finds the trough', () => {
    // Weight piles up at the ends, so the middle strike is cheapest to settle
    // at.
    const curve = painCurve([strike(100, 0, 90), strike(150, 10, 10), strike(200, 90, 0)]);
    expect(maxPainStrike(curve)).toBe(150);
  });

  it('agrees with the argmin the server reports', () => {
    // The guard for risk 2 in the plan: `max_pain` arrives on the payload and
    // the curve is derived here. If these two ever disagree, the client is
    // summing a different set of strikes than the server.
    const chain = [
      strike(24_300, 40_000, 10_000),
      strike(24_400, 60_000, 30_000),
      strike(24_500, 90_000, 90_000),
      strike(24_600, 30_000, 60_000),
      strike(24_700, 10_000, 40_000)
    ];

    // The same formula, written out independently rather than reusing the
    // module under test.
    const byHand = chain
      .map((candidate) => {
        const total = chain.reduce(
          (sum, row) =>
            sum +
            row.call_oi_now * Math.max(0, candidate.strike - row.strike) +
            row.put_oi_now * Math.max(0, row.strike - candidate.strike),
          0
        );
        return { strike: candidate.strike, total };
      })
      .reduce((best, p) => (p.total < best.total ? p : best));

    expect(maxPainStrike(painCurve(chain))).toBe(byHand.strike);
  });

  it('has no answer for an empty curve', () => {
    expect(maxPainStrike([])).toBeNull();
  });
});

describe('visibleCurve', () => {
  const curve = painCurve([100, 150, 200, 250, 300].map((k) => strike(k, 1, 1)));

  it('narrows to the chosen window', () => {
    expect(visibleCurve(curve, [150, 200, 250], 200).map((p) => p.strike)).toEqual([150, 200, 250]);
  });

  it('stretches to keep an off-window max pain on the chart', () => {
    // Decision 2: a Max Pain chart that does not show max pain is broken.
    expect(visibleCurve(curve, [150, 200], 300).map((p) => p.strike)).toEqual([150, 200, 250, 300]);
  });

  it('stretches downwards too', () => {
    expect(visibleCurve(curve, [200, 250], 100).map((p) => p.strike)).toEqual([100, 150, 200, 250]);
  });

  it('draws everything when no window was chosen', () => {
    expect(visibleCurve(curve, [], 200)).toHaveLength(5);
  });
});

describe('windowWidened', () => {
  it('is quiet when max pain already sits inside the window', () => {
    expect(windowWidened([150, 200, 250], 200)).toBe(false);
    expect(windowWidened([150, 200, 250], 150)).toBe(false);
  });

  it('reports a stretch at either end', () => {
    expect(windowWidened([150, 200], 300)).toBe(true);
    expect(windowWidened([150, 200], 100)).toBe(true);
  });

  it('is quiet with no window at all', () => {
    expect(windowWidened([], 100)).toBe(false);
  });
});

describe('fmtPain', () => {
  it('scales through K, M, B and T', () => {
    expect(fmtPain(940)).toBe('940');
    expect(fmtPain(1_000)).toBe('1.00K');
    expect(fmtPain(999_999)).toBe('1000.00K');
    expect(fmtPain(1_000_000)).toBe('1.00M');
    expect(fmtPain(1_290_000_000)).toBe('1.29B');
    expect(fmtPain(60_000_000_000)).toBe('60.00B');
    expect(fmtPain(2_500_000_000_000)).toBe('2.50T');
  });

  it('keeps the sign', () => {
    expect(fmtPain(-1_500)).toBe('-1.50K');
    expect(fmtPain(0)).toBe('0');
  });
});

describe('zoneAt', () => {
  it('splits the arc into five equal zones', () => {
    expect(zoneAt(0.1)).toBe('Strong sell');
    expect(zoneAt(0.3)).toBe('Sell');
    expect(zoneAt(0.5)).toBe('Neutral');
    expect(zoneAt(0.7)).toBe('Buy');
    expect(zoneAt(0.9)).toBe('Strong buy');
  });

  it('keeps both ends of the arc inside a zone', () => {
    expect(zoneAt(0)).toBe('Strong sell');
    // Not a sixth zone: an exact 1 has to fall in the last fifth.
    expect(zoneAt(1)).toBe('Strong buy');
  });

  it('clamps rather than inventing a zone off the end', () => {
    expect(zoneAt(-3)).toBe('Strong sell');
    expect(zoneAt(9)).toBe('Strong buy');
  });
});

describe('maxPainBias', () => {
  it('reads spot above max pain as a buy', () => {
    const bias = maxPainBias(24_600, 24_400);
    expect(bias.label).toBe('Buy');
    expect(bias.caption).toBe('Spot above Max Pain');
    // Right of centre on the gauge — direction is the whole signal here.
    expect(bias.position).toBeGreaterThan(0.5);
    expect(bias.gapPct).toBeGreaterThan(0);
  });

  it('reads spot below max pain as a sell', () => {
    const bias = maxPainBias(24_200, 24_400);
    expect(bias.label).toBe('Sell');
    expect(bias.position).toBeLessThan(0.5);
    expect(bias.gapPct).toBeLessThan(0);
  });

  it('escalates to the strong zones past a 1.2% gap', () => {
    // The outer fifths of a ±2% arc begin at ±1.2%.
    expect(maxPainBias(24_000 * 1.015, 24_000).label).toBe('Strong buy');
    expect(maxPainBias(24_000 * 0.985, 24_000).label).toBe('Strong sell');
  });

  it('calls a gap inside the middle fifth neutral', () => {
    // ±0.4% of max pain — the arc's central zone, and the only definition of
    // neutral on the page.
    expect(maxPainBias(24_405, 24_400).label).toBe('Neutral');
    expect(maxPainBias(24_470, 24_400).label).toBe('Neutral');
    expect(maxPainBias(24_330, 24_400).label).toBe('Neutral');
  });

  it('never names a zone the needle is not in', () => {
    // The guard for the one way the dial can lie: the word and the needle are
    // two renderings of one number, and only stay in step while the zone is
    // read off `position`.
    for (let spot = 23_800; spot <= 25_000; spot += 7) {
      const bias = maxPainBias(spot, 24_400);
      expect(bias.label).toBe(zoneAt(bias.position));
    }
  });

  it('reaches the end of the arc at a two-percent gap and never overruns it', () => {
    expect(maxPainBias(24_000 * 1.02, 24_000).position).toBeCloseTo(1);
    expect(maxPainBias(24_000 * 1.2, 24_000).position).toBe(1);
    expect(maxPainBias(24_000 * 0.8, 24_000).position).toBe(0);
  });

  it('stays neutral with nothing to compare', () => {
    const bias = maxPainBias(Number.NaN, Number.NaN);
    expect(bias.label).toBe('Neutral');
    // Dead centre, not zero: an empty gauge would read as a full bearish move.
    expect(bias.position).toBe(0.5);
    expect(bias.gapPct).toBe(0);
    expect(maxPainBias(24_500, 0).label).toBe('Neutral');
  });
});
