/**
 * @vitest-environment node
 */
import { describe, expect, it } from 'vitest';
import { buildCashFlowOption, type CashFlowPoint } from '$shared/charts/options/fii-dii-cash';
import { buildContributorsOption } from '$shared/charts/options/index-contributors';
import { buildSectorRotationOption } from '$shared/charts/options/sector-rotation';
import { buildWeightageOption } from '$shared/charts/options/index-weightage';
import type { ChartTheme } from '$shared/charts/theme/types';

/**
 * The Analysis pages' four chart builders.
 *
 * Pure functions, so their behaviour is assertable in Node with no DOM, no
 * ECharts instance and no canvas — the reason option construction lives
 * outside the components at all.
 *
 * Distinct placeholder colours rather than real ones: these tests assert that
 * a builder reaches for the right theme *role*, and a recognisable hex would
 * let a wrong lookup pass unnoticed.
 */
const THEME: ChartTheme = {
  axis: '#a10000',
  accent: '#a20000',
  grid: '#a30000',
  surface: '#a40000',
  tooltipBg: '#a50000',
  tooltipText: '#a60000',
  call: '#a70000',
  put: '#a80000',
  marker: '#a90000',
  atmBand: '#aa0000',
  onMarker: '#ab0000',
  spotLabelBg: '#ac0000',
  spotLabelText: '#ad0000',
  maxPainLabelBg: '#ae0000',
  series1: '#b10000',
  series2: '#b20000',
  series3: '#b30000',
  series4: '#b40000',
  series5: '#b50000',
  series6: '#b60000',
  series7: '#b70000',
  series8: '#b80000'
};

const identity = (value: number) => String(value);
/** The weightage and breadth builders format a nullable move. */
const identityOrDash = (value: number | null) => (value === null ? '—' : String(value));

describe('cash flow panels', () => {
  const points: CashFlowPoint[] = [
    { label: '01 Sep', fiiNet: -500, diiNet: 400, fiiCumulative: -500, diiCumulative: 400 },
    { label: '02 Sep', fiiNet: 300, diiNet: -100, fiiCumulative: -200, diiCumulative: 300 }
  ];

  it('never puts the daily and cumulative series on one pair of axes', () => {
    /**
     * The whole reason the page stacks two panels. A dual-axis chart lets the
     * choice of scale decide where the cumulative line crosses the bars.
     */
    const daily = buildCashFlowOption(points, THEME, { mode: 'daily', format: identity });
    const cumulative = buildCashFlowOption(points, THEME, {
      mode: 'cumulative',
      format: identity
    });

    for (const option of [daily, cumulative]) {
      expect(Array.isArray(option.yAxis)).toBe(false);
      expect(option.series).toHaveLength(2);
    }
  });

  it('draws bars for the daily panel and lines for the cumulative one', () => {
    const daily = buildCashFlowOption(points, THEME, { mode: 'daily', format: identity });
    const cumulative = buildCashFlowOption(points, THEME, {
      mode: 'cumulative',
      format: identity
    });

    expect((daily.series as { type: string }[]).map((entry) => entry.type)).toEqual(['bar', 'bar']);
    expect((cumulative.series as { type: string }[]).map((entry) => entry.type)).toEqual([
      'line',
      'line'
    ]);
  });

  it('never stacks the two participants — their crores are not a total', () => {
    const daily = buildCashFlowOption(points, THEME, { mode: 'daily', format: identity });

    for (const entry of daily.series as { stack?: unknown }[]) {
      expect(entry.stack).toBeUndefined();
    }
  });

  it('colours by participant, not by sign, so one series can be followed', () => {
    const daily = buildCashFlowOption(points, THEME, { mode: 'daily', format: identity });
    const [fii, dii] = daily.series as { itemStyle: { color: string } }[];

    expect(fii!.itemStyle.color).toBe(THEME.accent);
    expect(dii!.itemStyle.color).toBe(THEME.marker);
  });
});

