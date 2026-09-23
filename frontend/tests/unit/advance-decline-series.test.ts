import { describe, expect, it } from 'vitest';
import {
  buildAdvanceDeclineSeriesOption,
  type AdvanceDeclineSeriesOptions,
  type BreadthSeriesPoint
} from '../../app/lib/shared/charts/options/advance-decline-series';
import type { ChartTheme } from '../../app/lib/shared/charts/theme/types';

/**
 * The breadth chart's option.
 *
 * This chart carries two y scales, which is the one shape that can imply a
 * correlation nobody measured. What is pinned here is the part that keeps it
 * honest: the counts share one axis anchored at zero, the level has its own,
 * and a sector — which has no index — gets no level axis at all rather than an
 * empty one the reader would take for a flat benchmark.
 */

const THEME = {
  axis: '#9aa3b8',
  grid: '#262b3a',
  surface: '#131722',
  tooltipBg: '#1a1f2e',
  tooltipText: '#e6e9f0',
  call: '#17b877',
  put: '#f2495c'
} as unknown as ChartTheme;

function point(over: Partial<BreadthSeriesPoint> = {}): BreadthSeriesPoint {
  return {
    at: '2026-09-22T04:00:00Z',
    advancing: 30,
    declining: 18,
    level: 23450,
    advancingWeight: 62.5,
    decliningWeight: 31.25,
    ...over
  };
}

const OPTIONS: AdvanceDeclineSeriesOptions = {
  weighted: false,
  levelName: 'NIFTY 50',
  formatTime: (iso: string) => iso,
  formatLevel: (value: number) => String(value)
};

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function build(points: BreadthSeriesPoint[], over: Partial<AdvanceDeclineSeriesOptions> = {}): any {
  return buildAdvanceDeclineSeriesOption(points, THEME, { ...OPTIONS, ...over });
}

describe('buildAdvanceDeclineSeriesOption', () => {
  it('puts both counts on one axis and the level on the other', () => {
    /* Advances and declines are the same unit and must never be drawn on two
       scales — that would make more declines than advances look like fewer. */
    const option = build([point(), point({ at: '2026-09-22T04:05:00Z' })]);

    const [advances, declines, level] = option.series;
    expect(advances.yAxisIndex).toBe(1);
    expect(declines.yAxisIndex).toBe(1);
    expect(level.yAxisIndex).toBe(0);
  });

  it('anchors the count axis at zero', () => {
    /* A count axis that floats to fit its data makes four advances occupy the
       same height as forty. */
    expect(build([point()]).yAxis[1].min).toBe(0);
  });

  it('draws no level axis for a scope that has no index', () => {
    const option = build([point({ level: null })], { levelName: null });

    expect(option.yAxis[0].show).toBe(false);
    expect(option.series).toHaveLength(2);
  });

  it('plots the head count by default', () => {
    const option = build([point()]);
    expect(option.series[0].data).toEqual([30]);
    expect(option.series[1].data).toEqual([18]);
  });

  it('plots index weight when asked, and it is a different number', () => {
    const option = build([point()], { weighted: true });
    expect(option.series[0].data).toEqual([62.5]);
    expect(option.series[1].data).toEqual([31.25]);
  });

  it('keeps the benchmark recessive behind the two counts', () => {
    /* It is context, not a third equal series. Dotted, thinner, and under
       them in z-order. */
    const option = build([point()]);
    const [advances, , level] = option.series;

    expect(level.lineStyle.type).toBe('dotted');
    expect(level.lineStyle.width).toBeLessThan(advances.lineStyle.width);
    expect(level.z).toBeLessThan(advances.z);
  });

  it('escapes series names in the tooltip', () => {
    /* Labels arrive from an API response, and ECharts' tooltip contract is an
       HTML string — so escaping is this module's job. */
    const option = build([point()], { levelName: '<img src=x onerror=alert(1)>' });
    const html = option.tooltip.formatter([
      { seriesName: '<img src=x onerror=alert(1)>', axisValue: 'now', value: 1, color: '#000' }
    ]);

    expect(html).not.toContain('<img');
    expect(html).toContain('&lt;img');
  });

  it('draws nothing from an empty session', () => {
    const option = build([]);
    expect(option.xAxis.data).toEqual([]);
    expect(option.series[0].data).toEqual([]);
  });
});
