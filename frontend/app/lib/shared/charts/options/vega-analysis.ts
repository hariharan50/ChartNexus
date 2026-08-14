import { SESSION_OPEN_MIN } from '$shared/formatting/ist-clock';
import type { EChartsCoreOption } from '../echarts-modules';
import type { ChartTheme } from '../theme/types';
import { withAlpha } from '../theme/tokens';

/**
 * The intraday chart behind Vega Analysis.
 *
 * A close sibling of `multi-series.ts` (Multi OI & Volume / Put-Call Ratio): the
 * same trading-time value axis and hand-built IST tooltip, and the same dual-axis
 * split — a **Synth Future** price on the left (tens of thousands) and vega on the
 * right (single digits of lakh). It differs in two ways the page needs and the
 * shared builder does not offer: the vega sides fill toward the zero line as areas
 * (the shape the reader tracks is "how far from open"), and a zero reference line
 * anchors that reading. Kept pure — arrays in, an ECharts option out, no fetching
 * or DOM — so the arithmetic is testable without a canvas.
 *
 * **The x axis is elapsed trading time** — minutes past the 09:15 IST bell — so a
 * session that starts recording late draws its gap proportionally rather than as
 * one even step, exactly as the OI-family charts do.
 */

/** One plotted vega series. `null` marks a point with nothing recorded. */
export interface VegaLine {
  id: string;
  label: string;
  color: string;
  values: (number | null)[];
  /** Fill the area between the line and the zero reference. */
  fill?: boolean;
}

export interface VegaChartInput {
  /** ISO timestamps, one per point. The axis derives its own labels. */
  timestamps: string[];
  /** The synthetic future at each point, or `null` where none was recorded. */
  synth: (number | null)[];
  /** Whether the synth-future overlay is drawn. */
  showSynth: boolean;
  /** The vega series on the right axis, in draw order. */
  lines: VegaLine[];
  /** Formats a right-axis vega value. */
  formatValue: (value: number) => string;
  /** Formats the left-axis synth-future price. */
  formatPrice: (value: number) => string;
  /** What the right axis measures, e.g. "Vega (Δ, lakh)". */
  valueAxisName: string;
}

/**
 * Blank track past the newest reading, as a share of the plotted span. A live
 * chart whose last point sits hard against the frame reads as though it has run
 * out rather than as though it is still going.
 */
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

/** The x value for a point: minutes past the 09:15 IST bell. */
function axisX(ms: number): number {
  const minuteOfDay = ((ms + IST_OFFSET_MS) / MINUTE_MS) % 1440;
  return minuteOfDay - SESSION_OPEN_MIN;
}

/** An axis position back to a clock reading — the inverse of `axisX`. */
function xToClock(x: number): string {
  const base = Date.UTC(2000, 0, 1) - IST_OFFSET_MS;
  return clock.format(base + (SESSION_OPEN_MIN + x) * MINUTE_MS).toLowerCase();
}

/** `7 Aug, 9:48 am` — a tooltip header, which has to name the day. */
function headerLabel(ms: number): string {
  return stamp.format(ms).toLowerCase();
}

/** Series data as `[x, value]` against the trading-time axis. */
function pointsOf(xs: number[], values: (number | null)[]): [number, number | null][] {
  return xs.map((x, index) => [x, values[index] ?? null]);
}

export function buildVegaAnalysisOption(
  input: VegaChartInput,
  theme: ChartTheme
): EChartsCoreOption {
  const { timestamps, synth, showSynth, lines, formatValue, formatPrice, valueAxisName } = input;
  const axisName = { color: theme.axis, fontSize: 11, fontWeight: 600 as const };

  const ms = timestamps.map((iso) => Date.parse(iso));
  const xs = ms.map(axisX);
  const first = xs[0] ?? 0;
  const last = xs.at(-1) ?? 0;
  // A single point has no span to take a share of; fall back to a few minutes
  // so the axis still has somewhere to put it.
  const pad = Math.max((last - first) * RIGHT_PAD, 5);

  const latestSynth = [...synth].reverse().find((value) => value != null) ?? null;

  return {
    backgroundColor: 'transparent',
    grid: { left: 8, right: 96, top: 36, bottom: 24, containLabel: true },
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
      formatter: (params: unknown) => tooltipHtml(params, ms, theme, formatValue, formatPrice),
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
        name: 'Synth Future',
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
        name: valueAxisName,
        nameLocation: 'end',
        nameGap: 14,
        nameTextStyle: { ...axisName, align: 'right' },
        axisLine: { show: false },
        axisTick: { show: false },
        splitLine: { show: false },
        axisLabel: { color: theme.axis, fontSize: 11, formatter: formatValue }
      }
    ],
    series: [
      ...(showSynth ? [synthSeries(xs, synth, latestSynth, theme, formatPrice)] : []),
      ...lines.map((line) => vegaSeries(xs, line, formatValue)),
      // The zero line the two deltas are read against. Its own silent series so
      // hiding a vega line from the legend cannot take the reference with it.
      zeroSeries(theme)
    ]
  };
}