describe('index contributors', () => {
  const bars = [
    { symbol: 'RELIANCE', points: 42.5, changePercent: 2.1, weightPercent: 8.3 },
    { symbol: 'INFY', points: -18.25, changePercent: -1.4, weightPercent: 5.3 }
  ];

  it('reverses the rows so the biggest push sits at the top of a horizontal axis', () => {
    const option = buildContributorsOption(bars, THEME, {
      formatPoints: identity,
      formatPercent: identity
    });

    expect((option.yAxis as { data: string[] }).data).toEqual(['INFY', 'RELIANCE']);
  });

  it('splits the two directions by hue and anchors the rounding to the zero line', () => {
    const option = buildContributorsOption(bars, THEME, {
      formatPoints: identity,
      formatPercent: identity
    });
    const data = (
      option.series as [{ data: { itemStyle: { color: string; borderRadius: number[] } }[] }]
    )[0].data;

    // Reversed, so INFY (negative) is first.
    expect(data[0]!.itemStyle.color).toBe(THEME.put);
    expect(data[0]!.itemStyle.borderRadius).toEqual([4, 0, 0, 4]);
    expect(data[1]!.itemStyle.color).toBe(THEME.call);
    expect(data[1]!.itemStyle.borderRadius).toEqual([0, 4, 4, 0]);
  });

  it('puts a negative bar’s label on its left, away from the zero line', () => {
    const option = buildContributorsOption(bars, THEME, {
      formatPoints: identity,
      formatPercent: identity
    });
    const data = (option.series as [{ data: { label: { position: string } }[] }])[0].data;

    expect(data[0]!.label.position).toBe('left');
    expect(data[1]!.label.position).toBe('right');
  });
});

describe('index weightage donut', () => {
  const slices = [
    { label: 'BANKING', share: 38.2, members: 8, changePercent: 1.1 },
    { label: 'IT', share: 12.4, members: 5, changePercent: -0.6 }
  ];

  it('assigns the categorical slots in order, never cycled', () => {
    const option = buildWeightageOption(slices, THEME, {
      centreLabel: 'sectors',
      centreValue: '48',
      formatPercent: identityOrDash
    });
    const data = (option.series as [{ data: { itemStyle: { color: string } }[] }])[0].data;

    expect(data.map((entry) => entry.itemStyle.color)).toEqual([THEME.series1, THEME.series2]);
  });

  it('labels every slice directly — the relief the light-theme palette requires', () => {
    const option = buildWeightageOption(slices, THEME, {
      centreLabel: 'sectors',
      centreValue: '48',
      formatPercent: identityOrDash
    });
    const series = (option.series as [{ label: { show: boolean } }])[0];

    expect(series.label.show).toBe(true);
  });
});

describe('sector rotation', () => {
  const points = [
    {
      sector: 'BANKING',
      relativeStrength: 0.8,
      participationOffset: 20,
      weightPercent: 36,
      changePercent: 1.2,
      advancing: 7,
      declining: 2,
      members: 9,
      quadrant: 'leading' as const,
      leaders: ['HDFCBANK'],
      laggards: []
    },
    {
      sector: 'IT',
      relativeStrength: -1.6,
      participationOffset: -30,
      weightPercent: 9,
      changePercent: -1.2,
      advancing: 1,
      declining: 4,
      members: 5,
      quadrant: 'lagging' as const,
      leaders: [],
      laggards: ['INFY']
    }
  ];

  it('pins the participation axis to its full range so the neutral line never moves', () => {
    const option = buildSectorRotationOption(points, THEME, { formatPercent: identity });

    expect(option.yAxis).toMatchObject({ min: -50, max: 50 });
  });

  it('keeps the strength axis symmetric, because the origin is the index itself', () => {
    const option = buildSectorRotationOption(points, THEME, { formatPercent: identity });
    const axis = option.xAxis as { min: number; max: number };

    expect(axis.min).toBe(-axis.max);
    expect(axis.max).toBeGreaterThanOrEqual(1.6);
  });

  it('sizes bubbles by the square root of weight, so the eye reads area', () => {
    const option = buildSectorRotationOption(points, THEME, { formatPercent: identity });
    const size = (option.series as [{ symbolSize: (v: unknown, p: unknown) => number }])[0]
      .symbolSize;

    // The heaviest sector saturates the scale; a quarter of its weight lands a
    // half-scale bubble, which is what a square root gives and a linear one
    // would not.
    expect(size(null, { dataIndex: 0 })).toBe(56);
    expect(size(null, { dataIndex: 1 })).toBeCloseTo(14 + 42 * Math.sqrt(9 / 36), 5);
  });

  it('labels each bubble with its sector rather than deferring to a legend', () => {
    const option = buildSectorRotationOption(points, THEME, { formatPercent: identity });
    const label = (option.series as [{ label: { formatter: (p: unknown) => string } }])[0].label;

    expect(label.formatter({ dataIndex: 1 })).toBe('IT');
  });
});
