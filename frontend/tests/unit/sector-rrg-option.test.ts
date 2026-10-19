/**
 * @vitest-environment node
 */
import { describe, expect, it } from 'vitest';
import { buildSectorRrgOption, rrgSpan, type RrgSeries } from '$shared/charts/options/sector-rrg';
import { withAlpha } from '$shared/charts/theme/tokens';
import type { ChartTheme } from '$shared/charts/theme/types';

/**
 * The rotation graph's option builder.
 *
 * Pure, so it is assertable in Node with no DOM and no ECharts instance. What
 * is worth asserting is everything that would still *draw* if it were wrong:
 * axes that are not square (which silently distorts every angle on a plane
 * whose whole meaning is direction), a quadrant tint taken from the wrong
 * theme role, and a head marker that is not the newest point.
 *
 * Distinct placeholder colours rather than real ones: these assert that the
 * builder reaches for the right theme *role*, and a recognisable hex would let
 * a wrong lookup pass unnoticed.
 */
const THEME: ChartTheme = {
  axis: '#a10000',
  accent: '#a20000',
  grid: '#a30000',
  surface: '#a40000',
  tooltipBg: '#a50000',
  tooltipText: '#a60000',
  up: '#a90000',
  down: '#aa0000',
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

function tail(
  sector: string,
  quadrant: RrgSeries['quadrant'],
  points: [number, number][]
): RrgSeries {
  return {
    sector,
    quadrant,
    measured: points.length,
    members: points.length,
    points: points.map(([x, y], index) => ({ at: `2026-10-16T0${index}:00:00Z`, x, y }))
  };
}

// `markArea` and `label` are declared here for the same reason as `itemStyle`:
// the assertions below narrow an entry to the one shape they care about, and a
// cast only type-checks against a type the property exists on.
type Series = {
  type: string;
  name?: string;
  data?: unknown[];
  z?: number;
  itemStyle?: unknown;
  label?: unknown;
  markArea?: unknown;
};

function seriesOf(option: unknown): Series[] {
  return (option as { series: Series[] }).series;
}

function axes(option: unknown) {
  const built = option as {
    xAxis: { min: number; max: number; name: string };
    yAxis: { min: number; max: number; name: string };
  };
  return built;
}

describe('rrgSpan', () => {
  it('never shrinks below a floor', () => {
    // A quiet board sits within a whisker of the centre, and an axis fitted to
    // that magnifies noise into what looks like violent rotation.
    const span = rrgSpan([tail('IT', 'leading', [[100.01, 100.02]])]);
    expect(span).toBeGreaterThanOrEqual(1.5);
  });

  it('grows to contain the widest point on either axis', () => {
    const span = rrgSpan([tail('IT', 'leading', [[106, 100]])]);
    expect(span).toBeGreaterThanOrEqual(6);
  });

  it('measures momentum as well as ratio', () => {
    // An early version only scanned x, which clipped a sector that had rotated
    // far up the momentum axis without gaining much relative strength.
    const span = rrgSpan([tail('IT', 'improving', [[100, 108]])]);
    expect(span).toBeGreaterThanOrEqual(8);
  });
});

describe('sector rotation graph', () => {
  const series = [
    tail('IT', 'leading', [
      [100.5, 100.4],
      [101.5, 101.2]
    ]),
    tail('PHARMA', 'lagging', [
      [99.5, 99.6],
      [99.1, 99.2]
    ])
  ];

  it('centres both axes on 100 and keeps them square', () => {
    // The plane's meaning is *direction* — a tail's angle says where a sector
    // is rotating to. Axes with different scales distort every angle on it.
    const { xAxis, yAxis } = axes(buildSectorRrgOption(series, THEME));
    expect(xAxis.min).toBe(yAxis.min);
    expect(xAxis.max).toBe(yAxis.max);
    expect((xAxis.min + xAxis.max) / 2).toBeCloseTo(100);
  });

  it('labels the axes as the JdK pair, not as prices', () => {
    const { xAxis, yAxis } = axes(buildSectorRrgOption(series, THEME));
    expect(xAxis.name).toMatch(/RS-Ratio/);
    expect(yAxis.name).toMatch(/RS-Momentum/);
  });

  it('draws a trail and a head for every sector', () => {
    const built = seriesOf(buildSectorRrgOption(series, THEME));
    expect(built.filter((entry) => entry.type === 'line')).toHaveLength(2);
    // One head scatter each, plus the single invisible quadrant layer.
    expect(built.filter((entry) => entry.type === 'scatter')).toHaveLength(3);
  });

  it('puts every head above every trail', () => {
    // Not just above its own: on a crowded centre a head drawn under another
    // sector's trail is the one mark the reader was looking for, buried.
    const built = seriesOf(buildSectorRrgOption(series, THEME));
    const trails = built.filter((entry) => entry.type === 'line');
    const heads = built.filter((entry) => entry.type === 'scatter' && entry.name);
    const highestTrail = Math.max(...trails.map((entry) => entry.z ?? 0));
    expect(Math.min(...heads.map((entry) => entry.z ?? 0))).toBeGreaterThan(highestTrail);
  });

  it('marks the head at the newest point', () => {
    const built = seriesOf(buildSectorRrgOption(series, THEME));
    const head = built.find((entry) => entry.type === 'scatter' && entry.name === 'IT');
    expect(head?.data).toEqual([[101.5, 101.2, 'IT', '2026-10-16T01:00:00Z']]);
  });

  it('takes each tail colour from the quadrant its head is in', () => {
    const built = seriesOf(buildSectorRrgOption(series, THEME));
    const head = (name: string) =>
      built.find((entry) => entry.type === 'scatter' && entry.name === name) as {
        itemStyle: { color: string };
      };
    expect(head('IT').itemStyle.color).toBe(THEME.up);
    expect(head('PHARMA').itemStyle.color).toBe(THEME.down);
  });

  it('tints the four quadrants from the four status roles', () => {
    // `withAlpha` resolves a hex to `rgba(...)`, so the tints are compared
    // against the same transform rather than by looking for the hex inside the
    // output — which would quietly pass for any colour once it stopped being
    // a substring match.
    const built = seriesOf(buildSectorRrgOption(series, THEME));
    const layer = built[0] as { markArea: { data: [{ itemStyle: { color: string } }, unknown][] } };
    const tints = layer.markArea.data.map(([corner]) => corner.itemStyle.color);
    for (const role of [THEME.up, THEME.accent, THEME.marker, THEME.down]) {
      const rgb = withAlpha(role, 1).replace(/,\s*1\)$/, '');
      expect(tints.some((tint) => tint.startsWith(rgb))).toBe(true);
    }
  });

  it('can be drawn without labels', () => {
    const built = seriesOf(buildSectorRrgOption(series, THEME, { labels: false }));
    const head = built.find((entry) => entry.type === 'scatter' && entry.name === 'IT') as {
      label: { show: boolean };
    };
    expect(head.label.show).toBe(false);
  });

  it('survives an empty board', () => {
    // No sector priced is a normal answer on a thin archive, not an error.
    const { xAxis } = axes(buildSectorRrgOption([], THEME));
    expect(Number.isFinite(xAxis.min)).toBe(true);
    expect(Number.isFinite(xAxis.max)).toBe(true);
  });
});
