import type { EChartsCoreOption } from '../echarts-modules';
import type { ChartTheme } from '../theme/types';

/**
 * Cash-market FII and DII activity, as two charts rather than one.
 *
 * The page stacks a **daily** panel and a **cumulative** panel. That is a
 * deliberate refusal of the obvious design — bars for the daily net with the
 * running total as a line on a second y-axis — because a dual-axis chart lets
 * whoever picked the scales decide where the line crosses the bars, and a
 * reader has no way to know the crossing means nothing. Two panels on their own
 * axes say the same thing and cannot lie about it.
 *
 * **The two series are one pair, and the pairing is the point.** Domestic
 * institutions have spent years taking the other side of foreign flows, so
 * these bars mostly mirror each other; drawing them side by side at each
 * session is what makes that visible. They are never stacked — a crore bought
 * by an FII and a crore bought by a DII are not a total anybody quotes.
 *
 * Colour follows the participant, never the sign. It is tempting to paint every
 * negative bar red, but then the FII series changes colour day to day and the
 * eye can no longer follow one participant across the chart. The sign is
 * carried by which side of zero the bar is on, which is unambiguous and needs
 * no legend.
 */

export interface CashFlowPoint {
  /** Axis label, already formatted — this module does no date work. */
  label: string;
  fiiNet: number;
  diiNet: number;
  fiiCumulative: number;
  diiCumulative: number;
}

export interface CashFlowOptions {
  /** `daily` draws the paired bars; `cumulative` draws the two running lines. */
  mode: 'daily' | 'cumulative';
  /** Formats a crore figure for the axis and the tooltip. */
  format: (value: number) => string;
}

/** FII is the accent blue, DII the warning amber — see the note above. */
function palette(theme: ChartTheme): { fii: string; dii: string } {
  return { fii: theme.accent, dii: theme.marker };
}

export function buildCashFlowOption(
  points: CashFlowPoint[],
  theme: ChartTheme,
  options: CashFlowOptions
): EChartsCoreOption {
  const { mode, format } = options;
  const colors = palette(theme);
  const daily = mode === 'daily';

  return {
    backgroundColor: 'transparent',
    grid: { left: 8, right: 16, top: 16, bottom: 8, containLabel: true },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: daily ? 'shadow' : 'line', lineStyle: { color: theme.grid } },
      appendTo: 'body',
      backgroundColor: theme.tooltipBg,
      borderColor: theme.grid,
      textStyle: { color: theme.tooltipText, fontSize: 12 },
      padding: [8, 12],
      formatter: (params: unknown) => {
        const arr = params as Array<{ dataIndex: number }>;
        const point = arr.length ? points[arr[0]!.dataIndex] : undefined;
        if (!point) return '';
        const fii = daily ? point.fiiNet : point.fiiCumulative;
        const dii = daily ? point.diiNet : point.diiCumulative;
        return `
          <div style="font-weight:700;margin-bottom:4px">${point.label}</div>
          <div style="color:${colors.fii}">FII: ${format(fii)} Cr</div>
          <div style="color:${colors.dii}">DII: ${format(dii)} Cr</div>`;
      }
    },
    xAxis: {
      type: 'category',
      data: points.map((point) => point.label),
      axisLine: { lineStyle: { color: theme.grid } },
      axisTick: { show: false },
      // `hideOverlap` rather than a rotation: sixty sessions rotated to 45° eat
      // a third of the panel's height for labels nobody reads individually.
      axisLabel: { color: theme.axis, fontSize: 11, hideOverlap: true, margin: 10 }
    },
    yAxis: {
      type: 'value',
      splitLine: { lineStyle: { color: theme.grid, type: 'dashed' } },
      axisLabel: { color: theme.axis, fontSize: 11, formatter: format },
      // Zero is a real boundary on both panels — above it is money in.
      axisLine: { show: false }
    },
    series: daily ? bars(points, colors) : lines(points, colors, theme)
  };
}

function bars(points: CashFlowPoint[], colors: { fii: string; dii: string }) {
  // A 2px gap between the paired bars, per the app's mark spec: touching fills
  // read as one wide bar at this density.
  const shared = { type: 'bar' as const, barGap: '2%', barMaxWidth: 14 };
  return [
    {
      ...shared,
      name: 'FII',
      data: points.map((point) => point.fiiNet),
      itemStyle: { color: colors.fii, borderRadius: [2, 2, 0, 0] }
    },
    {
      ...shared,
      name: 'DII',
      data: points.map((point) => point.diiNet),
      itemStyle: { color: colors.dii, borderRadius: [2, 2, 0, 0] }
    }
  ];
}

function lines(points: CashFlowPoint[], colors: { fii: string; dii: string }, theme: ChartTheme) {
  const shared = {
    type: 'line' as const,
    smooth: false,
    showSymbol: false,
    lineStyle: { width: 2 },
    // A 2px ring in the surface colour where the two lines cross, so the
    // upper one stays readable instead of merging into the lower.
    emphasis: { focus: 'series' as const },
    symbolSize: 8,
    itemStyle: { borderColor: theme.surface, borderWidth: 2 }
  };
  return [
    {
      ...shared,
      name: 'FII',
      data: points.map((point) => point.fiiCumulative),
      lineStyle: { width: 2, color: colors.fii },
      itemStyle: { ...shared.itemStyle, color: colors.fii }
    },
    {
      ...shared,
      name: 'DII',
      data: points.map((point) => point.diiCumulative),
      lineStyle: { width: 2, color: colors.dii },
      itemStyle: { ...shared.itemStyle, color: colors.dii }
    }
  ];
}
