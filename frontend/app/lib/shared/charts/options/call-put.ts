/**
 * The call-vs-put comparison charts behind Price vs OI (Price, OI, OI Change).
 *
 * Pure — derived arrays in, an ECharts option out — and a sibling of
 * `price-vs-oi.ts`, whose trading-minute x-axis and dated tooltip it shares. It
 * draws two coloured lines, the call in green and the put in red.
 *
 * Two of the three charts plot a **normalised** value — each leg as a fraction of
 * its own session open — so a call worth 150 and a put worth 90 sit on one
 * centred axis and can be read against each other. The absolute value each leg is
 * actually at is carried alongside and shown in the end-pill and the tooltip,
 * which is the number a trader reads. The OI-Change chart plots raw values on a
 * single axis instead (`normalized: false`). An optional PCR line rides a second
 * axis when the legend toggles it on.
 */

import { SESSION_OPEN_MIN } from '$shared/formatting/ist-clock';
import type { EChartsCoreOption } from '../echarts-modules';
import type { ChartTheme } from '../theme/types';
import { withAlpha } from '../theme/tokens';

/** One leg: the values plotted, and the absolute values shown to the reader. */
export interface CallPutLeg {
  /** What the line is drawn from — normalised fraction, or the raw value. */
  plot: (number | null)[];
  /** The absolute price/OI, for the end-pill and tooltip. */
  abs: (number | null)[];
  name: string;
  color: string;
}

export interface CallPutInput {
  timestamps: string[];
  ce: CallPutLeg;
  pe: CallPutLeg;
  /** Left axis is a percentage (normalised) rather than a raw value. */
  normalized: boolean;
  /** Formats an absolute value — the price or the OI. */
  formatAbs: (value: number) => string;
  showCe: boolean;
  showPe: boolean;
  /** The optional PCR overlay: a dotted line on its own right axis. */
  pcr?: { values: (number | null)[]; show: boolean; format: (value: number) => string } | undefined;
  /** Wheel-to-zoom and drag-to-pan the time axis, synced across the group. */
  zoomable?: boolean | undefined;
  /** Show only the last N trading minutes; undefined spans the whole session. */
  windowMinutes?: number | undefined;
}

/** The shared time-axis zoom — Shift+wheel to zoom, drag to pan. See price-vs-oi.ts. */
const TIME_ZOOM = [
  {
    type: 'inside' as const,
    filterMode: 'none' as const,
    zoomOnMouseWheel: 'shift' as const,
    moveOnMouseMove: true,
    moveOnMouseWheel: false
  }
];

// A hair of blank track past the newest point — just enough that the end-pill
// floats clear of the frame, no dead gutter.
const RIGHT_PAD = 0.008;
const IST = 'Asia/Kolkata';
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

function axisX(ms: number): number {
  const minuteOfDay = ((ms + IST_OFFSET_MS) / MINUTE_MS) % 1440;
  return minuteOfDay - SESSION_OPEN_MIN;
}
function xToClock(x: number): string {
  const base = Date.UTC(2000, 0, 1) - IST_OFFSET_MS;
  return clock.format(base + (SESSION_OPEN_MIN + x) * MINUTE_MS).toLowerCase();
}
function headerLabel(ms: number): string {
  return stamp.format(ms).toLowerCase();
}
function pointsOf(xs: number[], values: (number | null)[]): [number, number | null][] {
  return xs.map((x, index) => [x, values[index] ?? null]);
}

/** A signed percentage, e.g. `+12.4%`, for the normalised axis. */
function pct(value: number): string {
  return `${value >= 0 ? '+' : ''}${(value * 100).toFixed(0)}%`;
}

