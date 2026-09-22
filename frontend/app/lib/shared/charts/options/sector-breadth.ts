import type { EChartsCoreOption } from '../echarts-modules';
import type { ChartTheme } from '../theme/types';

/**
 * Advancing against declining, sector by sector.
 *
 * A **100% stacked horizontal bar**: every sector is a different size, and the
 * question the page asks is "what proportion of this sector is up", not "how
 * many names are up". Stacking raw counts would let BANKING's twelve members
 * dwarf CEMENT's two and answer a question nobody asked.
 *
 * Stacked is right here where it is wrong for the FII/DII panel, and the
 * difference is worth stating: these three segments *are* parts of one whole —
 * every member is advancing or declining or flat, and they sum to the sector —
 * whereas an FII crore and a DII crore sum to nothing anybody quotes.
 *
 * Unchanged is drawn in the neutral axis colour rather than a third hue. It is
 * not a third direction; it is the absence of one, and giving it a hue of its
 * own would invent a category at zero.
 */

export interface SectorBreadthBar {
  sector: string;
  advancing: number;
  declining: number;
  unchanged: number;
  /** For the hover card — the reason a sector's row is worth its width. */
  weightPercent: number;
  changePercent: number | null;
}

export interface SectorBreadthOptions {
  formatPercent: (value: number | null) => string;
}

export function buildSectorBreadthOption(
  bars: SectorBreadthBar[],
  theme: ChartTheme,
  options: SectorBreadthOptions
): EChartsCoreOption {
  // A horizontal category axis runs bottom-up; reversing puts the heaviest
  // sector (which the caller sorts first) at the top.
  const ordered = [...bars].reverse();
  const share = (bar: SectorBreadthBar, part: number) => {
    const total = bar.advancing + bar.declining + bar.unchanged;
    return total === 0 ? 0 : (part / total) * 100;
  };

  return {
    backgroundColor: 'transparent',
    grid: { left: 8, right: 16, top: 8, bottom: 8, containLabel: true },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      appendTo: 'body',
      backgroundColor: theme.tooltipBg,
      borderColor: theme.grid,
      textStyle: { color: theme.tooltipText, fontSize: 12 },
      padding: [8, 12],
      formatter: (params: unknown) => {
        const arr = params as Array<{ dataIndex: number }>;
        const bar = arr.length ? ordered[arr[0]!.dataIndex] : undefined;
        if (!bar) return '';
        return `
          <div style="font-weight:700;margin-bottom:4px">${bar.sector}</div>
          <div style="color:${theme.call}">Advancing: ${bar.advancing}</div>
          <div style="color:${theme.put}">Declining: ${bar.declining}</div>
          <div style="color:${theme.axis}">Unchanged: ${bar.unchanged}</div>
          <div>Sector move: ${options.formatPercent(bar.changePercent)}</div>
          <div>Weight: ${bar.weightPercent.toFixed(2)}%</div>`;
      }
    },
    xAxis: {
      type: 'value',
      max: 100,
      splitLine: { lineStyle: { color: theme.grid, type: 'dashed' } },
      axisLabel: { color: theme.axis, fontSize: 11, formatter: (value: number) => `${value}%` }
    },
    yAxis: {
      type: 'category',
      data: ordered.map((bar) => bar.sector),
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: theme.axis, fontSize: 11 }
    },
    series: [
      segment(
        'Advancing',
        ordered.map((bar) => share(bar, bar.advancing)),
        theme.call,
        theme
      ),
      segment(
        'Unchanged',
        ordered.map((bar) => share(bar, bar.unchanged)),
        theme.axis,
        theme
      ),
      segment(
        'Declining',
        ordered.map((bar) => share(bar, bar.declining)),
        theme.put,
        theme
      )
    ]
  };
}

function segment(name: string, data: number[], color: string, theme: ChartTheme) {
  return {
    name,
    type: 'bar' as const,
    stack: 'breadth',
    data,
    barMaxWidth: 18,
    // A 2px gap in the surface colour between segments: touching fills read as
    // one bar, and the boundary between advancing and declining is the whole
    // measurement.
    itemStyle: { color, borderColor: theme.surface, borderWidth: 1 }
  };
}
