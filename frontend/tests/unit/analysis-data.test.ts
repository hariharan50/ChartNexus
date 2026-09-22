/**
 * @vitest-environment node
 */
import { describe, expect, it } from 'vitest';
import {
  CATEGORY_SLOTS,
  fmtCrore,
  fmtGross,
  fmtPoints,
  foldToSlots,
  OTHER_LABEL,
  quadrantMeta,
  ratioLabel,
  streakLabel
} from '../../app/routes/terminal/future-lab/analysis/analysis-data';

/**
 * The Analysis pages' shared vocabulary.
 *
 * Every assertion here is about a distinction the pages must not blur: a dash
 * is not a zero, a fold is not a truncation, and a signed number reads as a
 * direction rather than as a quantity.
 */

describe('money formatting', () => {
  it('prints a dash for an unknown figure, never a zero', () => {
    expect(fmtCrore(null)).toBe('—');
    expect(fmtCrore(undefined)).toBe('—');
    expect(fmtGross(null)).toBe('—');
  });

  it('always signs a net, because direction is the reading', () => {
    expect(fmtCrore(2140)).toBe('+2,140');
    expect(fmtCrore(-2140)).toBe('−2,140');
  });

  it('leaves an exact zero unsigned', () => {
    expect(fmtCrore(0)).toBe('0');
  });

  it('never signs a gross, which cannot be negative', () => {
    expect(fmtGross(14238)).toBe('14,238');
  });

  it('keeps two decimals on index points, where a member is often under one', () => {
    expect(fmtPoints('0.43')).toBe('+0.43');
    expect(fmtPoints(-12.5)).toBe('−12.50');
    expect(fmtPoints(null)).toBe('—');
  });
});

describe('streaks', () => {
  it('spells out the side, so a run never reads as money', () => {
    expect(streakLabel(4)).toBe('4 sessions buying');
    expect(streakLabel(-1)).toBe('1 session selling');
  });

  it('names a flat session rather than calling it a zero-length run', () => {
    expect(streakLabel(0)).toBe('No run');
  });
});

describe('advance/decline ratio', () => {
  it('reads as a ratio', () => {
    expect(
      ratioLabel({
        advancing: 30,
        declining: 20,
        unchanged: 0,
        unpriced: 0,
        ratio: '1.5',
        advancing_percent: '60',
        net: 10
      })
    ).toBe('1.50 : 1');
  });

  it('says what happened when nothing declined, rather than printing infinity', () => {
    expect(
      ratioLabel({
        advancing: 50,
        declining: 0,
        unchanged: 0,
        unpriced: 0,
        ratio: null,
        advancing_percent: '100',
        net: 50
      })
    ).toBe('All advancing');
  });

  it('falls back to a dash when nothing was counted at all', () => {
    expect(
      ratioLabel({
        advancing: 0,
        declining: 0,
        unchanged: 0,
        unpriced: 50,
        ratio: null,
        advancing_percent: null,
        net: 0
      })
    ).toBe('—');
  });
});

describe('folding to palette slots', () => {
  const rows = (count: number) =>
    Array.from({ length: count }, (_, index) => ({ name: `S${index}`, weight: count - index }));

  it('leaves a short list alone, ranked', () => {
    const folded = foldToSlots(
      rows(3),
      (row) => row.name,
      (row) => row.weight
    );

    expect(folded.map((slice) => slice.label)).toEqual(['S0', 'S1', 'S2']);
  });

  it('never returns more slices than the palette has slots', () => {
    const folded = foldToSlots(
      rows(20),
      (row) => row.name,
      (row) => row.weight
    );

    expect(folded).toHaveLength(CATEGORY_SLOTS);
    expect(folded.at(-1)?.label).toBe(OTHER_LABEL);
  });

  it('folds the tail rather than dropping it, so the slices still sum to the whole', () => {
    const source = rows(20);
    const total = source.reduce((sum, row) => sum + row.weight, 0);

    const folded = foldToSlots(
      source,
      (row) => row.name,
      (row) => row.weight
    );

    expect(folded.reduce((sum, slice) => sum + slice.value, 0)).toBe(total);
    // And Other keeps the rows behind it, so the page can still count them.
    expect(folded.at(-1)?.rows).toHaveLength(20 - (CATEGORY_SLOTS - 1));
  });
});

describe('rotation quadrants', () => {
  it('names each quadrant and what being in it means', () => {
    expect(quadrantMeta('leading').label).toBe('Leading');
    expect(quadrantMeta('improving').hint).toContain('not yet ahead');
  });
});
