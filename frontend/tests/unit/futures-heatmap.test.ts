import { describe, expect, it } from 'vitest';
import type { ChartTheme } from '../../app/lib/shared/charts/theme/types';
import { SERVER_CHART_THEME } from '../../app/lib/shared/charts/theme/tokens';
import {
  buildFuturesHeatmapOption,
  type HeatmapCell
} from '../../app/lib/shared/charts/options/futures-heatmap';

/**
 * The Future Lab heatmap.
 *
 * Price change has a meaningful zero, so this is a *diverging* scale: two hues
 * with a neutral midpoint. A hue at the midpoint would invent a third category
 * at "unchanged", and colour alone would be unreadable to a red/green
 * colour-blind reader — which is why every cell also prints its number.
 */

const theme: ChartTheme = SERVER_CHART_THEME;

function cell(overrides: Partial<HeatmapCell> = {}): HeatmapCell {
  return {
    symbol: 'RELIANCE',
    name: 'RELIANCE INDUSTRIES LTD',
    sector: 'OIL & GAS',
    changePercent: 1,
    turnover: 1_000_000,
    ...overrides
  };
}

/** The contract cells, whichever layout produced them. */
function leaves(option: unknown) {
  const series = (
    option as {
      series: { data: (Record<string, unknown> & { children?: Record<string, unknown>[] })[] }[];
    }
  ).series[0]!;
  return series.data.flatMap((node) => node.children ?? [node]);
}

describe('buildFuturesHeatmapOption', () => {
  it('groups cells by sector when asked', () => {
    const option = buildFuturesHeatmapOption(
      [
        cell({ symbol: 'RELIANCE', sector: 'OIL & GAS' }),
        cell({ symbol: 'ONGC', sector: 'OIL & GAS' }),
        cell({ symbol: 'TCS', sector: 'IT' })
      ],
      theme,
      { layout: 'sector' }
    );
    const groups = (option as { series: { data: { name: string }[] }[] }).series[0]!.data;

    expect(groups.map((g) => g.name)).toEqual(['IT', 'OIL & GAS']);
  });

  it('lays out one flat grid by default, with no sector nodes', () => {
    const option = buildFuturesHeatmapOption(
      [cell({ symbol: 'RELIANCE', sector: 'OIL & GAS' }), cell({ symbol: 'TCS', sector: 'IT' })],
      theme
    );
    const nodes = (
      option as {
        series: { data: { name: string; children?: unknown[] }[] }[];
      }
    ).series[0]!.data;

    expect(nodes).toHaveLength(2);
    expect(nodes.every((node) => node.children === undefined)).toBe(true);
    expect(nodes.map((n) => n.name).sort()).toEqual(['RELIANCE', 'TCS']);
  });

  it('orders the flat grid largest first', () => {
    // The treemap fills from the top-left, so sorting is what puts the
    // heavyweights where the eye starts.
    const option = buildFuturesHeatmapOption(
      [
        cell({ symbol: 'SMALL', turnover: 1_000 }),
        cell({ symbol: 'HUGE', turnover: 10_000_000 }),
        cell({ symbol: 'MID', turnover: 500_000 })
      ],
      theme
    );
    const nodes = (option as { series: { data: { name: string }[] }[] }).series[0]!.data;

    expect(nodes.map((n) => n.name)).toEqual(['HUGE', 'MID', 'SMALL']);
  });

  it('can size cells by something other than turnover', () => {
    const equal = buildFuturesHeatmapOption(
      [cell({ symbol: 'A', turnover: 1 }), cell({ symbol: 'B', turnover: 1_000_000 })],
      theme,
      { size: 'equal' }
    );
    const values = (leaves(equal) as { value: number }[]).map((l) => l.value);

    expect(new Set(values).size).toBe(1);
  });

  it('buckets a sectorless contract rather than dropping it', () => {
    const option = buildFuturesHeatmapOption([cell({ sector: null })], theme);

    expect(leaves(option)).toHaveLength(1);
  });

  it('gives a contract that barely traded a clickable area', () => {
    const option = buildFuturesHeatmapOption([cell({ turnover: 0 })], theme);

    expect((leaves(option)[0] as { value: number }).value).toBeGreaterThan(0);
  });

  it('compresses turnover so one giant does not swallow the board', () => {
    const option = buildFuturesHeatmapOption(
      [
        cell({ symbol: 'SMALL', turnover: 1_000_000 }),
        cell({ symbol: 'HUGE', turnover: 100_000_000 })
      ],
      theme
    );
    const [huge, small] = (leaves(option) as { name: string; value: number }[]).sort(
      (a, b) => b.value - a.value
    );

    // A hundredfold in turnover becomes tenfold in area under the square root.
    expect(huge!.value / small!.value).toBeCloseTo(10, 0);
  });

  it('paints gains and losses on opposite sides of a neutral midpoint', () => {
    const option = buildFuturesHeatmapOption(
      [
        cell({ symbol: 'UP', changePercent: 3 }),
        cell({ symbol: 'FLAT', changePercent: 0 }),
        cell({ symbol: 'DOWN', changePercent: -3 })
      ],
      theme
    );
    const colours = Object.fromEntries(
      (leaves(option) as { name: string; itemStyle: { color: string } }[]).map((l) => [
        l.name,
        l.itemStyle.color
      ])
    );

    expect(colours.UP).not.toBe(colours.DOWN);
    // The midpoint is a neutral, not either pole — a hue there would invent a
    // third category at "unchanged".
    expect(colours.FLAT).not.toBe(colours.UP);
    expect(colours.FLAT).not.toBe(colours.DOWN);
    expect(channels(colours.UP!).g).toBeGreaterThan(channels(colours.UP!).r);
    expect(channels(colours.DOWN!).r).toBeGreaterThan(channels(colours.DOWN!).g);
  });

  it('gives even a hairline move a visible tint', () => {
    // A contract down 0.1% is still down. Fading it into the background hides
    // most of a quiet session, which is what the old ramp did.
    const option = buildFuturesHeatmapOption(
      [cell({ symbol: 'TINY', changePercent: -0.1 }), cell({ symbol: 'FLAT', changePercent: 0 })],
      theme
    );
    const [flat, tiny] = (leaves(option) as { name: string; itemStyle: { color: string } }[]).sort(
      (a, b) => a.name.localeCompare(b.name)
    );

    expect(tiny!.itemStyle.color).not.toBe(flat!.itemStyle.color);
    // Clearly red, not a hint of it.
    expect(channels(tiny!.itemStyle.color).r - channels(flat!.itemStyle.color).r).toBeGreaterThan(
      25
    );
  });

  it('keeps deepening past the saturation point instead of clipping', () => {
    const option = buildFuturesHeatmapOption(
      [cell({ symbol: 'BIG', changePercent: -3 }), cell({ symbol: 'HUGE', changePercent: -9 })],
      theme
    );
    const byName = Object.fromEntries(
      (leaves(option) as { name: string; itemStyle: { color: string } }[]).map((l) => [
        l.name,
        l.itemStyle.color
      ])
    );

    expect(byName.HUGE).not.toBe(byName.BIG);
    // Deeper means darker, so a limit move reads as more extreme than a 3% one.
    expect(luminance(byName.HUGE!)).toBeLessThan(luminance(byName.BIG!));
  });

  it('treats an unmeasured change as neutral, never as a loss', () => {
    const unmeasured = buildFuturesHeatmapOption([cell({ changePercent: null })], theme);
    const flat = buildFuturesHeatmapOption([cell({ changePercent: 0 })], theme);

    const colourOf = (option: unknown) =>
      (leaves(option)[0] as { itemStyle: { color: string } }).itemStyle.color;

    // "We could not measure this" and "this did not move" look the same, and
    // both must be distinct from any loss.
    expect(colourOf(unmeasured)).toBe(colourOf(flat));
    expect(channels(colourOf(unmeasured)).r).toBeLessThan(120);
  });

  it('escapes company names going into the tooltip', () => {
    const option = buildFuturesHeatmapOption([cell({ name: 'A & B <script>' })], theme);
    const format = (option as { tooltip: { formatter: (p: unknown) => string } }).tooltip.formatter;

    const html = format({
      name: 'RELIANCE',
      data: { change: 1, company: 'A & B <script>' },
      treePathInfo: [{ name: '' }, { name: 'OIL & GAS' }, { name: 'RELIANCE' }]
    });

    expect(html).toContain('&amp;');
    expect(html).not.toContain('<script>');
  });
});

