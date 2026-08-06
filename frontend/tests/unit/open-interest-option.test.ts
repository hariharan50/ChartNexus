/**
 * @vitest-environment node
 */
import { describe, expect, it } from 'vitest';
import {
  buildOpenInterestOption,
  priceIndex,
  tooltipHtml,
  type OiChartBar,
  type OpenInterestInput
} from '$shared/charts/options/open-interest';
import { withAlpha } from '$shared/charts/theme/tokens';
import type { ChartTheme } from '$shared/charts/theme/types';

/**
 * The point of extracting the option builder from the component: chart
 * behaviour is a pure function, so it can be asserted in a Node process with no
 * DOM, no canvas and no ECharts instance.
 */

const THEME: ChartTheme = {
  axis: 'rgb(1, 1, 1)',
  grid: 'rgb(2, 2, 2)',
  tooltipBg: 'rgb(3, 3, 3)',
  tooltipText: 'rgb(4, 4, 4)',
  call: 'rgb(5, 5, 5)',
  put: 'rgb(6, 6, 6)',
  marker: 'rgb(7, 7, 7)',
  atmBand: 'rgb(8, 8, 8)',
  onMarker: 'rgb(9, 9, 9)',
  spotLabelBg: 'rgb(10, 10, 10)',
  spotLabelText: 'rgb(12, 12, 12)',
  maxPainLabelBg: 'rgb(11, 11, 11)'
};

function bar(strike: number, over: Partial<OiChartBar> = {}): OiChartBar {
  return {
    strike,
    callOpen: 1000,
    callNow: 1200,
    putOpen: 900,
    putNow: 800,
    callChg: 200,
    putChg: -100,
    atm: false,
    ...over
  };
}

const BARS: OiChartBar[] = [
  bar(24_400),
  bar(24_450),
  bar(24_500, { atm: true }),
  bar(24_550),
  bar(24_600)
];

function input(over: Partial<OpenInterestInput> = {}): OpenInterestInput {
  return {
    bars: BARS,
    mode: 'change_total',
    spot: 24_525,
    maxPain: 24_450,
    callColor: '#22c55e',
    putColor: '#ef4444',
    showTooltip: true,
    formatOi: (v) => `${v}`,
    formatSigned: (v) => (v >= 0 ? `+${v}` : `${v}`),
    openLabel: '9:15 am',
    nowLabel: '10:46 am',
    ...over
  };
}

// ECharts' option type is deliberately loose; these narrow it for assertions.
interface Series {
  name: string;
  stack: string;
  data: unknown[];
  markLine?: { data: Array<{ xAxis: number; label: { formatter: string } }> };
  markArea?: { data: Array<Array<{ xAxis: number }>> };
  itemStyle?: Record<string, unknown>;
}
const seriesOf = (option: unknown) => (option as { series: Series[] }).series;

describe('priceIndex', () => {
  const strikes = [100, 200, 300];

  it('lands between two strikes so a spot line is not forced onto a column', () => {
    expect(priceIndex(strikes, 150)).toBeCloseTo(0.5);
    expect(priceIndex(strikes, 250)).toBeCloseTo(1.5);
  });

  it('clamps outside the ladder rather than extrapolating off-chart', () => {
    expect(priceIndex(strikes, 10)).toBe(0);
    expect(priceIndex(strikes, 9_999)).toBe(2);
  });

  it('is exact on a strike', () => {
    expect(priceIndex(strikes, 200)).toBe(1);
  });

  it('survives an empty ladder', () => {
    expect(priceIndex([], 100)).toBe(0);
  });
});

describe('series per mode', () => {
  it('total mode draws one call and one put series of current OI', () => {
    const series = seriesOf(buildOpenInterestOption(input({ mode: 'total' }), THEME));
    expect(series).toHaveLength(2);
    expect(series.map((s) => s.name)).toEqual(['Call', 'Put']);
    expect(series[0]!.data).toEqual(BARS.map((b) => b.callNow));
    expect(series[1]!.data).toEqual(BARS.map((b) => b.putNow));
  });

  it('change mode plots absolute magnitudes, with the sign carried by style', () => {
    const series = seriesOf(buildOpenInterestOption(input({ mode: 'change' }), THEME));
    expect(series).toHaveLength(2);

    const call = series[0]!.data[0] as { value: number; itemStyle: { decal?: unknown } };
    const put = series[1]!.data[0] as {
      value: number;
      itemStyle: { color: string; borderType?: string };
    };

    // +200 and -100 both plot upward…
    expect(call.value).toBe(200);
    expect(put.value).toBe(100);
    // …so the increase gets a hatch and the decrease a dashed hollow bar.
    expect(call.itemStyle.decal).toBeDefined();
    expect(put.itemStyle.color).toBe('transparent');
    expect(put.itemStyle.borderType).toBe('dashed');
  });

  it('change_total mode stacks a change segment on a solid base', () => {
    const series = seriesOf(buildOpenInterestOption(input({ mode: 'change_total' }), THEME));
    expect(series.map((s) => s.name)).toEqual(['Call', 'CallChg', 'Put', 'PutChg']);

    // The base is min(open, now) so the change segment always sits on top,
    // whichever direction it went.
    expect(series[0]!.data).toEqual(BARS.map((b) => Math.min(b.callOpen, b.callNow)));
    expect(series[2]!.data).toEqual(BARS.map((b) => Math.min(b.putOpen, b.putNow)));
    expect(series[0]!.stack).toBe('call');
    expect(series[1]!.stack).toBe('call');
  });
});

