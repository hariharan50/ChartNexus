import type { EChartsCoreOption } from '../echarts-modules';
import type { ChartTheme } from '../theme/types';
import { withAlpha } from '../theme/tokens';

/**
 * The intraday multi-contract line chart behind Multi OI & Volume.
 *
 * Pure: takes already-derived arrays and returns an ECharts option. No fetching,
 * no state, no DOM — the same shape as `open-interest.ts`, so both are testable
 * without a canvas.
 *
 * The chart carries two unrelated quantities, which is why it has two Y axes:
 * a price on the left (tens of thousands, moving by tenths of a percent) and an
 * OI or volume figure on the right (millions, moving by tens of percent).
 * Sharing one axis would flatten whichever lost.
 */

/** One plotted contract. `null` marks a point with nothing recorded. */
export interface SeriesLine {
  id: string;
  label: string;
  color: string;
  values: (number | null)[];
}

export interface MultiSeriesInput {
  /** Category labels for the x axis, already formatted for display. */
  times: string[];
  /** The tradable future at each point, or `null` where none was recorded. */
  futures: (number | null)[];
  lines: SeriesLine[];
  /** Formats a right-axis value — OI in lakh/crore, or a lot count. */
  formatValue: (value: number) => string;
  /** Formats the left-axis price. */
  formatPrice: (value: number) => string;
  /** What the right axis measures, e.g. "Open interest". */
  valueAxisName: string;
  /** A horizontal marker on the value axis, e.g. PCR = 1. */
  referenceLine?: { value: number; label: string } | undefined;
  showFutures: boolean;
}

/**
 * Colours a contract keeps everywhere it appears.
 *
 * Assigned by position in the selection, not derived from the strike, so the
 * sidebar chips act as a legend for all three charts at once. Picked to stay
 * apart under both light and dark themes and to avoid the call-green /
 * put-red pair, which mean something else on the Open Interest page.
 */
export const SERIES_PALETTE = [
  '#ec4899',
  '#3b82f6',
  '#eab308',
  '#22c55e',
  '#f97316',
  '#a855f7',
  '#06b6d4',
  '#f43f5e',
  '#84cc16',
  '#8b5cf6'
] as const;

/** The colour for the nth selected contract, wrapping past the palette's end. */
export function seriesColor(index: number): string {
  return SERIES_PALETTE[index % SERIES_PALETTE.length]!;
}

export function buildMultiSeriesOption(
  input: MultiSeriesInput,
  theme: ChartTheme
): EChartsCoreOption {
  const { times, futures, lines, formatValue, formatPrice, valueAxisName } = input;
  const { referenceLine, showFutures } = input;
  const axisName = { color: theme.axis, fontSize: 11, fontWeight: 600 as const };

  return {
    backgroundColor: 'transparent',
    // Generous top and bottom margins. The cramped version had labels touching
    // the plot edge, which is most of what separates a chart that looks
    // considered from one that looks emitted.
    grid: { left: 8, right: 80, top: 36, bottom: 24, containLabel: true },
    tooltip: {
      trigger: 'axis',
      // Biggest first: with five lines crossing each other, reading the tooltip
      // in series order means hunting for the one you are pointing at.
      order: 'valueDesc',
      axisPointer: {
        type: 'line',
        lineStyle: { color: theme.axis, type: 'dashed', width: 1 },
        label: {
          backgroundColor: theme.tooltipBg,
          borderColor: theme.grid,
          borderWidth: 1,
          color: theme.tooltipText
        }
      },
      appendTo: 'body',
      backgroundColor: theme.tooltipBg,
      borderColor: theme.grid,
      textStyle: { color: theme.tooltipText, fontSize: 12 },
      padding: [8, 12]
    },
    xAxis: {
      type: 'category',
      data: times,
      boundaryGap: false,
      axisLine: { lineStyle: { color: theme.grid } },
      axisTick: { show: false },
      axisLabel: {
        color: theme.axis,
        fontSize: 11,
        // Breathing room between the labels and the axis line.
        margin: 12,
        // Let ECharts thin the labels itself; a 375-point session cannot show
        // every one, and forcing `interval: 0` would overprint them.
        hideOverlap: true
      }
    },
    yAxis: [
      {
        type: 'value',
        scale: true,
        position: 'left',
        // Named at the top rather than rotated up the side: a rotated title
        // costs horizontal room the plot needs more, and this chart is wide.
        name: 'Future',
        nameLocation: 'end',
        nameGap: 14,
        nameTextStyle: { ...axisName, align: 'left' },
        axisLine: { show: false },
        axisTick: { show: false },
        // Dashed and faint. Gridlines are for reading a value off, not for
        // looking at, and solid rules compete with the series for attention.
        splitLine: { lineStyle: { color: theme.grid, type: 'dashed' } },
        axisLabel: { color: theme.axis, fontSize: 11, formatter: formatPrice }
      },
      {
        type: 'value',
        scale: true,
        position: 'right',
        name: valueAxisName,
        nameLocation: 'end',
        nameGap: 14,
        nameTextStyle: { ...axisName, align: 'right' },
        axisLine: { show: false },
        axisTick: { show: false },
        // Only the price axis draws split lines. Two sets of horizontal rules at
        // different intervals reads as a moiré and neither is followable.
        splitLine: { show: false },
        axisLabel: { color: theme.axis, fontSize: 11, formatter: formatValue }
      }
    ],
    series: [
      ...(showFutures ? [futuresSeries(futures, theme, formatPrice)] : []),
      ...lines.map((line) => contractSeries(line, formatValue)),
      ...(referenceLine ? [markerSeries(referenceLine, theme)] : [])
    ]
  };
}