export function buildCallPutOption(input: CallPutInput, theme: ChartTheme): EChartsCoreOption {
  const { timestamps, ce, pe, normalized, formatAbs, showCe, showPe, pcr } = input;
  const axisName = { color: theme.axis, fontSize: 11, fontWeight: 600 as const };
  const withPcr = Boolean(pcr?.show);

  const ms = timestamps.map((iso) => Date.parse(iso));
  const xs = ms.map(axisX);
  const first = xs[0] ?? 0;
  const last = xs.at(-1) ?? 0;
  const pad = Math.max((last - first) * RIGHT_PAD, 2);
  // The left edge: the whole session, or the last N trading minutes.
  const min = input.windowMinutes != null ? Math.max(first, last - input.windowMinutes) : first;

  // The right gutter holds only the end-pills, so size it to the actual pill
  // text — a 3-digit price needs far less than a "62.84L" OI. Fixed at 72 it
  // left a wide band of dead space beside the small price pills.
  const latestOf = (values: (number | null)[]) =>
    [...values].reverse().find((value) => value != null) ?? null;
  const lce = latestOf(ce.abs);
  const lpe = latestOf(pe.abs);
  const pillChars = Math.max(
    lce != null ? formatAbs(lce).length : 0,
    lpe != null ? formatAbs(lpe).length : 0,
    3
  );
  // ~6.5px a glyph + the pill padding and its offset. With the PCR axis shown
  // there is nothing to reserve: the pills move inside the frame (they would
  // otherwise overprint the PCR tick labels), and `containLabel` covers those
  // labels itself.
  const rightGutter = withPcr ? 12 : Math.min(54, Math.round(pillChars * 6.5) + 12);

  const yAxes: Record<string, unknown>[] = [
    {
      type: 'value',
      scale: true,
      position: 'left',
      name: normalized ? 'vs Open' : 'Value',
      nameLocation: 'end',
      nameGap: 14,
      nameTextStyle: { ...axisName, align: 'left' },
      axisLine: { show: false },
      axisTick: { show: false },
      splitLine: { lineStyle: { color: theme.grid, type: 'dashed' } },
      axisLabel: {
        color: theme.axis,
        fontSize: 11,
        formatter: (value: number) => (normalized ? pct(value) : formatAbs(value))
      }
    }
  ];
  if (withPcr) {
    yAxes.push({
      type: 'value',
      scale: true,
      position: 'right',
      name: 'PCR',
      nameLocation: 'end',
      nameGap: 14,
      nameTextStyle: { ...axisName, align: 'right' },
      axisLine: { show: false },
      axisTick: { show: false },
      splitLine: { show: false },
      axisLabel: { color: theme.axis, fontSize: 11, formatter: pcr!.format }
    });
  }

  const series: Record<string, unknown>[] = [];
  if (showCe) series.push(legSeries('ce', xs, ce, formatAbs, withPcr));
  if (showPe) series.push(legSeries('pe', xs, pe, formatAbs, withPcr));
  if (withPcr) series.push(pcrSeries(xs, pcr!.values, theme));

  return {
    backgroundColor: 'transparent',
    ...(input.zoomable ? { dataZoom: TIME_ZOOM } : {}),
    // Trimmed to the minimum each edge needs — the pills (and the PCR axis when
    // shown) on the right, the tick labels elsewhere via `containLabel` — so the
    // plot itself takes the whole panel rather than sitting in a frame of gutter.
    grid: { left: 2, right: rightGutter, top: 16, bottom: 14, containLabel: true },
    tooltip: {
      trigger: 'axis',
      order: 'valueDesc',
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
        tooltipHtml(params, ms, theme, { ce, pe }, formatAbs, pcr?.format),
      appendTo: 'body',
      backgroundColor: theme.tooltipBg,
      borderColor: theme.grid,
      textStyle: { color: theme.tooltipText, fontSize: 12 },
      padding: [8, 12]
    },
    xAxis: {
      type: 'value',
      min,
      max: last + pad,
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
    yAxis: yAxes,
    series
  };
}

/** One leg's line, drawn from `plot`, its end-pill reading the absolute value. */
function legSeries(
  id: 'ce' | 'pe',
  xs: number[],
  leg: CallPutLeg,
  formatAbs: (value: number) => string,
  /** Draw the pill inside the frame — the PCR axis owns the space outside it. */
  pillInside: boolean
) {
  return {
    id,
    name: leg.name,
    type: 'line',
    yAxisIndex: 0,
    z: 2,
    data: pointsOf(xs, leg.plot),
    showSymbol: false,
    symbol: 'circle',
    symbolSize: 6,
    connectNulls: false,
    smooth: false,
    lineStyle: { width: 2, color: leg.color },
    itemStyle: { color: leg.color },
    emphasis: { focus: 'series', lineStyle: { width: 3 } },
    blur: { lineStyle: { opacity: 0.2 } },
    // The pill shows the ABSOLUTE value at the last point, not the plotted
    // normalised fraction — the number the trader reads.
    endLabel: {
      show: true,
      color: '#fff',
      backgroundColor: leg.color,
      padding: [2, 5],
      borderRadius: 3,
      fontSize: 10,
      fontWeight: 600,
      // Anchored at the last point: hanging off it by default, tucked back
      // inside the frame when the right axis needs the outside.
      ...(pillInside ? { align: 'right' as const, distance: -4 } : { distance: 4 }),
      formatter: (params: { dataIndex: number }) => {
        const value = leg.abs[params.dataIndex];
        return value == null ? '' : formatAbs(value);
      }
    },
    labelLayout: { moveOverlap: 'shiftY' }
  };
}

/** The PCR overlay: dotted, faint, on the right axis — the context. */
function pcrSeries(xs: number[], values: (number | null)[], theme: ChartTheme) {
  return {
    id: 'pcr',
    name: 'PCR',
    type: 'line',
    yAxisIndex: 1,
    z: 1,
    data: pointsOf(xs, values),
    showSymbol: false,
    connectNulls: false,
    smooth: false,
    lineStyle: { width: 1.25, type: 'dotted', color: withAlpha(theme.axis, 0.85) },
    emphasis: { disabled: true }
  };
}

function tooltipHtml(
  params: unknown,
  ms: number[],
  theme: ChartTheme,
  legs: { ce: CallPutLeg; pe: CallPutLeg },
  formatAbs: (value: number) => string,
  formatPcr: ((value: number) => string) | undefined
): string {
  const rows = Array.isArray(params) ? params : [params];
  const index = (rows[0] as { dataIndex?: number } | undefined)?.dataIndex ?? -1;
  const at = ms[index];
  const head = at == null ? '' : headerLabel(at);

  const body = rows
    .map((row) => {
      const entry = row as {
        seriesId?: string;
        seriesName?: string;
        color?: string;
        value?: [number, number | null];
      };
      let text: string;
      if (entry.seriesId === 'ce') text = fmtOrDash(legs.ce.abs[index] ?? null, formatAbs);
      else if (entry.seriesId === 'pe') text = fmtOrDash(legs.pe.abs[index] ?? null, formatAbs);
      else if (entry.seriesId === 'pcr')
        text = fmtOrDash(entry.value?.[1] ?? null, formatPcr ?? formatAbs);
      else return '';
      return (
        `<div style="display:flex;align-items:center;gap:8px;margin-top:4px">` +
        `<span style="width:8px;height:8px;border-radius:50%;background:${entry.color ?? theme.axis}"></span>` +
        `<span style="flex:1">${entry.seriesName ?? ''}</span>` +
        `<span style="font-weight:700">${text}</span>` +
        `</div>`
      );
    })
    .join('');

  return `<div style="font-weight:700;margin-bottom:2px">${head}</div>${body}`;
}

function fmtOrDash(value: number | null, format: (value: number) => string): string {
  return value == null ? '—' : format(value);
}
