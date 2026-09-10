import type { EChartsCoreOption } from '../echarts-modules';
import type { ChartTheme } from '../theme/types';

/**
 * At-the-money implied volatility across expiries — the term structure.
 *
 * Pure: takes already-derived points and returns an ECharts option, like its
 * siblings in this folder.
 *
 * **The smallest chart in the folder, and deliberately drawn like one.** Every
 * other builder here plots hundreds of points and hides the individual ones; a
 * term structure is four or five, and it is read *point by point* — "the near
 * one is bid up, the far ones are flat" — not as a shape. So the markers are
 * large and always shown, and each point wears its own value. A bare line
 * between five invisible vertices would leave the reader estimating numbers off
 * an axis that exists to be approximate.
 *
 * **A category axis, not a value axis of dates.** The gaps between listed
 * expiries are uneven — weeklies then monthlies — and spacing them
 * proportionally squashes the near end, which is the end that moves. Days to
 * expiry rides in the axis label instead, so the irregularity is legible
 * without distorting the curve.
 */

export interface TermStructurePoint {
  /** `YYYY-MM-DD`. */
  expiry: string;
  /** Volatility points; `null` where the chain quoted none at the money. */
  atmIv: number | null;
  daysToExpiry: number | null;
}

export interface TermStructureInput {
  points: TermStructurePoint[];
  color: string;
  /** Formats a volatility for the axis, the labels and the tooltip. */
  formatIv: (value: number) => string;
  /** `2026-09-08` → `08 Sep`. */
  formatExpiry: (iso: string) => string;
}

export function buildTermStructureOption(
  input: TermStructureInput,
  theme: ChartTheme
): EChartsCoreOption {
  return {
    backgroundColor: 'transparent',
    // Generous top margin: every point carries a label above it, and the
    // tallest would otherwise be clipped by the plot's own edge.
    grid: { left: 8, right: 24, top: 40, bottom: 8, containLabel: true },
    tooltip: tooltip(input, theme),
    xAxis: {
      type: 'category',
      data: input.points.map((point) => point.expiry),
      boundaryGap: false,
      axisLine: { lineStyle: { color: theme.grid } },
      axisTick: { show: false },
      axisLabel: {
        color: theme.axis,
        fontSize: 11,
        margin: 10,
        formatter: (value: string) => axisLabel(input, value)
      }
    },
    yAxis: {
      type: 'value',
      name: 'ATM IV',
      nameTextStyle: { color: theme.axis, fontSize: 10 },
      // The curve lives in a narrow band well above zero; anchoring the axis
      // there would flatten the very differences the page exists to show.
      scale: true,
      splitLine: { lineStyle: { color: theme.grid, type: 'dashed' } },
      axisLabel: { color: theme.axis, fontSize: 11, formatter: input.formatIv }
    },
    series: [
      {
        name: 'ATM IV',
        type: 'line',
        data: input.points.map((point) => point.atmIv),
        symbol: 'circle',
        symbolSize: 8,
        showSymbol: true,
        smooth: false,
        // An expiry nobody priced breaks the curve rather than being bridged:
        // a straight line drawn through a missing expiry is an interpolation
        // the reader would have no way to see.
        connectNulls: false,
        lineStyle: { color: input.color, width: 2 },
        itemStyle: { color: input.color },
        label: {
          show: true,
          position: 'top' as const,
          formatter: (params: { value?: unknown }) =>
            typeof params.value === 'number' ? input.formatIv(params.value) : '',
          color: theme.axis,
          fontSize: 11,
          fontWeight: 600 as const
        },
        emphasis: { focus: 'series' as const },
        z: 3
      }
    ]
  };
}

/** `08 Sep` over `5d` — the date, and how long is left on it. */
function axisLabel(input: TermStructureInput, expiry: string): string {
  const point = input.points.find((entry) => entry.expiry === expiry);
  const label = input.formatExpiry(expiry);
  return point?.daysToExpiry == null ? label : `${label}\n${point.daysToExpiry}d`;
}

function tooltip(input: TermStructureInput, theme: ChartTheme) {
  return {
    trigger: 'axis' as const,
    axisPointer: { type: 'line' as const, lineStyle: { color: theme.axis, type: 'dotted' } },
    backgroundColor: theme.tooltipBg,
    borderWidth: 0,
    textStyle: { color: theme.tooltipText, fontSize: 12 },
    formatter: (params: unknown) => {
      const list = Array.isArray(params) ? params : [params];
      const index = (list[0] as { dataIndex?: number } | undefined)?.dataIndex;
      if (index === undefined) return '';
      const point = input.points[index];
      if (!point) return '';
      return tooltipHtml(input, point);
    }
  };
}

export function tooltipHtml(input: TermStructureInput, point: TermStructurePoint): string {
  const days =
    point.daysToExpiry === null
      ? ''
      : `<div style="opacity:0.7;font-size:11px">${point.daysToExpiry} days to expiry</div>`;
  const value = point.atmIv === null ? '—' : input.formatIv(point.atmIv);

  return (
    `<div style="font-weight:700;margin-bottom:4px">${input.formatExpiry(point.expiry)}</div>` +
    days +
    `<div style="display:flex;align-items:center;gap:6px;line-height:1.6;margin-top:4px">` +
    `<span style="display:inline-block;width:8px;height:8px;border-radius:2px;background:${input.color}"></span>` +
    `<span style="flex:1">ATM IV:</span><b>${value}</b></div>`
  );
}
