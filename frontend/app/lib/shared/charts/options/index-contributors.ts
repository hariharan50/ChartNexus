import type { EChartsCoreOption } from '../echarts-modules';
import type { ChartTheme } from '../theme/types';

/**
 * Who moved the index, in index points.
 *
 * A **diverging horizontal bar**: the quantity has a meaningful zero (a name
 * either pushed the index up or dragged it down), the labels are tickers that
 * read left-to-right, and the ranking is the whole message. Vertical bars with
 * rotated ticker labels would say the same thing worse.
 *
 * Two hues and a real zero line, never a single-hue ramp — direction is the
 * primary reading here and a sequential scale would make "up a lot" and "down
 * a lot" the two ends of one colour.
 *
 * The bars are not the *only* carrier of sign: every bar is directly labelled
 * with its signed point figure, so the chart survives being printed in grey,
 * read by someone with a colour-vision deficiency, or glanced at from across a
 * desk. That is also why no legend is needed — the two colours are up and down,
 * which the axis and the labels already say.
 */

export interface ContributionBar {
  symbol: string;
  points: number;
  changePercent: number;
  weightPercent: number;
}

export interface ContributorsOptions {
  /** Formats an index-point figure for the labels and the tooltip. */
  formatPoints: (value: number) => string;
  formatPercent: (value: number) => string;
}

export function buildContributorsOption(
  bars: ContributionBar[],
  theme: ChartTheme,
  options: ContributorsOptions
): EChartsCoreOption {
  const { formatPoints, formatPercent } = options;
  // Largest push at the top: a horizontal category axis runs bottom-up, so the
  // data is reversed to put the leader where the eye lands first.
  const ordered = [...bars].reverse();

  return {
    backgroundColor: 'transparent',
    // Room on the right for the direct labels, which sit outside the bar ends.
    grid: { left: 8, right: 64, top: 8, bottom: 8, containLabel: true },
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
          <div style="font-weight:700;margin-bottom:4px">${bar.symbol}</div>
          <div>Contribution: ${formatPoints(bar.points)} pts</div>
          <div>Move: ${formatPercent(bar.changePercent)}</div>
          <div>Weight: ${bar.weightPercent.toFixed(2)}%</div>`;
      }
    },
    xAxis: {
      type: 'value',
      splitLine: { lineStyle: { color: theme.grid, type: 'dashed' } },
      axisLabel: { color: theme.axis, fontSize: 11, formatter: formatPoints }
    },
    yAxis: {
      type: 'category',
      data: ordered.map((bar) => bar.symbol),
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: theme.axis, fontSize: 11 }
    },
    series: [
      {
        type: 'bar',
        data: ordered.map((bar) => ({
          value: bar.points,
          itemStyle: {
            color: bar.points >= 0 ? theme.call : theme.put,
            // Rounded only at the data end, anchored square to the zero line.
            borderRadius: bar.points >= 0 ? [0, 4, 4, 0] : [4, 0, 0, 4]
          },
          // Per item, not per series: ECharts takes a fixed string for label
          // position, and a negative bar's label has to sit on its *left* or
          // it lands on top of the zero line it is pointing away from.
          label: { position: bar.points >= 0 ? 'right' : 'left' }
        })),
        barMaxWidth: 16,
        label: {
          show: true,
          color: theme.axis,
          fontSize: 11,
          formatter: (params: { value: number }) => formatPoints(params.value)
        },
        markLine: {
          silent: true,
          symbol: 'none',
          // The zero line is the axis this chart is read against; the default
          // split line is too faint to serve as one.
          data: [{ xAxis: 0 }],
          lineStyle: { color: theme.axis, width: 1 },
          label: { show: false }
        }
      }
    ]
  };
}
