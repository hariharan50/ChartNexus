import { describe, expect, it } from 'vitest';
import {
  csvFilename,
  expiryLabel,
  fmtGex,
  fmtGexSigned,
  frameBars,
  frameLevels,
  gexCsv,
  type GexFrame
} from '../../app/routes/terminal/options/gamma-exposure/gex-data';

/**
 * The Gamma Exposure page applies both its strike filter and its time scrub on
 * the client, so this arithmetic is everything between the payload and what the
 * chart, the levels row and the CSV export all show.
 */

const STRIKES = [24_500, 24_550, 24_600, 24_650, 24_700];

function frame(overrides: Partial<GexFrame> = {}): GexFrame {
  return {
    t: '2026-08-06T10:00:00+00:00',
    spot: 24_636,
    atm: 24_650,
    call_gex: [1, 2, 3, 4, 5],
    put_gex: [-5, -4, -3, -2, -1],
    net_total: 0,
    abs_total: 30,
    call_wall: 24_700,
    put_wall: 24_500,
    gamma_flip: 24_603,
    net_cross: 24_641,
    ...overrides
  };
}

describe('frameBars', () => {
  it('keeps only the strikes in the window, in axis order', () => {
    const bars = frameBars(STRIKES, frame(), new Set([24_550, 24_650]));

    expect(bars.map((bar) => bar.strike)).toEqual([24_550, 24_650]);
  });

  it('reads each side from the position the strike occupies on the axis', () => {
    // The whole payload is positional: a bar taking its value from the wrong
    // index would draw a real number against the wrong strike, which is the
    // one error nothing downstream could catch.
    const bars = frameBars(STRIKES, frame(), new Set([24_600]));

    expect(bars[0]).toMatchObject({ strike: 24_600, callGex: 3, putGex: -3 });
  });

  it('derives net and total from the two sides', () => {
    const bars = frameBars(STRIKES, frame(), new Set([24_700]));

    expect(bars[0]?.net).toBe(4); // 5 + -1
    expect(bars[0]?.abs).toBe(6); // |5| + |-1|
  });

  it('sees a strike that nets to zero because both sides are large', () => {
    // The one shape the net series cannot show on its own. If `abs` were
    // derived from `net` this strike would read as empty.
    const bars = frameBars([100], frame({ call_gex: [40], put_gex: [-40] }), new Set([100]));

    expect(bars[0]?.net).toBe(0);
    expect(bars[0]?.abs).toBe(80);
  });

  it('treats a strike the frame never priced as zero, not as a hole', () => {
    const bars = frameBars(STRIKES, frame({ call_gex: [1], put_gex: [-1] }), new Set(STRIKES));

    expect(bars).toHaveLength(STRIKES.length);
    expect(bars[4]).toMatchObject({ callGex: 0, putGex: 0, net: 0, abs: 0 });
  });
});

describe('fmtGex', () => {
  it('groups crore into lakh-crore and thousand-crore', () => {
    expect(fmtGex(44.09)).toBe('44.09 Cr');
    expect(fmtGex(1_234)).toBe('1.23 K Cr');
    expect(fmtGex(150_000)).toBe('1.50 L Cr');
  });

  it('drops below a crore into lakh rather than rounding a quiet strike away', () => {
    expect(fmtGex(0.42)).toBe('42.00 L');
  });

  it('carries the sign, which is the whole reading', () => {
    expect(fmtGex(-6.22)).toBe('-6.22 Cr');
    expect(fmtGexSigned(6.22)).toBe('+6.22 Cr');
    expect(fmtGexSigned(-6.22)).toBe('-6.22 Cr');
  });

  it('prints an unsigned zero rather than "-0.00 Cr"', () => {
    expect(fmtGex(0)).toBe('0');
    expect(fmtGex(-0.0001)).toBe('-0');
  });
});

describe('frameLevels', () => {
  it('measures each level against the frame it came from', () => {
    const levels = frameLevels(frame());
    const flip = levels.find((level) => level.id === 'gammaFlip');

    expect(flip?.strike).toBe(24_603);
    expect(flip?.gap).toBe(24_603 - 24_636);
  });

  it('reports a level the book does not have as absent, not as zero', () => {
    // `0` would plant a marker at the bottom of the ladder and read as a wall
    // at zero — worse than no marker.
    const levels = frameLevels(frame({ call_wall: null }));
    const wall = levels.find((level) => level.id === 'callWall');

    expect(wall?.strike).toBeNull();
    expect(wall?.gap).toBeNull();
  });

  it('still returns all four cells with no frame at all', () => {
    // The levels row is a fixed grid; a shorter array would reflow the layout
    // on every poll that arrived empty.
    const levels = frameLevels(undefined);

    expect(levels).toHaveLength(4);
    expect(levels.every((level) => level.strike === null)).toBe(true);
  });
});

describe('gexCsv', () => {
  it('exports one row per visible bar, under a stable header', () => {
    const bars = frameBars(STRIKES, frame(), new Set([24_550, 24_650]));

    const lines = gexCsv(bars, frame()).split('\n');

    expect(lines[1]).toBe('strike,call_gex_cr,put_gex_cr,net_gex_cr,abs_gex_cr');
    expect(lines).toHaveLength(4); // stamp + header + two rows
    expect(lines[2]).toBe('24550,2,-4,-2,6');
  });

  it('stamps the scrubbed frame, not the wall clock', () => {
    const bars = frameBars(STRIKES, frame(), new Set([24_600]));

    expect(gexCsv(bars, frame())).toContain('2026-08-06T10:00:00+00:00');
  });

  it('exports a header and a reason when there is no frame', () => {
    const text = gexCsv([], undefined);

    expect(text.split('\n')[0]).toBe('# no data');
    expect(text).toContain('strike,call_gex_cr');
  });
});

describe('csvFilename', () => {
  it('names the file after the instrument and the frame, in IST', () => {
    // 10:00 UTC is 15:30 IST — the file has to say which market minute it is,
    // and the viewer's zone is not the market's.
    expect(csvFilename('NIFTY', frame())).toBe('gex-NIFTY-2026-08-06-1530.csv');
  });

  it('falls back to a bare name when there is nothing to stamp', () => {
    expect(csvFilename('NIFTY', undefined)).toBe('gex-NIFTY.csv');
  });
});

describe('expiryLabel', () => {
  it('says when there is no expiry rather than printing an invalid date', () => {
    expect(expiryLabel(null)).toBe('Nearest expiry');
  });
});
