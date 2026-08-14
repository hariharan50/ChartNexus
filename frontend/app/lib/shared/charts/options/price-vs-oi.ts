/**
 * The Future Lab → Price vs OI chart: futures price against total open interest.
 *
 * Pure — already-derived arrays in, an ECharts option out, no fetching or DOM —
 * the same shape as `multi-series.ts`, which this is a two-line sibling of. It
 * shares that file's design decisions (a value x-axis measured in trading minutes
 * so gaps are drawn proportional to real elapsed time; two Y axes because a price
 * in the tens of thousands and an OI count in the crores cannot share a scale)
 * but **reverses the emphasis**: here the price is the subject, drawn solid and
 * bold on the left, and the OI is the context, drawn dotted on the right — the
 * opposite of the Multi OI chart where the coloured OI lines lead.
 */

import { SESSION_OPEN_MIN } from '$shared/formatting/ist-clock';
import type { EChartsCoreOption } from '../echarts-modules';
import type { ChartTheme } from '../theme/types';
import { withAlpha } from '../theme/tokens';

export interface PriceVsOiInput {
  /** ISO timestamps, one per point. The axis derives its own labels. */
  timestamps: string[];
  /** Tradable future price at each point, or `null` where none was recorded. */
  price: (number | null)[];
  /** Total chain open interest at each point. */
  oi: number[];
  formatPrice: (value: number) => string;
  formatOi: (value: number) => string;
  showPrice: boolean;
  showOi: boolean;
}

/** The price line's colour — the reference's blue, legible in both themes. */
const PRICE_COLOR = '#3b82f6';

/** Blank track past the newest reading, as a share of the plotted span. */
const RIGHT_PAD = 0.06;

const IST = 'Asia/Kolkata';
/** India observes no DST, so a fixed offset is correct and needs no tzdata. */
const IST_OFFSET_MS = 5.5 * 60 * 60 * 1000;
const MINUTE_MS = 60_000;

const clock = new Intl.DateTimeFormat('en-US', {
  timeZone: IST,
  hour: 'numeric',
  minute: '2-digit',
  hour12: true
});

const stamp = new Intl.DateTimeFormat('en-GB', {
  timeZone: IST,
  day: 'numeric',
  month: 'short',
  hour: 'numeric',
  minute: '2-digit',
  hour12: true
});

/** The x value for a point: minutes past the 09:15 IST bell. See multi-series.ts. */
function axisX(ms: number): number {
  const minuteOfDay = ((ms + IST_OFFSET_MS) / MINUTE_MS) % 1440;
  return minuteOfDay - SESSION_OPEN_MIN;
}

/** An axis position back to a clock reading — the inverse of `axisX`. */
function xToClock(x: number): string {
  const base = Date.UTC(2000, 0, 1) - IST_OFFSET_MS;
  return clock.format(base + (SESSION_OPEN_MIN + x) * MINUTE_MS).toLowerCase();
}

/** `13 Aug, 12:16 pm` — a tooltip header, which has to name the day. */
function headerLabel(ms: number): string {
  return stamp.format(ms).toLowerCase();
}

function pointsOf(xs: number[], values: (number | null)[]): [number, number | null][] {
  return xs.map((x, index) => [x, values[index] ?? null]);
}