describe('overlays', () => {
  it('puts the spot marker at a fractional index between strikes', () => {
    const series = seriesOf(buildOpenInterestOption(input(), THEME));
    const lines = series[0]!.markLine!.data;

    const spotLine = lines.find((l) => l.label.formatter.startsWith('Spot'))!;
    // 24525 is halfway between 24500 (index 2) and 24550 (index 3).
    expect(spotLine.xAxis).toBeCloseTo(2.5);
    expect(spotLine.label.formatter).toBe('Spot: 24525');
  });

  it('puts the max-pain marker on its strike column', () => {
    const series = seriesOf(buildOpenInterestOption(input(), THEME));
    const mpLine = series[0]!.markLine!.data.find((l) => l.label.formatter.startsWith('Max Pain'))!;
    expect(mpLine.xAxis).toBe(1);
    expect(mpLine.label.formatter).toBe('Max Pain: 24450');
  });

  it('bands the ATM column', () => {
    const series = seriesOf(buildOpenInterestOption(input(), THEME));
    expect(series[0]!.markArea!.data[0]).toEqual([{ xAxis: 1.5 }, { xAxis: 2.5 }]);
  });

  it('omits the ATM band when no bar is the ATM strike', () => {
    const option = buildOpenInterestOption(input({ bars: [bar(100), bar(200)] }), THEME);
    expect(seriesOf(option)[0]!.markArea).toBeUndefined();
  });

  it('omits the max-pain line when that strike is filtered out of view', () => {
    const option = buildOpenInterestOption(input({ maxPain: 99_999 }), THEME);
    const lines = seriesOf(option)[0]!.markLine!.data;
    expect(lines.some((l) => l.label.formatter.startsWith('Max Pain'))).toBe(false);
  });

  it('omits the spot line when spot is not a usable number', () => {
    for (const spot of [0, Number.NaN, Number.POSITIVE_INFINITY]) {
      const option = buildOpenInterestOption(input({ spot }), THEME);
      const lines = seriesOf(option)[0]!.markLine!.data;
      expect(lines.some((l) => l.label.formatter.startsWith('Spot'))).toBe(false);
    }
  });

  it('hangs the overlays off the first series only, so they are drawn once', () => {
    const series = seriesOf(buildOpenInterestOption(input(), THEME));
    expect(series[0]!.markLine).toBeDefined();
    expect(series.slice(1).every((s) => s.markLine === undefined)).toBe(true);
  });
});

describe('theming', () => {
  it('takes every chrome colour from the supplied theme', () => {
    const option = buildOpenInterestOption(input(), THEME) as {
      xAxis: { axisLine: { lineStyle: { color: string } }; axisLabel: { color: string } };
      yAxis: { splitLine: { lineStyle: { color: string } } };
      tooltip: { backgroundColor: string; textStyle: { color: string } };
    };

    expect(option.xAxis.axisLine.lineStyle.color).toBe(THEME.grid);
    expect(option.xAxis.axisLabel.color).toBe(THEME.axis);
    expect(option.yAxis.splitLine.lineStyle.color).toBe(THEME.grid);
    expect(option.tooltip.backgroundColor).toBe(THEME.tooltipBg);
    expect(option.tooltip.textStyle.color).toBe(THEME.tooltipText);
  });

  it('keeps the Call/Put palette separate from the theme', () => {
    const series = seriesOf(buildOpenInterestOption(input({ mode: 'total' }), THEME));
    expect(series[0]!.itemStyle!.color).toBe('#22c55e');
    expect(series[1]!.itemStyle!.color).toBe('#ef4444');
  });

  it('can be switched off entirely', () => {
    const option = buildOpenInterestOption(input({ showTooltip: false }), THEME) as {
      tooltip: { show: boolean };
    };
    expect(option.tooltip.show).toBe(false);
  });
});

describe('tooltip', () => {
  it('reports both legs against the window end points', () => {
    const html = tooltipHtml(input(), 2);
    expect(html).toContain('24500 · ATM');
    expect(html).toContain('OI @ 9:15 am: 1000');
    expect(html).toContain('OI @ 10:46 am: 1200');
    expect(html).toContain('OI Chg: +200 (+20.0%)');
    expect(html).toContain('OI Chg: -100 (-11.1%)');
  });

  it('does not divide by a zero opening OI', () => {
    const bars = [bar(100, { callOpen: 0, callNow: 50, callChg: 50 })];
    expect(tooltipHtml(input({ bars }), 0)).toContain('(+0.0%)');
  });

  it('returns nothing for an index past the end', () => {
    expect(tooltipHtml(input(), 99)).toBe('');
  });
});

describe('withAlpha', () => {
  it('handles the hex the Open Interest palette is declared in', () => {
    expect(withAlpha('#22c55e', 0.32)).toBe('rgba(34, 197, 94, 0.32)');
    expect(withAlpha('#abc', 0.5)).toBe('rgba(170, 187, 204, 0.5)');
  });

  it('handles the rgb() a resolved token arrives as', () => {
    expect(withAlpha('rgb(34, 197, 94)', 0.12)).toBe('rgba(34, 197, 94, 0.12)');
    expect(withAlpha('rgba(34, 197, 94, 0.8)', 0.12)).toBe('rgba(34, 197, 94, 0.12)');
  });

  it('passes anything it cannot parse straight through rather than emitting NaN', () => {
    expect(withAlpha('transparent', 0.5)).toBe('transparent');
  });
});
