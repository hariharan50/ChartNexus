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
  /** The context line at each point — open interest, or a ratio. `null` breaks it. */
  oi: (number | null)[];
  formatPrice: (value: number) => string;
  formatOi: (value: number) => string;
  showPrice: boolean;
  showOi: boolean;
  /**
   * The solid line's colour and the two axis names.
   *
   * The Future-Lab chart this began as is always a blue future against total OI;
   * the strike-centric Price vs OI tool reuses the same shape for a green CE
   * price / dotted CE OI, a red PE, and a blue straddle against a dotted PCR, so
   * the subject colour and both axis titles are caller-supplied. Left undefined
   * they fall back to the original blue "Price" / "OI".
   */
  priceColor?: string | undefined;
  priceName?: string | undefined;
  oiName?: string | undefined;
  /**
   * Wheel-to-zoom and drag-to-pan the time axis.
   *
   * Off by default so the single Future-Lab chart is unchanged; the Price vs OI
   * grid turns it on and, because those panels share an `echarts.connect` group,
   * zooming one zooms them all to the same window.
   */
  zoomable?: boolean | undefined;
  /**
   * Show only the last N trading minutes, instead of the whole session.
   *
   * The visible time window the Price vs OI range chips set. Left undefined the
   * axis spans the full session; a number clamps the left edge to `now - N`,
   * which in Live mode auto-scrolls forward as captures arrive.
   */
  windowMinutes?: number | undefined;
}

/**
 * The shared time-axis zoom: Shift+wheel to zoom, drag to pan, no data dropped.
 *
 * Shift-gated on purpose — the Price vs OI grid is a tall, scrolling page, so a
 * plain wheel has to keep scrolling it rather than being swallowed to zoom the
 * chart under the pointer.
 */
/**
 * The time-axis zoom: wheel over the plot to scale the window, drag inside it to
 * pan, and drag the clock strip under the plot to stretch or squeeze the window
 * against its right edge (see `installAxisDrag` in `use-echart.ts`).
 *
 * The wheel zooms without a modifier. It used to need Shift — safer on a page of
 * six stacked charts, since a plain wheel over one of them no longer scrolls the
 * page — but a modifier nobody discovers is the same as no zoom at all, and this
 * is how every charting tool a trader already uses behaves. The page still
 * scrolls from the gaps, the headers and the sidebar; only the plot rectangle
 * itself takes the wheel.
 *
 * `filterMode: 'none'`: zooming must scale the axis, never drop the points
 * outside it, or the lines would be redrawn from a truncated series and their
 * ends would move as you zoom.
 */
function timeZoom(window: { start: number; end: number }) {
  return [
    {
      type: 'inside' as const,
      filterMode: 'none' as const,
      // Both charts carry two y axes; left to guess, the zoom binds the wrong
      // one and the wheel moves nothing.
      xAxisIndex: 0,
      startValue: window.start,
      endValue: window.end,
      zoomOnMouseWheel: true,
      moveOnMouseMove: true,
      moveOnMouseWheel: false,
      // Otherwise a drag-to-pan also selects the page text around the chart.
      preventDefaultMouseMove: true
    }
  ];
}

/** The default line colour — the reference's blue, legible in both themes. */
const PRICE_COLOR = '#3b82f6';