/** Pull the channels out of an `rgb(r, g, b)` string. */
function channels(colour: string): { r: number; g: number; b: number } {
  const [r, g, b] = colour.match(/\d+/g)!.map(Number);
  return { r: r!, g: g!, b: b! };
}

function luminance(colour: string): number {
  const { r, g, b } = channels(colour);
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

describe('the hover card', () => {
  const format = (data: Record<string, unknown>, depth = 3) => {
    const option = buildFuturesHeatmapOption([cell()], theme);
    const formatter = (option as { tooltip: { formatter: (p: unknown) => string } }).tooltip
      .formatter;
    return formatter({
      name: 'RELIANCE',
      data,
      treePathInfo: Array.from({ length: depth }, (_, i) => ({ name: `n${i}` }))
    });
  };

  it('reports price, both changes and the sentiment', () => {
    const html = format({
      change: 1.5,
      oiChange: -2.25,
      price: '1234.5',
      sentiment: 'Short Covering',
      company: 'RELIANCE INDUSTRIES LTD'
    });

    expect(html).toContain('Price');
    expect(html).toContain('+1.50%');
    expect(html).toContain('-2.25%');
    expect(html).toContain('Short Covering');
  });

  it('shows a dash for anything unmeasured rather than a zero', () => {
    const html = format({ change: null, oiChange: null, price: null });

    expect(html).toContain('—');
    expect(html).not.toContain('0.00%');
  });

  it('names a sector node without pretending it has a price', () => {
    const html = format({ change: 1 }, 2);

    expect(html).not.toContain('Price');
  });
});