/**
 * The price overlay: dashed, thin, and behind everything.
 *
 * Deliberately understated. It is context for the OI lines rather than a
 * reading in its own right, and drawn solid at the same weight it dominates a
 * chart where the coloured series are the subject.
 */
function futuresSeries(
  values: (number | null)[],
  theme: ChartTheme,
  formatPrice: (value: number) => string
) {
  return {
    id: 'futures',
    name: 'Future',
    type: 'line',
    yAxisIndex: 0,
    z: 1,
    data: values,
    showSymbol: false,
    smooth: false,
    // Bridges the gap left by the reconstructed 09:15 frame, which has no
    // recorded price. Breaking the line there would imply the future stopped
    // trading rather than that we started watching late.
    connectNulls: true,
    lineStyle: { width: 1.25, type: 'dashed', color: withAlpha(theme.axis, 0.75) },
    // Never dimmed when another series is hovered: it is the reference every
    // other line is read against, so losing it defeats the isolation.
    emphasis: { disabled: true },
    blur: { lineStyle: { opacity: 0.75 } },
    tooltip: {
      valueFormatter: (value: number | null) => (value == null ? '—' : formatPrice(value))
    }
  };
}

function contractSeries(line: SeriesLine, formatValue: (value: number) => string) {
  return {
    id: line.id,
    name: line.label,
    type: 'line',
    yAxisIndex: 1,
    z: 2,
    data: line.values,
    showSymbol: false,
    // A dot appears under the crosshair, so a reading can be pinpointed without
    // 375 symbols cluttering the line the rest of the time.
    symbol: 'circle',
    symbolSize: 6,
    connectNulls: true,
    // Straight segments, never smoothed. A spline through open-interest points
    // draws values between captures that were never recorded, and the overshoot
    // it invents at a turn is exactly where someone would read a peak.
    smooth: false,
    lineStyle: { width: 2, color: line.color },
    itemStyle: { color: line.color },
    // Hovering one line fades the rest. With five contracts crossing repeatedly
    // this is the difference between a readable chart and a tangle.
    emphasis: { focus: 'series', lineStyle: { width: 3 } },
    blur: { lineStyle: { opacity: 0.15 } },
    // The value tag pinned past the right edge. The latest reading is what
    // anyone reads first on an intraday chart, and hunting for the end of a
    // line among five to find it is the thing this removes.
    endLabel: {
      show: true,
      color: '#fff',
      backgroundColor: line.color,
      padding: [3, 6],
      borderRadius: 3,
      fontSize: 11,
      fontWeight: 600,
      distance: 6,
      formatter: (params: { value: number | null }) =>
        params.value == null ? '' : formatValue(params.value)
    },
    // Contracts that finish close together would otherwise stack their tags on
    // top of each other and none of them would be readable. Nudging them apart
    // vertically keeps every value legible; hiding the overlaps instead would
    // drop exactly the readings a crowded area most needs.
    labelLayout: { moveOverlap: 'shiftY' },
    tooltip: {
      valueFormatter: (value: number | null) => (value == null ? '—' : formatValue(value))
    }
  };
}

/**
 * A horizontal marker on the value axis — PCR = 1, say.
 *
 * Carried by its own empty series rather than hung off a data series, so hiding
 * a line from the legend cannot take the reference with it. The reference is
 * the thing the lines are read *against*; it has to outlive them.
 */
function markerSeries(reference: { value: number; label: string }, theme: ChartTheme) {
  return {
    id: 'reference',
    type: 'line',
    yAxisIndex: 1,
    data: [],
    silent: true,
    markLine: {
      silent: true,
      symbol: 'none',
      data: [{ yAxis: reference.value }],
      lineStyle: { color: withAlpha(theme.marker, 0.7), type: 'dashed', width: 1 },
      label: {
        formatter: reference.label,
        position: 'insideEndTop',
        color: theme.marker,
        fontSize: 10,
        fontWeight: 600
      }
    }
  };
}
