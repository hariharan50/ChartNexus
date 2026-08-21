import { SESSION_OPEN_MIN } from '$shared/formatting/ist-clock';
import type { EChartsCoreOption } from '../echarts-modules';
import type { ChartTheme } from '../theme/types';
import { withAlpha } from '../theme/tokens';

/**
 * The intraday multi-contract line chart behind Multi OI & Volume and the
 * Put-Call Ratio tool.
 *
 * Pure: takes already-derived arrays and returns an ECharts option. No fetching,
 * no state, no DOM — the same shape as `open-interest.ts`, so both are testable
 * without a canvas.
 *
 * **The x axis is elapsed trading time.** It was a category axis fed
 * pre-formatted clock strings, which meant ECharts had no idea when any point
 * actually was and spaced them all equally. A session that starts recording at
 * 09:48 draws a reconstructed 09:15 baseline and its first real capture 33
 * minutes apart — and on a category axis that gap rendered exactly as wide as
 * the 3-minute step beside it. The result read as a straight ramp into a flat
 * line: a shape the market never made.
 *
 * So the axis measures *minutes past the 09:15 bell*: spacing is proportional to
 * real elapsed time, which is the property the category axis lost, and the scale
 * is the session rather than the viewer's day.
 *
 * The chart carries two unrelated quantities, which is why it has two Y axes:
 * a price on the left (tens of thousands, moving by tenths of a percent) and an
 * OI or volume figure on the right (millions, moving by tens of percent).
 * Sharing one axis would flatten whichever lost. This is a deliberate exception
 * to the usual rule against dual axes — the two are read together and neither is
 * a proxy for the other.
 */

/** One plotted contract. `null` marks a point with nothing recorded. */
export interface SeriesLine {
  id: string;
  label: string;
  color: string;
  values: (number | null)[];
  /**
   * Fill the area under the line, faintly, in its own colour.
   *
   * Opt-in and off by default: the OI and PCR charts stack several lines that
   * would smother each other as areas, but a single subject line — the ATM
   * straddle — reads better as a filled band, which is what the reference draws.
   */
  fill?: boolean;
}