/** A hair of blank track past the newest reading — the pill floats clear, no gutter. */
const RIGHT_PAD = 0.008;

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
  const priceColor = input.priceColor ?? PRICE_COLOR;
  const priceName = input.priceName ?? 'Price';
  const oiName = input.oiName ?? 'OI';
  const axisName = { color: theme.axis, fontSize: 11, fontWeight: 600 as const };

  const ms = timestamps.map((iso) => Date.parse(iso));
  const xs = ms.map(axisX);
  const first = xs[0] ?? 0;
  const last = xs.at(-1) ?? 0;
  const pad = Math.max((last - first) * RIGHT_PAD, 2);
  // The left edge: the whole session, or the last N trading minutes.
  const min = input.windowMinutes != null ? Math.max(first, last - input.windowMinutes) : first;
  const max = last + pad;

  const latestPrice = [...price].reverse().find((value) => value != null) ?? null;

  return {
    backgroundColor: 'transparent',
    ...(input.zoomable ? { dataZoom: timeZoom({ start: min, end: max }) } : {}),
    // The right gutter used to hold the price pill, which hung outside the plot
    // and landed on the OI axis's own tick labels — a left-axis number sitting
    // on the right axis's scale. The pill now sits inside the frame (see
    // `priceSeries`), so all this reserves is the panel's own breathing room;
    // `containLabel` adds the OI labels on top.
    grid: { left: 2, right: 12, top: 16, bottom: 14, containLabel: true },
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
      formatter: (params: unknown) =>
        tooltipHtml(params, ms, theme, priceColor, formatPrice, formatOi),
      appendTo: 'body',
      backgroundColor: theme.tooltipBg,
      borderColor: theme.grid,
      textStyle: { color: theme.tooltipText, fontSize: 12 },
      padding: [8, 12]
    },
    xAxis: {
      type: 'value',
      // Bounded by `dataZoom` when the chart is zoomable, and pinned here when it
      // is not. A pinned axis WINS over `dataZoom`: fixing both is what made the
      // wheel and the axis drag move nothing at all.
      ...(input.zoomable ? {} : { min, max }),
      axisLine: { lineStyle: { color: theme.grid } },
      axisTick: { show: false },
      splitLine: { show: true, lineStyle: { color: withAlpha(theme.grid, 0.4), type: 'solid' } },
      axisLabel: {
        color: theme.axis,
        fontSize: 11,
        margin: 12,
        hideOverlap: true,
        // The first and last labels are pinned inside the axis instead of being
        // centred on their ticks, where half of each hangs past the plot.
        // `containLabel` budgets for that overhang, so a centred end label
        // reserved ~28px of blank panel on each side — on a 2-across grid of six
        // charts that is most of a chart's worth of dead space.
        alignMinLabel: 'left',
        alignMaxLabel: 'right',
        formatter: (value: number) => xToClock(value)
      }
    },
    yAxis: [
      {
        type: 'value',
        scale: true,
        position: 'left',
        name: priceName,
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
        name: oiName,
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
      ...(showOi ? [oiSeries(xs, oi, oiName, theme)] : []),
      ...(showPrice
        ? [priceSeries(xs, price, latestPrice, priceColor, priceName, formatPrice)]
        : [])
    ]
  };
}

/** The price line: solid, bold, on the left axis — the subject. */
function priceSeries(
  xs: number[],
  values: (number | null)[],
  latest: number | null,
  color: string,
  name: string,
  formatPrice: (value: number) => string
) {
  return {
    id: 'price',
    name,
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
    lineStyle: { width: 2, color },
    itemStyle: { color },
    ...(latest == null
      ? {}
      : {
          markLine: {
            silent: true,
            symbol: 'none',
            data: [{ yAxis: latest }],
            lineStyle: { color: withAlpha(color, 0.35), type: 'dashed', width: 1 },
            label: {
              show: true,
              // Inside the frame, above the marker: outside it, the pill
              // overprinted the OI axis's tick labels and forced a wide dead
              // gutter to sit in.
              position: 'insideEndTop',
              distance: 0,
              formatter: formatPrice(latest),
              backgroundColor: color,
              color: '#fff',
              padding: [2, 4],
              borderRadius: 3,
              fontSize: 10,
              fontWeight: 700
            }
          }
        })
  };
}

/** The OI line: dotted, faint, on the right axis — the context. */
function oiSeries(xs: number[], values: (number | null)[], name: string, theme: ChartTheme) {
  return {
    id: 'oi',
    name,
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
  priceColor: string,
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
      const swatch = entry.seriesId === 'price' ? priceColor : (entry.color ?? theme.axis);
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
