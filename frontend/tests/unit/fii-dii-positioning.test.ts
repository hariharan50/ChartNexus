import { describe, expect, it } from 'vitest';
import type { OiGroup, OiRow, SegmentFlow } from '../../app/lib/contexts/market-breadth/types';
import {
  gaugePosition,
  longShortRead,
  matrixIntensity,
  moneyFlowRows,
  positioningMatrix,
  ratioVerdict,
  ratioZone
} from '../../app/routes/terminal/future-lab/analysis/analysis-data';

/**
 * The FII/DII Summary's derived readings.
 *
 * The long/short ratio is the number this page now leads with, so the cases
 * that matter are the ones where a naive implementation looks fine and is
 * wrong: a linear gauge that crushes every bearish reading into the left
 * sliver, and an undefined ratio rendered as a confident zero.
 */
function row(over: Partial<OiRow> = {}): OiRow {
  return {
    participant: 'fii',
    segment: 'index_futures',
    net: -303_000,
    previous_net: -291_000,
    change: -12_362,
    legs: {
      long: 40_257,
      short: 343_165,
      call_long: null,
      call_short: null,
      put_long: null,
      put_short: null,
      total: 383_422
    },
    ...over
  };
}

function groups(rows: OiRow[]): OiGroup[] {
  return [{ key: 'fii', rows, net: 0, change: 0 }];
}

describe('gaugePosition', () => {
  it('puts parity dead centre', () => {
    expect(gaugePosition(1)).toBeCloseTo(0.5, 6);
  });

  it('places halving and doubling equally far either side', () => {
    // The whole reason for the log scale. On a linear mapping 0.5 sits at 0.06
    // and 2.0 at 0.25 — both crammed into the bearish third of the dial.
    const short = gaugePosition(0.5);
    const long = gaugePosition(2);

    expect(0.5 - short).toBeCloseTo(long - 0.5, 6);
  });

  it('pins the extremes to the ends without overflowing', () => {
    expect(gaugePosition(1 / 16)).toBeCloseTo(0, 6);
    expect(gaugePosition(16)).toBeCloseTo(1, 6);
    expect(gaugePosition(1_000)).toBe(1);
    expect(gaugePosition(0.0001)).toBe(0);
  });

  it('keeps a real FII session off the very edge of the dial', () => {
    // 40,611 long against 339,224 short, from a live payload. An earlier
    // extent of 8 put this at exactly 0 — pegged, with no resolution left on
    // the readings this gauge exists to show.
    const position = gaugePosition(40_611 / 339_224);

    expect(position).toBeGreaterThan(0.02);
    expect(position).toBeLessThan(0.25);
  });

  it('refuses a ratio that cannot exist', () => {
    expect(gaugePosition(0)).toBe(0);
    expect(gaugePosition(Number.NaN)).toBe(0);
    expect(gaugePosition(-2)).toBe(0);
  });
});

describe('ratioZone', () => {
  it('calls the real session heavily short', () => {
    // 40,257 long against 343,165 short — the figures from a live payload.
    expect(ratioZone(40_257 / 343_165)).toBe('heavily_short');
  });

  it('treats a near-even book as balanced rather than picking a side', () => {
    expect(ratioZone(0.95)).toBe('balanced');
    expect(ratioZone(1.1)).toBe('balanced');
  });

  it('separates a lean from a conviction', () => {
    expect(ratioZone(0.7)).toBe('short');
    expect(ratioZone(1.5)).toBe('long');
    expect(ratioZone(3)).toBe('heavily_long');
  });
});

describe('longShortRead', () => {
  it('divides the two legs off the matching row', () => {
    const read = longShortRead(groups([row()]), 'fii', 'index_futures');

    expect(read?.long).toBe(40_257);
    expect(read?.short).toBe(343_165);
    expect(read?.ratio).toBeCloseTo(0.117, 3);
    expect(read?.zone).toBe('heavily_short');
  });

  it('has no reading when the short leg is zero, rather than Infinity', () => {
    const legs = { ...row().legs!, short: 0 };
    expect(longShortRead(groups([row({ legs })]), 'fii', 'index_futures')).toBeUndefined();
  });

  it('has no reading for an options row, which carries no long/short legs', () => {
    const legs = { ...row().legs!, long: null, short: null };
    const options = row({ segment: 'index_options', legs });

    expect(longShortRead(groups([options]), 'fii', 'index_options')).toBeUndefined();
  });

  it('has no reading when the participant is absent from the board', () => {
    expect(longShortRead(groups([row()]), 'dii', 'index_futures')).toBeUndefined();
    expect(longShortRead(undefined, 'fii', 'index_futures')).toBeUndefined();
  });
});

describe('ratioVerdict', () => {
  it('speaks in shorts-per-long rather than the raw ratio', () => {
    const read = longShortRead(groups([row()]), 'fii', 'index_futures')!;

    expect(ratioVerdict(read)).toContain('8.5 shorts for every long');
    expect(ratioVerdict(read)).toContain('fall');
  });

  it('claims no direction on a balanced book', () => {
    const legs = { ...row().legs!, long: 100_000, short: 100_000 };
    const read = longShortRead(groups([row({ legs })]), 'fii', 'index_futures')!;

    expect(ratioVerdict(read)).toContain('close to even');
  });
});

describe('positioningMatrix', () => {
  it('always returns the full 4x4, so cells keep their place', () => {
    const cells = positioningMatrix(groups([row()]));

    expect(cells).toHaveLength(16);
  });

  it('leaves an unpublished pair null instead of shifting the grid', () => {
    const cells = positioningMatrix(groups([row()]));
    const filled = cells.filter((cell) => cell.net !== null);

    expect(filled).toHaveLength(1);
    expect(filled[0]?.participant).toBe('fii');
    expect(filled[0]?.segment).toBe('index_futures');
  });
});

describe('matrixIntensity', () => {
  it('scales against the board peak, not an absolute figure', () => {
    // Segments differ by orders of magnitude; a fixed scale would leave most
    // cells invisible.
    expect(matrixIntensity(1_000, 1_000)).toBe(1);
    expect(matrixIntensity(-1_000, 1_000)).toBe(1);
  });

  it('keeps mid-sized cells visible rather than washing them out', () => {
    // Linear would give 0.25; the square root lifts it to 0.5.
    expect(matrixIntensity(250, 1_000)).toBeCloseTo(0.5, 6);
  });

  it('is nothing when there is nothing to scale', () => {
    expect(matrixIntensity(null, 1_000)).toBe(0);
    expect(matrixIntensity(500, 0)).toBe(0);
  });
});

describe('moneyFlowRows', () => {
  function segment(over: Partial<SegmentFlow> = {}): SegmentFlow {
    return {
      segment: 'cash',
      fii: { buy: '13580', sell: '11963', net: '1617' },
      dii: { buy: '14405', sell: '12063', net: '2341' },
      ...over
    };
  }

  it('leads with both cash participants', () => {
    const rows = moneyFlowRows([segment()]);

    expect(rows[0]?.label).toBe('FII Cash');
    expect(rows[0]?.net).toBe(1617);
    expect(rows[1]?.label).toBe('DII Cash');
    expect(rows[1]?.net).toBe(2341);
  });

  it('lists every derivative segment even when unpublished', () => {
    // A gap is honest; quietly listing four segments as three is not.
    const rows = moneyFlowRows([segment()]);

    expect(rows).toHaveLength(6);
    expect(rows.slice(2).every((entry) => entry.net === null)).toBe(true);
  });

  it('survives a payload with no segments at all', () => {
    expect(moneyFlowRows(undefined)).toHaveLength(6);
  });
});
