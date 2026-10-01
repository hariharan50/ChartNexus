import type { EChartsCoreOption } from 'echarts/core';
import type { ChartTheme } from '../theme/types';
import { withAlpha } from '../theme/tokens';

/**
 * One option leg's greek through the session — the Option Greeks panel.
 *
 * A single line on its own scale, drawn twice per page: call on the left, put
 * on the right. Deliberately *not* one chart with two series. A call's delta
 * lives in `0…1` and a put's in `-1…0`; theta and vega differ by less but still
 * differ, and sharing one axis would squash whichever side is smaller into a
 * flat band. Two panels, two scales, same shape of reading — which is how every
 * terminal that shows this draws it.
 *
 * The y axis never includes zero unless the data does (`scale: true`): the
 * question this chart answers is "how did this move through the day", and an
 * axis anchored at zero turns a 14.0 → 16.5 IV session into a motionless line.
 *
 * The last value is marked with a dashed rule and a pill, because the figure a
 * reader wants first is where the leg is *now*, and hunting for the end of a
 * line against a tick scale is a worse way to get it than reading a label.
 */

export interface GreekLineOptions {
  /** Names the pill at the last value, e.g. `CE IV`. */
  label: string;
  /** The side's colour — call green or put red, from the theme. */
  color: string;
  /** Aligned with `values`; ISO UTC instants. */
  timestamps: string[];
  /** `null` wherever the leg was unquoted, which draws as a gap. */
  values: (number | null)[];
  formatValue: (value: number) => string;
  formatTime: (iso: string) => string;
}

export function buildGreekLineOption(
  options: GreekLineOptions,
  theme: ChartTheme
): EChartsCoreOption {
  const { label, color, timestamps, values, formatValue, formatTime } = options;
  const latest = lastDefined(values);

  return {
    backgroundColor: 'transparent',
    animation: false,
    // Right-hand axis labels sit inside the grid's own padding; the extra right
    // margin is for the value pill, which hangs off the end of the plot.
    grid: { left: 8, right: 64, top: 16, bottom: 8, containLabel: true },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'line', lineStyle: { color: theme.axis, width: 1 } },
      backgroundColor: theme.tooltipBg,
      borderWidth: 0,
      textStyle: { color: theme.tooltipText, fontSize: 12 },
      formatter: (params: unknown) => tooltip(params, { label, formatValue, formatTime })
    },
    xAxis: {
      type: 'category',
      data: timestamps,
      boundaryGap: false,
      axisLine: { lineStyle: { color: theme.grid } },
      axisTick: { show: false },
      axisLabel: {
        color: theme.axis,
        fontSize: 11,
        hideOverlap: true,
        formatter: (value: string) => formatTime(value)
      },
      splitLine: { show: true, lineStyle: { color: withAlpha(theme.grid, 0.45) } }
    },
    yAxis: {
      type: 'value',
      // The reading is the movement, not the distance from zero.
      scale: true,
      position: 'right',
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: {
        color: theme.axis,
        fontSize: 11,
        formatter: (value: number) => formatValue(value)
      },
      splitLine: { show: true, lineStyle: { color: withAlpha(theme.grid, 0.45) } }
    },
    series: [
      {
        name: label,
        type: 'line',
        data: values,
        showSymbol: false,
        // A gap is the honest render of a leg nobody quoted; joining across it
        // would draw a straight line through minutes that never happened.
        connectNulls: false,
        lineStyle: { color, width: 1.5 },
        itemStyle: { color },
        ...(latest == null
          ? {}
          : {
              markLine: {
                silent: true,
                symbol: 'none',
                data: [{ yAxis: latest }],
                lineStyle: { color: withAlpha(color, 0.55), type: 'dotted', width: 1 },
                label: {
                  show: true,
                  position: 'end',
                  distance: 2,
                  formatter: formatValue(latest),
                  backgroundColor: color,
                  color: theme.onMarker,
                  padding: [3, 5],
                  borderRadius: 3,
                  fontSize: 11,
                  fontWeight: 700
                }
              }
            })
      }
    ]
  };
}

/** The most recent value that exists, or `null` when the leg never priced. */
export function lastDefined(values: (number | null)[]): number | null {
  for (let index = values.length - 1; index >= 0; index--) {
    const value = values[index];
    if (value != null) return value;
  }
  return null;
}

interface TooltipParts {
  label: string;
  formatValue: (value: number) => string;
  formatTime: (iso: string) => string;
}

function tooltip(params: unknown, parts: TooltipParts): string {
  const rows = Array.isArray(params) ? params : [params];
  const first = rows[0] as { axisValue?: string; value?: number | null } | undefined;
  if (!first) return '';

  const value = first.value;
  const reading = value == null ? 'not quoted' : parts.formatValue(value);
  return `${parts.formatTime(String(first.axisValue ?? ''))}<br/>${parts.label}: <b>${reading}</b>`;
}
