import type { EChartsCoreOption } from '../echarts-modules';
import type { ChartTheme } from '../theme/types';
import { priceIndex } from './open-interest';

/**
 * The per-strike dealer-gamma profile behind the Gamma Exposure tool.
 *
 * Pure: takes already-derived bars and returns an ECharts option, like its
 * siblings in this folder. No React, no DOM, no chart instance — which layout
 * draws what, and where the five markers land, is testable without rendering.
 *
 * **Two value axes, not one.** Net exposure is signed and centred on zero; total
 * exposure is a magnitude that never goes negative and typically runs an order
 * larger. Sharing one axis crushes the net bars into a band a few pixels tall.
 * Left carries the bars, right carries the line, and both name their unit.
 *
 * **The sign is the chart.** Positive net exposure means dealers are long gamma
 * and hedge *against* the move, damping it; negative means they hedge with it,
 * amplifying it. So a bar's side of zero is the reading, and the palette follows
 * the sign rather than the side of spot — a red bar above spot is real
 * information, not a rendering slip.
 */

/** One strike's row. Structurally the `GexBar` from the Gamma Exposure page. */
export interface GexChartBar {
  strike: number;
  callGex: number;
  putGex: number;
  net: number;
  abs: number;
}

export type GexChartLayout = 'horizontal' | 'vertical' | 'callPut';

/** One labelled vertical reference on the profile. */
export interface GexMarker {
  id: string;
  label: string;
  strike: number;
  color: string;
  /** Chips are stacked in this order so they cannot overprint each other. */
  slot: number;
}

export interface GammaExposureInput {
  bars: GexChartBar[];
  layout: GexChartLayout;
  spot: number;
  /** Walls and flips, already filtered by the sidebar's two toggles. */
  markers: GexMarker[];
  showNet: boolean;
  showAbs: boolean;
  callColor: string;
  putColor: string;
  /** Formats an exposure for the axes and the tooltip. */
  formatGex: (value: number) => string;
}

/** Vertical spacing between stacked marker chips, in pixels. */
const CHIP_PITCH = 22;

export function buildGammaExposureOption(
  input: GammaExposureInput,
  theme: ChartTheme
): EChartsCoreOption {
  const vertical = input.layout === 'vertical';
  const categories = input.bars.map((bar) => String(bar.strike));

  const categoryAxis = {
    type: 'category' as const,
    data: categories,
    axisLine: { lineStyle: { color: theme.grid } },
    axisTick: { show: false },
    axisLabel: { color: theme.axis, fontSize: 11, hideOverlap: true, margin: 10 }
  };

  const netAxis = {
    type: 'value' as const,
    name: 'Net GEX (Cr / 1%)',
    nameTextStyle: { color: theme.axis, fontSize: 10 },
    splitLine: { lineStyle: { color: theme.grid, type: 'dashed' as const } },
    axisLabel: { color: theme.axis, fontSize: 11, formatter: input.formatGex }
  };

  const absAxis = {
    type: 'value' as const,
    name: 'ABS GEX (Cr / 1%)',
    nameTextStyle: { color: theme.axis, fontSize: 10 },
    // Only one grid of split lines, or the two axes draw a lattice nothing can
    // be read through.
    splitLine: { show: false },
    axisLabel: { color: theme.axis, fontSize: 11, formatter: input.formatGex }
  };

  return {
    backgroundColor: 'transparent',
    // Room at the top for the stacked marker chips, and on both flanks for the
    // two axes' names.
    grid: { left: 8, right: 16, top: 24 + CHIP_PITCH * 2, bottom: 8, containLabel: true },
    tooltip: tooltip(input, theme),
    xAxis: vertical ? [netAxis, absAxis] : categoryAxis,
    yAxis: vertical ? categoryAxis : [netAxis, absAxis],
    series: series(input, theme)
  };
}

