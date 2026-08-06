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
  const { times, futures, lines, formatValue, formatPrice, showFutures } = input;

  return {
    backgroundColor: 'transparent',
    // Room on the right for the end labels; they sit outside the plot area and
    // are the whole point of the layout, so the grid has to yield to them.
    grid: { left: 8, right: 76, top: 16, bottom: 8, containLabel: true },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'line', lineStyle: { color: theme.axis, type: 'dashed' } },
      appendTo: 'body',
      backgroundColor: theme.tooltipBg,
      borderColor: theme.grid,
      textStyle: { color: theme.tooltipText, fontSize: 12 }
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
        splitLine: { lineStyle: { color: theme.grid } },
        axisLabel: { color: theme.axis, fontSize: 11, formatter: formatPrice }
      },
      {
        type: 'value',
        scale: true,
        position: 'right',
        // Only the price axis draws split lines. Two sets of horizontal rules at
        // different intervals reads as a moiré and neither is followable.
        splitLine: { show: false },
        axisLabel: { color: theme.axis, fontSize: 11, formatter: formatValue }
      }
    ],
    series: [
      ...(showFutures ? [futuresSeries(futures, theme, formatPrice)] : []),
      ...lines.map((line) => contractSeries(line, formatValue))
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
    // Bridges the gap left by the reconstructed 09:15 frame, which has no
    // recorded price. Breaking the line there would imply the future stopped
    // trading rather than that we started watching late.
    connectNulls: true,
    lineStyle: { width: 1, type: 'dashed', color: withAlpha(theme.axis, 0.9) },
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
    connectNulls: true,
    lineStyle: { width: 1.5, color: line.color },
    itemStyle: { color: line.color },
    // The value tag pinned past the right edge. The latest reading is what
    // anyone reads first on an intraday chart, and hunting for the end of a
    // line among five to find it is the thing this removes.
    endLabel: {
      show: true,
      color: '#fff',
      backgroundColor: line.color,
      padding: [2, 4],
      borderRadius: 2,
      fontSize: 11,
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