export interface MultiSeriesInput {
  /** ISO timestamps, one per point. The axis derives its own labels. */
  timestamps: string[];
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
  /**
   * Give the plot the width back on a narrow panel.
   *
   * The default margins are sized for a chart that owns most of the page. In a
   * side column they are ruinous: the fixed right gutter plus `containLabel`'s
   * own allowance reserved ~140px of a 446px chart — a third of it blank — and
   * the end-of-line value pills, which are drawn outward from the plot edge,
   * landed on top of the axis labels on their way into it.
   *
   * Compact mode shrinks that gutter to just the pill's own breathing room,
   * trusting `containLabel` to add whatever the axis's tick labels need on top
   * rather than budgeting for both. The full-size gutter budgeted for both and
   * left most of a narrow side chart blank.
   */
  compact?: boolean | undefined;
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

/**
 * Blank track past the newest reading, as a share of the plotted span.
 *
 * A live chart whose last point sits hard against the frame reads as though it
 * has run out rather than as though it is still going.
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

/**
 * The x value for a point: minutes past the 09:15 IST bell.
 *
 * Fractional, and deliberately neither floored nor clamped. Both of those
 * mapped *distinct* captures onto an identical x, and an axis-triggered tooltip
 * reports every series value sharing the hovered x — so each collision added
 * another row per contract. Flooring collided any two captures inside the same
 * minute, which a 60-second ingest cadence makes routine; clamping piled every
 * reading past the session end onto one position, which is how ten minutes of
 * post-15:30 captures became a tooltip the height of the screen once the F&O
 * close moved to 15:40 and this file still said 375.
 *
 * Out-of-session instants are left where they fall rather than pinned to the
 * edge: the capture worker does not run outside market hours, so the case is
 * hypothetical, and a point drawn slightly past the bell is a smaller lie than
 * several points drawn on top of each other.
 */
function axisX(ms: number): number {
  const minuteOfDay = ((ms + IST_OFFSET_MS) / MINUTE_MS) % 1440;
  return minuteOfDay - SESSION_OPEN_MIN;
}

/** An axis position back to a clock reading — the inverse of `axisX`. */
function xToClock(x: number): string {
  // Any date works; only the time-of-day is rendered.
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

export function buildMultiSeriesOption(
  input: MultiSeriesInput,
  theme: ChartTheme
): EChartsCoreOption {
  const { timestamps, futures, lines, formatValue, formatPrice, valueAxisName } = input;
  const { referenceLine, showFutures, compact } = input;
  const axisName = { color: theme.axis, fontSize: 11, fontWeight: 600 as const };

  const ms = timestamps.map((iso) => Date.parse(iso));
  const xs = ms.map(axisX);
  const first = xs[0] ?? 0;
  const last = xs.at(-1) ?? 0;
  // A single point has no span to take a share of; fall back to a few minutes
  // so the axis still has somewhere to put it.
  const pad = Math.max((last - first) * RIGHT_PAD, 5);

  const latestFuture = [...futures].reverse().find((value) => value != null) ?? null;

  return {
    backgroundColor: 'transparent',
    // Generous top and bottom margins. The cramped version had labels touching
    // the plot edge, which is most of what separates a chart that looks
    // considered from one that looks emitted.
    //
    // `right` is wide enough for a value pill plus the price it holds: at 80 the
    // tags for contracts finishing close together were shunted into each other
    // and neither could be read. `containLabel` already reserves whatever room
    // the right axis's own tick labels need on top of this, so compact panels
    // only have to budget the pill's own breathing room here — not the labels
    // again, which is what left a third of a narrow side chart blank.
    grid: {
      left: 8,
      right: compact ? 16 : 96,
      top: compact ? 28 : 36,
      bottom: 24,
      containLabel: true
    },
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
          color: theme.tooltipText,
          // The axis holds trading minutes, so left alone the pointer would
          // label itself "412".
          formatter: (params: { value: number | string }) => xToClock(Number(params.value))
        }
      },
      // Hand-built: the default heads the tooltip with the raw axis number,
      // which here is a count of trading minutes.
      formatter: (params: unknown) => tooltipHtml(params, ms, theme, formatValue, formatPrice),
      appendTo: 'body',
      backgroundColor: theme.tooltipBg,
      borderColor: theme.grid,
      textStyle: { color: theme.tooltipText, fontSize: 12 },
      padding: [8, 12]
    },
    xAxis: {
      // A value axis of trading minutes, not `time`: the scale is the session,
      // so a pre-open or post-close instant cannot stretch it.
      type: 'value',
      min: first,
      // Blank track past the newest point — see RIGHT_PAD.
      max: last + pad,
      axisLine: { lineStyle: { color: theme.grid } },
      axisTick: { show: false },
      // Vertical rules as well as horizontal, as the reference has. Faint
      // enough to read time off without competing with the series.
      splitLine: { show: true, lineStyle: { color: withAlpha(theme.grid, 0.4), type: 'solid' } },
      axisLabel: {
        color: theme.axis,
        fontSize: 11,
        // Breathing room between the labels and the axis line.
        margin: 12,
        // Let ECharts thin the labels itself; a 375-point session cannot show
        // every one, and forcing `interval: 0` would overprint them.
        hideOverlap: true,
        formatter: (value: number) => xToClock(value)
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
      ...(showFutures ? [futuresSeries(xs, futures, latestFuture, theme, formatPrice)] : []),
      ...lines.map((line) => contractSeries(xs, line, formatValue)),
      ...(referenceLine ? [markerSeries(referenceLine, theme)] : [])
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
      const value = entry.value?.[1];
      if (value == null) return '';
      const text = entry.seriesId === 'futures' ? formatPrice(value) : formatValue(value);
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
 * The price overlay: dashed, thin, and behind everything.
 *
 * Deliberately understated. It is context for the OI lines rather than a
 * reading in its own right, and drawn solid at the same weight it dominates a
 * chart where the coloured series are the subject.
 */
function futuresSeries(
  xs: number[],
  values: (number | null)[],
  latest: number | null,
  theme: ChartTheme,
  formatPrice: (value: number) => string
) {
  return {
    id: 'futures',
    name: 'Future',
    type: 'line',
    yAxisIndex: 0,
    z: 1,
    data: pointsOf(xs, values),
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
    // The current price, pinned to the left axis it belongs to. The contract
    // pills sit on the right against a different scale, and a reader following
    // the dashed line has nowhere else to find the number it is at.
    ...(latest == null
      ? {}
      : {
          markLine: {
            silent: true,
            symbol: 'none',
            data: [{ yAxis: latest }],
            // Faint rather than invisible: a fully transparent line takes its
            // own label out of the render with it, and the label is the point.
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

function contractSeries(xs: number[], line: SeriesLine, formatValue: (value: number) => string) {
  return {
    id: line.id,
    name: line.label,
    type: 'line',
    yAxisIndex: 1,
    z: 2,
    data: pointsOf(xs, line.values),
    showSymbol: false,
    // A dot appears under the crosshair, so a reading can be pinpointed without
    // 375 symbols cluttering the line the rest of the time.
    symbol: 'circle',
    symbolSize: 6,
    // Leading nulls are *not* bridged: a leg listed only today has no value
    // yesterday, and connecting across would draw it flat at zero and then leap.
    // ECharts starts the line at the first real point, which is what we want.
    connectNulls: false,
    // Straight segments, never smoothed. A spline through open-interest points
    // draws values between captures that were never recorded, and the overshoot
    // it invents at a turn is exactly where someone would read a peak.
    smooth: false,
    lineStyle: { width: 2, color: line.color },
    itemStyle: { color: line.color },
    // A faint fill under the line when the caller asks for one. Left off the
    // object entirely otherwise, so a stack of lines is never quietly banded.
    ...(line.fill ? { areaStyle: { color: withAlpha(line.color, 0.18) } } : {}),
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
      formatter: (params: { value: [number, number | null] }) =>
        params.value?.[1] == null ? '' : formatValue(params.value[1])
    },
    // Contracts that finish close together would otherwise stack their tags on
    // top of each other and none of them would be readable. Nudging them apart
    // vertically keeps every value legible; hiding the overlaps instead would
    // drop exactly the readings a crowded area most needs.
    labelLayout: { moveOverlap: 'shiftY' }
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
      // Red rather than the marker amber. `--mc-warning` is tuned to sit on a
      // dark surface; on the light and warm themes a 70%-alpha amber hairline
      // all but disappeared, and a reference line nobody can see is worse than
      // no reference line — every ratio on the chart is read against it.
      lineStyle: { color: withAlpha(theme.put, 0.7), type: 'dashed', width: 1 },
      label: {
        formatter: reference.label,
        position: 'insideEndTop',
        color: theme.put,
        fontSize: 10,
        fontWeight: 600
      }
    }
  };
}