function series(input: GammaExposureInput, theme: ChartTheme) {
  const { bars, layout, callColor, putColor, showNet, showAbs } = input;
  const vertical = layout === 'vertical';
  const out: Record<string, unknown>[] = [];

  if (showNet && layout === 'callPut') {
    // Split view: the two sides as they stand, rather than what they net to.
    // Useful when a strike's net is small because both sides are large — the
    // one case the net series cannot show.
    out.push(
      {
        name: 'Call GEX',
        type: 'bar',
        data: bars.map((bar) => bar.callGex),
        itemStyle: { color: callColor },
        ...(vertical ? { xAxisIndex: 0 } : { yAxisIndex: 0 }),
        z: 2
      },
      {
        name: 'Put GEX',
        type: 'bar',
        data: bars.map((bar) => bar.putGex),
        itemStyle: { color: putColor },
        ...(vertical ? { xAxisIndex: 0 } : { yAxisIndex: 0 }),
        z: 2
      }
    );
  } else if (showNet) {
    out.push({
      name: 'Net GEX',
      type: 'bar',
      // Coloured per bar by the sign of the value, not by the strike's position
      // relative to spot — see the module note.
      data: bars.map((bar) => ({
        value: bar.net,
        itemStyle: { color: bar.net >= 0 ? callColor : putColor }
      })),
      ...(vertical ? { xAxisIndex: 0 } : { yAxisIndex: 0 }),
      z: 2
    });
  }

  if (showAbs) {
    out.push({
      name: 'ABS GEX',
      type: 'line',
      data: bars.map((bar) => bar.abs),
      ...(vertical ? { xAxisIndex: 1 } : { yAxisIndex: 1 }),
      smooth: true,
      symbol: 'none',
      lineStyle: { color: theme.marker, width: 1.5 },
      itemStyle: { color: theme.marker },
      z: 3
    });
  }

  // The markers hang off whichever series is first, so they survive either
  // toggle being switched off. When both are off there is nothing to draw them
  // on — and nothing to draw them against.
  const host = out[0];
  if (host) host['markLine'] = markers(input, theme);

  return out;
}

/**
 * Spot plus the four derived levels.
 *
 * Spot keeps the treatment it has on Open Interest and Max Pain — dotted, on a
 * raised-surface chip — so a reader moving between the three pages sees the
 * same marker mean the same thing. The derived levels are dashed and carry
 * their own colour, which is what separates "where the market is" from "where
 * the book says it should stall".
 *
 * Every chip is pinned to its own horizontal band by `slot`. Left to ECharts
 * they all render at the top of the plot, and on a real chain the flip, the
 * cross and spot land within a few tens of points of each other — three chips
 * overprinting into an unreadable smear, which is exactly what the reference
 * screenshot does.
 */
function markers(input: GammaExposureInput, theme: ChartTheme) {
  const { bars, spot, markers: levels, layout } = input;
  const vertical = layout === 'vertical';
  const strikes = bars.map((bar) => bar.strike);
  const lines: Record<string, unknown>[] = [];

  if (strikes.length === 0) return { silent: true, symbol: 'none', data: lines };

  const at = (price: number) => {
    const index = priceIndex(strikes, price);
    return vertical ? { yAxis: index } : { xAxis: index };
  };

  if (Number.isFinite(spot) && spot > 0) {
    lines.push({
      ...at(spot),
      lineStyle: { color: theme.axis, type: 'dotted', width: 1.5 },
      label: {
        show: true,
        position: 'end',
        distance: 0,
        formatter: `Spot: ${Math.round(spot)}`,
        color: theme.spotLabelText,
        backgroundColor: theme.spotLabelBg,
        padding: [3, 6],
        borderRadius: 4,
        fontSize: 11
      }
    });
  }

  for (const level of levels) {
    lines.push({
      ...at(level.strike),
      lineStyle: { color: level.color, type: 'dashed', width: 1.5 },
      label: {
        show: true,
        position: 'end',
        // The one thing keeping five chips legible on a narrow strike range.
        distance: level.slot * CHIP_PITCH,
        formatter: `${level.label}: ${Math.round(level.strike)}`,
        color: level.color,
        backgroundColor: theme.spotLabelBg,
        borderColor: level.color,
        borderWidth: 1,
        padding: [3, 6],
        borderRadius: 4,
        fontSize: 11
      }
    });
  }

  return { silent: true, symbol: 'none', data: lines };
}

function tooltip(input: GammaExposureInput, theme: ChartTheme) {
  const { bars, formatGex, callColor, putColor } = input;

  return {
    trigger: 'axis' as const,
    axisPointer: { type: 'shadow' as const },
    appendTo: 'body',
    backgroundColor: theme.tooltipBg,
    borderColor: theme.grid,
    textStyle: { color: theme.tooltipText, fontSize: 12 },
    padding: [8, 12],
    formatter: (params: unknown) => {
      const entries = params as Array<{ dataIndex: number }>;
      const bar = entries.length ? bars[entries[0]!.dataIndex] : undefined;
      if (!bar) return '';
      // Every figure at once, whichever layout asked. The four are read
      // against each other — a net of nearly zero means one thing beside a
      // small total and the opposite beside a large one.
      return `
        <div style="font-weight:700;margin-bottom:4px">Strike: ${bar.strike}</div>
        <div style="color:${callColor}">Call GEX: ${formatGex(bar.callGex)}</div>
        <div style="color:${putColor}">Put GEX: ${formatGex(bar.putGex)}</div>
        <div style="color:${bar.net >= 0 ? callColor : putColor}">Net: ${formatGex(bar.net)}</div>
        <div>Total: ${formatGex(bar.abs)}</div>`;
    }
  };
}
