/**
 * @vitest-environment node
 */
import { describe, expect, it } from 'vitest';
import { buildMultiSeriesOption, type SeriesLine } from '$shared/charts/options/multi-series';
import type { ChartTheme } from '$shared/charts/theme/types';
import {
  coverageNote,
  formatStrike,
  sessionsOf,
  SPOT,
  STRADDLE,
  straddleColors,
  SYNTHETIC,
  timeLabel,
  type StraddleChartView
} from '../../app/routes/terminal/tools/straddle-chart/straddle-data';

/**
 * Straddle Chart's share of the multi-series engine, and its page helpers.
 *
 * The tool plots two quantities that must not share a scale — a premium in the
 * hundreds and an index level in the tens of thousands — so what is pinned here
 * is that each line lands on the axis it is measured against. `priceLines` is
 * the extension this tool needed: the chart already carried one price-axis line
 * (the future), and this one has two of the same kind.
 *
 * Placeholder colours rather than real ones: these assert a builder reaches for
 * the right theme *role*, and a recognisable hex would let a wrong lookup pass.
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

const TIMES = ['2026-10-01T03:45:00Z', '2026-10-01T04:45:00Z'];
const COLORS = straddleColors(THEME);

type Built = {
  yAxis: { name: string; position: string }[];
  series: {
    id: string;
    name: string;
    yAxisIndex: number;
    lineStyle: { color: string; type?: string; width: number };
    areaStyle?: unknown;
  }[];
  dataZoom?: unknown[];
};

function build({
  showSpot = true,
  showSynthetic = true
}: { showSpot?: boolean; showSynthetic?: boolean } = {}) {
  const priceLines: SeriesLine[] = showSynthetic
    ? [
        {
          id: 'synthetic',
          label: SYNTHETIC,
          color: COLORS[SYNTHETIC]!,
          values: [22464.8, 22348.7],
          dashed: true
        }
      ]
    : [];

  return buildMultiSeriesOption(
    {
      timestamps: TIMES,
      futures: [22421.95, 22324.8],
      showFutures: showSpot,
      priceLines,
      priceAxisName: 'Spot',
      lines: [
        {
          id: 'straddle',
          label: STRADDLE,
          color: COLORS[STRADDLE]!,
          values: [256.1, 311.9],
          fill: true
        }
      ],
      formatValue: (value: number) => value.toFixed(2),
      formatPrice: (value: number) => value.toFixed(2),
      valueAxisName: 'Straddle',
      zoomable: true
    },
    THEME
  ) as unknown as Built;
}

describe('straddle chart', () => {
  it('keeps the premium on the value axis and both index lines on the price axis', () => {
    /**
     * A straddle is in the hundreds and the index is in the tens of thousands.
     * On one axis the premium — the only line this chart exists for — flattens
     * into the baseline.
     */
    const option = build();

    const straddle = option.series.find((entry) => entry.id === 'straddle')!;
    const synthetic = option.series.find((entry) => entry.id === 'synthetic')!;
    const spot = option.series.find((entry) => entry.id === 'futures')!;

    expect(straddle.yAxisIndex).toBe(1);
    expect(synthetic.yAxisIndex).toBe(0);
    expect(spot.yAxisIndex).toBe(0);
  });

  it('names the left axis for what actually plots there', () => {
    const option = build();

    expect(option.yAxis[0]!.name).toBe('Spot');
    expect(option.yAxis[0]!.position).toBe('left');
    expect(option.yAxis[1]!.position).toBe('right');
  });

  it('draws the forward dotted, so it does not read as one line with spot', () => {
    const synthetic = build().series.find((entry) => entry.id === 'synthetic')!;

    expect(synthetic.lineStyle.type).toBe('dotted');
    expect(synthetic.lineStyle.width).toBeLessThan(2);
  });

  it('bands the straddle, which is the one subject line', () => {
    expect(build().series.find((entry) => entry.id === 'straddle')!.areaStyle).toBeDefined();
  });

  it('omits a line entirely when its chip is switched off', () => {
    const option = build({ showSpot: false, showSynthetic: false });

    expect(option.series.find((entry) => entry.id === 'futures')).toBeUndefined();
    expect(option.series.find((entry) => entry.id === 'synthetic')).toBeUndefined();
    // The straddle survives on its own — it is the chart.
    expect(option.series.find((entry) => entry.id === 'straddle')).toBeDefined();
  });

  it('takes the wheel, so Reset zoom has something to reset', () => {
    expect(build().dataZoom).toHaveLength(1);
  });

  it('gives the two coloured lines distinct contract-palette colours', () => {
    expect(COLORS[STRADDLE]).not.toBe(COLORS[SYNTHETIC]);
    // Spot plots in the price-reference slot, which the chart draws itself.
    expect(COLORS[SPOT]).toBeUndefined();
  });
});

describe('straddle page helpers', () => {
  const view = (over: Partial<StraddleChartView>): StraddleChartView =>
    ({
      data_quality: 'intraday',
      requested_sessions: 3,
      covered_sessions: 3,
      ...over
    }) as StraddleChartView;

  it('reads a range as a count of sessions', () => {
    expect(sessionsOf('3')).toBe(3);
    expect(sessionsOf('nonsense')).toBe(1);
  });

  it('says when the archive held fewer sessions than were asked for', () => {
    expect(coverageNote(view({ covered_sessions: 1 }))).toMatch(/1 of 3 sessions/);
    expect(coverageNote(view({ data_quality: 'live' }))).toMatch(/One live reading/);
    expect(coverageNote(view({}))).toBeNull();
  });

  it('prefixes the day only once the window spans more than one session', () => {
    // 03:45 UTC is 09:15 IST — the bell.
    expect(timeLabel('2026-10-01T03:45:00Z', false)).toBe('09:15');
    expect(timeLabel('2026-10-01T03:45:00Z', true)).toBe('01/10 09:15');
  });

  it('keeps a fractional strike fractional', () => {
    expect(formatStrike(22400)).toBe('22400');
    expect(formatStrike(2512.5)).toBe('2512.5');
  });
});
