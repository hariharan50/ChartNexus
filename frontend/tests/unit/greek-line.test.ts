/**
 * @vitest-environment node
 */
import { describe, expect, it } from 'vitest';
import { buildGreekLineOption, lastDefined } from '$shared/charts/options/greek-line';
import type { ChartTheme } from '$shared/charts/theme/types';
import {
  formatGreek,
  latestOf,
  legSeries,
  qualityNote,
  type GreekLeg,
  type GreeksView
} from '../../app/routes/terminal/tools/option-greeks/greeks-data';

/**
 * The Option Greeks panel's chart builder and its pure page helpers.
 *
 * What is pinned here is the handful of choices that, if they drifted, would
 * make the chart quietly wrong rather than visibly broken: an axis that
 * includes zero (which flattens an intraday IV session into a straight line), a
 * gap bridged across minutes nobody quoted, and a precision that rounds gamma
 * away to nothing.
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

const TIMES = ['2026-10-01T03:45:00Z', '2026-10-01T04:45:00Z', '2026-10-01T05:45:00Z'];

function build(values: (number | null)[], color = '#22c55e') {
  return buildGreekLineOption(
    {
      label: 'CE IV',
      color,
      timestamps: TIMES,
      values,
      formatValue: (value) => `${value.toFixed(2)}%`,
      formatTime: (iso) => iso.slice(11, 16)
    },
    THEME
  ) as {
    yAxis: { scale: boolean; position: string };
    series: {
      data: (number | null)[];
      connectNulls: boolean;
      lineStyle: { color: string };
      markLine?: { data: { yAxis: number }[]; label: { formatter: string } };
    }[];
  };
}

describe('greek line', () => {
  it('scales the axis to the data rather than anchoring it at zero', () => {
    /**
     * A session that ran 14.0 → 16.5 is the whole subject of this chart. An
     * axis from zero draws it as a motionless line two thirds up the panel.
     */
    const option = build([14.0, 15.2, 16.5]);

    expect(option.yAxis.scale).toBe(true);
    expect(option.yAxis.position).toBe('right');
  });

  it('leaves a gap where a leg was unquoted instead of bridging it', () => {
    const option = build([14.0, null, 16.5]);

    expect(option.series[0]!.connectNulls).toBe(false);
    expect(option.series[0]!.data).toEqual([14.0, null, 16.5]);
  });

  it('marks the last value that exists, not the last slot', () => {
    const option = build([14.0, 16.5, null]);

    expect(option.series[0]!.markLine?.data[0]!.yAxis).toBe(16.5);
    expect(option.series[0]!.markLine?.label.formatter).toBe('16.50%');
  });

  it('draws no marker at all for a leg that never priced', () => {
    expect(build([null, null, null]).series[0]!.markLine).toBeUndefined();
  });

  it('takes the series colour from the caller, so both panels can differ', () => {
    expect(build([1, 2, 3], '#ef4444').series[0]!.lineStyle.color).toBe('#ef4444');
  });
});

describe('lastDefined', () => {
  it('skips trailing gaps and reports nothing for an empty leg', () => {
    expect(lastDefined([1, 2, null])).toBe(2);
    expect(lastDefined([null, null])).toBeNull();
    expect(lastDefined([])).toBeNull();
    expect(latestOf([0.5, null])).toBe(0.5);
  });
});

describe('greek formatting', () => {
  it('gives each greek the precision it is actually read at', () => {
    // Gamma on an index is 1e-3-small: four places is a staircase, two is zero.
    expect(formatGreek('gamma', 0.001064)).toBe('0.001064');
    expect(formatGreek('iv', 14.25)).toBe('14.25%');
    expect(formatGreek('delta', 0.5267)).toBe('0.5267');
    expect(formatGreek('theta', -14.8855)).toBe('-14.8855');
  });
});

describe('leg series', () => {
  const leg: GreekLeg = {
    iv: [14],
    delta: [0.52],
    gamma: [0.001],
    theta: [-14],
    vega: [10.4],
    ltp: [120]
  };

  it('hands back the tab the reader picked', () => {
    expect(legSeries(leg, 'delta')).toEqual([0.52]);
    expect(legSeries(leg, 'gamma')).toEqual([0.001]);
  });
});

describe('quality note', () => {
  const view = (over: Partial<GreeksView>): GreeksView =>
    ({
      data_quality: 'intraday',
      iv_coverage: 1,
      ...over
    }) as GreeksView;

  it('says when a single live reading is all there is', () => {
    expect(qualityNote(view({ data_quality: 'live' }))).toMatch(/One live reading/);
  });

  it('says when part of the session had no quoted volatility', () => {
    expect(qualityNote(view({ iv_coverage: 0.4 }))).toMatch(/60% of captures/);
  });

  it('stays quiet on a complete session', () => {
    expect(qualityNote(view({}))).toBeNull();
    expect(qualityNote(undefined)).toBeNull();
  });
});
