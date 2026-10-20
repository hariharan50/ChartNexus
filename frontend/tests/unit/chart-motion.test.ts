import { describe, expect, it } from 'vitest';
import { CHART_DURATION, withMotionDefaults } from '../../app/lib/shared/charts/motion-preference';

/**
 * Chart motion defaults.
 *
 * Three contracts, and the interesting one is the third:
 *
 *   1. A chart that says nothing about animation gets the house duration
 *      rather than ECharts' 1000ms default.
 *   2. A chart that has decided for itself is left alone — including the two
 *      builders that ship `animation: false`, which must not be revived.
 *   3. Reduced motion wins over both. The charts animate inside a canvas that
 *      no stylesheet can reach, so the global `prefers-reduced-motion` block
 *      in `app.css` does not cover them: this transform is the only thing
 *      standing between that preference and twenty-one chart builders.
 */
describe('withMotionDefaults', () => {
  it('gives an undecided option the house duration on mount and on update', () => {
    const out = withMotionDefaults({ series: [] }, false) as Record<string, unknown>;

    expect(out.animationDuration).toBe(CHART_DURATION);
    expect(out.animationDurationUpdate).toBe(CHART_DURATION);
    expect(out.animationEasing).toBe('cubicOut');
    expect(out.animationEasingUpdate).toBe('cubicOut');
  });

  it('is well under the 1000ms ECharts default it exists to replace', () => {
    expect(CHART_DURATION).toBeLessThan(500);
  });

  it('leaves a builder that disabled animation disabled', () => {
    const option = { animation: false as const, series: [] };
    expect(withMotionDefaults(option, false)).toBe(option);
  });

  it('leaves an explicit duration untouched', () => {
    const option = { animationDuration: 600, series: [] };
    expect(withMotionDefaults(option, false)).toBe(option);
  });

  it('stills every chart under reduced motion, explicit duration included', () => {
    const undecided = withMotionDefaults({ series: [] }, true) as Record<string, unknown>;
    const opinionated = withMotionDefaults({ animationDuration: 600, series: [] }, true) as Record<
      string,
      unknown
    >;

    expect(undecided.animation).toBe(false);
    expect(opinionated.animation).toBe(false);
  });

  it('does not mutate the option it is given', () => {
    const option = { series: [] };
    withMotionDefaults(option, false);
    expect(option).toEqual({ series: [] });
  });
});