export function buildPriceVsOiOption(input: PriceVsOiInput, theme: ChartTheme): EChartsCoreOption {
  const { timestamps, price, oi, formatPrice, formatOi, showPrice, showOi } = input;
  const axisName = { color: theme.axis, fontSize: 11, fontWeight: 600 as const };

  const ms = timestamps.map((iso) => Date.parse(iso));
  const xs = ms.map(axisX);
  const first = xs[0] ?? 0;
  const last = xs.at(-1) ?? 0;
  const pad = Math.max((last - first) * RIGHT_PAD, 5);

  const latestPrice = [...price].reverse().find((value) => value != null) ?? null;

  return {
    backgroundColor: 'transparent',
    grid: { left: 8, right: 72, top: 36, bottom: 24, containLabel: true },
    tooltip: {
      trigger: 'axis',
      axisPointer: {
        type: 'line',
        lineStyle: { color: theme.axis, type: 'dashed', width: 1 },
        label: {
          backgroundColor: theme.tooltipBg,
          borderColor: theme.grid,
          borderWidth: 1,
          color: theme.tooltipText,
          formatter: (params: { value: number | string }) => xToClock(Number(params.value))
        }
      },
      formatter: (params: unknown) => tooltipHtml(params, ms, theme, formatPrice, formatOi),
      appendTo: 'body',
      backgroundColor: theme.tooltipBg,
      borderColor: theme.grid,
      textStyle: { color: theme.tooltipText, fontSize: 12 },
      padding: [8, 12]
    },
    xAxis: {
      type: 'value',
      min: first,
      max: last + pad,
      axisLine: { lineStyle: { color: theme.grid } },
      axisTick: { show: false },
      splitLine: { show: true, lineStyle: { color: withAlpha(theme.grid, 0.4), type: 'solid' } },
      axisLabel: {
        color: theme.axis,
        fontSize: 11,
        margin: 12,
        hideOverlap: true,
        formatter: (value: number) => xToClock(value)
      }
    },
    yAxis: [
      {
        type: 'value',
        scale: true,
        position: 'left',
        name: 'Price',
        nameLocation: 'end',
        nameGap: 14,
        nameTextStyle: { ...axisName, align: 'left' },
        axisLine: { show: false },
        axisTick: { show: false },
        splitLine: { lineStyle: { color: theme.grid, type: 'dashed' } },
        axisLabel: { color: theme.axis, fontSize: 11, formatter: formatPrice }
      },
      {
        type: 'value',
        scale: true,
        position: 'right',
        name: 'OI',
        nameLocation: 'end',
        nameGap: 14,
        nameTextStyle: { ...axisName, align: 'right' },
        axisLine: { show: false },
        axisTick: { show: false },
        // Only the price axis draws split lines — two sets at different intervals
        // read as a moiré and neither is followable.
        splitLine: { show: false },
        axisLabel: { color: theme.axis, fontSize: 11, formatter: formatOi }
      }
    ],
    series: [
      ...(showOi ? [oiSeries(xs, oi, theme)] : []),
      ...(showPrice ? [priceSeries(xs, price, latestPrice, theme, formatPrice)] : [])
    ]
  };
}

/** The price line: solid blue, bold, on the left axis — the subject. */
function priceSeries(
  xs: number[],
  values: (number | null)[],
  latest: number | null,
  theme: ChartTheme,
  formatPrice: (value: number) => string
) {
  return {
    id: 'price',
    name: 'Price',
    type: 'line',
    yAxisIndex: 0,
    z: 3,
    data: pointsOf(xs, values),
    showSymbol: false,
    symbol: 'circle',
    symbolSize: 6,
    // Bridges the reconstructed 09:15 frame, which has no recorded price.
    connectNulls: true,
    smooth: false,
    lineStyle: { width: 2, color: PRICE_COLOR },
    itemStyle: { color: PRICE_COLOR },
    ...(latest == null
      ? {}
      : {
          markLine: {
            silent: true,
            symbol: 'none',
            data: [{ yAxis: latest }],
            lineStyle: { color: withAlpha(PRICE_COLOR, 0.35), type: 'dashed', width: 1 },
            label: {
              show: true,
              position: 'end',
              distance: 0,
              formatter: formatPrice(latest),
              backgroundColor: PRICE_COLOR,
              color: '#fff',
              padding: [3, 5],
              borderRadius: 3,
              fontSize: 11,
              fontWeight: 700
            }
          }
        })
  };
}

/** The OI line: dotted, faint, on the right axis — the context. */
function oiSeries(xs: number[], values: number[], theme: ChartTheme) {
  return {
    id: 'oi',
    name: 'OI',
    type: 'line',
    yAxisIndex: 1,
    z: 2,
    data: pointsOf(xs, values),
    showSymbol: false,
    connectNulls: false,
    smooth: false,
    lineStyle: { width: 1.25, type: 'dotted', color: withAlpha(theme.axis, 0.85) },
    emphasis: { disabled: true }
  };
}

/** The tooltip body: a dated header, then a Price and an OI row. */
function tooltipHtml(
  params: unknown,
  ms: number[],
  theme: ChartTheme,
  formatPrice: (value: number) => string,
  formatOi: (value: number) => string
): string {
  const rows = Array.isArray(params) ? params : [params];
  const at = ms[(rows[0] as { dataIndex?: number } | undefined)?.dataIndex ?? -1];
  const head = at == null ? '' : headerLabel(at);

  const body = rows
    .map((row) => {
      const entry = row as {
        seriesId?: string;
        seriesName?: string;
        color?: string;
        value?: [number, number | null];
      };
      const value = entry.value?.[1];
      if (value == null) return '';
      const text = entry.seriesId === 'price' ? formatPrice(value) : formatOi(value);
      const swatch = entry.seriesId === 'price' ? PRICE_COLOR : (entry.color ?? theme.axis);
      return (
        `<div style="display:flex;align-items:center;gap:8px;margin-top:4px">` +
        `<span style="width:8px;height:8px;border-radius:50%;background:${swatch}"></span>` +
        `<span style="flex:1">${entry.seriesName ?? ''}</span>` +
        `<span style="font-weight:700">${text}</span>` +
        `</div>`
      );
    })
    .join('');

  return `<div style="font-weight:700;margin-bottom:2px">${head}</div>${body}`;
}