/**
 * The tooltip body.
 *
 * Hand-built because the axis carries trading minutes, so the default header
 * would read "153" rather than a clock time. The real instant comes from the
 * point's index, which is also what lets the header carry the date.
 */
function tooltipHtml(
  params: unknown,
  ms: number[],
  theme: ChartTheme,
  formatValue: (value: number) => string,
  formatPrice: (value: number) => string
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
      // The zero reference is drawn as a series so it survives a hidden line; it
      // has no reading of its own and must not print a tooltip row.
      if (entry.seriesId === 'zero') return '';
      const value = entry.value?.[1];
      if (value == null) return '';
      const text = entry.seriesId === 'synth' ? formatPrice(value) : formatValue(value);
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

/**
 * The synth-future overlay: dashed, thin, and behind everything.
 *
 * Context for the vega lines rather than a reading in its own right, so it is
 * never dimmed when another series is hovered — it is the reference every other
 * line is read against.
 */
function synthSeries(
  xs: number[],
  values: (number | null)[],
  latest: number | null,
  theme: ChartTheme,
  formatPrice: (value: number) => string
) {
  return {
    id: 'synth',
    name: 'Synth Future',
    type: 'line',
    yAxisIndex: 0,
    z: 1,
    data: pointsOf(xs, values),
    showSymbol: false,
    smooth: false,
    connectNulls: true,
    lineStyle: { width: 1.25, type: 'dashed', color: withAlpha(theme.axis, 0.75) },
    emphasis: { disabled: true },
    blur: { lineStyle: { opacity: 0.75 } },
    ...(latest == null
      ? {}
      : {
          markLine: {
            silent: true,
            symbol: 'none',
            data: [{ yAxis: latest }],
            lineStyle: { color: withAlpha(theme.axis, 0.25), type: 'dashed', width: 1 },
            label: {
              show: true,
              position: 'start',
              distance: 0,
              formatter: formatPrice(latest),
              backgroundColor: theme.spotLabelBg,
              color: theme.spotLabelText,
              padding: [3, 5],
              borderRadius: 3,
              fontSize: 11,
              fontWeight: 700
            }
          }
        })
  };
}

function vegaSeries(xs: number[], line: VegaLine, formatValue: (value: number) => string) {
  return {
    id: line.id,
    name: line.label,
    type: 'line',
    yAxisIndex: 1,
    z: 2,
    data: pointsOf(xs, line.values),
    showSymbol: false,
    symbol: 'circle',
    symbolSize: 6,
    connectNulls: false,
    smooth: false,
    lineStyle: { width: 2, color: line.color },
    itemStyle: { color: line.color },
    // Fill toward the zero line so the eye reads distance-from-open as area,
    // matching the green/red bands in the reference. `origin: 0` is what pins
    // the base to zero rather than the axis floor.
    ...(line.fill ? { areaStyle: { color: withAlpha(line.color, 0.18), origin: 0 } } : {}),
    emphasis: { focus: 'series', lineStyle: { width: 3 } },
    blur: { lineStyle: { opacity: 0.15 }, areaStyle: { opacity: 0.05 } },
    endLabel: {
      show: true,
      color: '#fff',
      backgroundColor: line.color,
      padding: [3, 6],
      borderRadius: 3,
      fontSize: 11,
      fontWeight: 600,
      distance: 6,
      formatter: (params: { value: [number, number | null] }) =>
        params.value?.[1] == null ? '' : formatValue(params.value[1])
    },
    labelLayout: { moveOverlap: 'shiftY' }
  };
}

/** The zero baseline on the vega axis — the level both deltas are read against. */
function zeroSeries(theme: ChartTheme) {
  return {
    id: 'zero',
    type: 'line',
    yAxisIndex: 1,
    data: [],
    silent: true,
    markLine: {
      silent: true,
      symbol: 'none',
      data: [{ yAxis: 0 }],
      lineStyle: { color: withAlpha(theme.marker, 0.6), type: 'solid', width: 1 },
      label: {
        formatter: '0',
        position: 'insideEndTop',
        color: theme.marker,
        fontSize: 10,
        fontWeight: 600
      }
    }
  };
}
