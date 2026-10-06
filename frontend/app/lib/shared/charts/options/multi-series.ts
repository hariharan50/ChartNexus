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
  /**
   * Where the fill band closes to on the value axis. Left undefined the area
   * runs to the axis floor (the straddle default); set to `0` for a signed
   * series that should fill toward a zero baseline, so a positive stretch bands
   * upward and a negative one downward — the Premium Decay change chart.
   */
  fillOrigin?: number | undefined;
  /**
   * Colour the line and its fill by sign, switching at zero.
   *
   * For a series whose sign is the headline — a running P&L, where "is it up or
   * down right now" is read off the colour before any number is. One colour for
   * the whole line forces that reading back onto the axis labels, and a curve
   * that crosses zero four times becomes four separate things to check.
   *
   * Pair it with `fillOrigin: 0` so the band closes to the same line the colour
   * turns on.
   */
  signed?: { positive: string; negative: string } | undefined;
  /**
   * Draw as a step rather than a sloped line, holding each value until the
   * next point.
   *
   * For series that only ever take discrete values. Max pain is a *strike*: it
   * sits at 23,400 and then it sits at 23,350, and it was never at 23,380 in
   * between. A sloped segment draws it passing through prices that are not
   * strikes and were never the answer to anything.
   */
  step?: boolean;
  /**
   * Draw the line dotted rather than solid.
   *
   * For a series that is context rather than subject and sits close enough to
   * another to be confused with it — the synthetic forward, which tracks spot
   * within a few points all day. Solid, the two read as one thick line and the
   * gap between them, which is the actual information, disappears.
   */
  dashed?: boolean;
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
   * Extra lines measured in the *price* unit, drawn on the left axis beside
   * the future.
   *
   * `futures` is one line and some charts have two of the same kind: Straddle
   * Chart plots spot and the put-call-parity forward together, both index
   * levels, against a premium on the right. They belong on the price axis
   * because that is the unit they are in — putting them on the value axis
   * would scale an index level against a premium and make the premium flat.
   */
  priceLines?: SeriesLine[] | undefined;
  /**
   * Names the left axis. "Future" by default, which is what plots there on
   * every chart that does not say otherwise.
   */
  priceAxisName?: string | undefined;
  /**
   * Hide the left axis entirely.
   *
   * For a chart whose price-axis series are all switched off: left showing, the
   * axis auto-scales to nothing and prints a ladder of meaningless numbers
   * (0.50 down to -0.10) beside a plot with nothing on it. An axis that
   * measures no drawn series is furniture at best and misread at worst.
   */
  hidePriceAxis?: boolean | undefined;
  /**
   * Plot the value lines on the *price* axis instead of their own.
   *
   * For series measured in the same unit as the future - max pain is an index
   * level, not a ratio or an OI total. The whole reading of such a chart is the
   * *distance* between the lines, and on two independently scaled axes they can
   * appear to cross when they never did. Sharing the scale is the only way that
   * gap means anything.
   *
   * Opt-in: every other chart here plots a different quantity against price,
   * where a second scale is exactly right.
   */
  sharedPriceAxis?: boolean | undefined;
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
  /**
   * Let the reader work the time axis: wheel to zoom, drag inside the plot to
   * pan, drag the clock strip to stretch or squeeze the window.
   *
   * Opt-in, and off by default. A chart that takes the wheel stops the page
   * scrolling over it, which is a bad trade on a panel someone only glances at;
   * it earns its keep on a full-width chart people actually read into.
   */
  zoomable?: boolean | undefined;
  /**
   * Override the blank right margin, in pixels, when the default is wrong for
   * this panel.
   *
   * The 96px default budgets for a value pill *outside* the plot. On a chart
   * whose pills land inside it — the right axis is far enough in that the
   * end-of-line tag still clears it — that budget is simply a blank column, and
   * on a full-width panel it is a wide one. `containLabel` adds the right axis's
   * own tick labels on top of whatever is set here, so this is the gap after the
   * labels, not before them.
   */
  rightGutter?: number | undefined;
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
 * The time-axis zoom: wheel over the plot to scale the window, drag inside it to
 * pan, and drag the clock strip under the plot to stretch or squeeze the window
 * against its right edge (see `installAxisDrag` in `use-echart.ts`).
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
      // This chart carries two y axes; left to guess, the zoom binds the wrong
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
  const { referenceLine, showFutures, compact, rightGutter, zoomable } = input;
  const priceLines = input.priceLines ?? [];
  const sharedAxis = input.sharedPriceAxis === true;
  // On a shared scale the lines belong to the price axis, and the right axis
  // has nothing left of its own to measure.
  const valueAxisIndex = sharedAxis ? 0 : 1;
  const axisName = { color: theme.axis, fontSize: 11, fontWeight: 600 as const };

  const ms = timestamps.map((iso) => Date.parse(iso));
  const xs = ms.map(axisX);
  const first = xs[0] ?? 0;
  const last = xs.at(-1) ?? 0;
  // A single point has no span to take a share of; fall back to a few minutes
  // so the axis still has somewhere to put it.
  const pad = Math.max((last - first) * RIGHT_PAD, 5);
  const max = last + pad;

  const latestFuture = [...futures].reverse().find((value) => value != null) ?? null;

  return {
    backgroundColor: 'transparent',
    ...(zoomable ? { dataZoom: timeZoom({ start: first, end: max }) } : {}),
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
      right: rightGutter ?? (compact ? 16 : 96),
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
      // Blank track past the newest point — see RIGHT_PAD. Bounded by `dataZoom`
      // when the chart is zoomable and pinned here when it is not: a pinned axis
      // WINS over `dataZoom`, so fixing both leaves the wheel moving nothing.
      ...(zoomable ? {} : { min: first, max }),
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
        show: !input.hidePriceAxis,
        // Named at the top rather than rotated up the side: a rotated title
        // costs horizontal room the plot needs more, and this chart is wide.
        name: input.priceAxisName ?? 'Future',
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
        name: sharedAxis ? '' : valueAxisName,
        nameLocation: 'end',
        nameGap: 14,
        nameTextStyle: { ...axisName, align: 'right' },
        axisLine: { show: false },
        axisTick: { show: false },
        // Only the price axis draws split lines. Two sets of horizontal rules at
        // different intervals reads as a moiré and neither is followable.
        splitLine: { show: false },
        // Nothing plots against it on a shared scale; leaving its labels on
        // would print a second, unrelated ladder of numbers down the edge.
        axisLabel: sharedAxis
          ? { show: false }
          : { color: theme.axis, fontSize: 11, formatter: formatValue }
      }
    ],
    series: [
      ...(showFutures ? [futuresSeries(xs, futures, latestFuture, theme, formatPrice)] : []),
      // On the price axis, so their pills read in the same unit as its labels.
      ...priceLines.map((line) => contractSeries(xs, line, formatPrice, 0)),
      ...lines.map((line) => contractSeries(xs, line, formatValue, valueAxisIndex)),
      ...(referenceLine ? [markerSeries(referenceLine, theme, valueAxisIndex)] : [])
    ]
  };
}

/**
 * A vertical two-colour gradient that switches exactly where the series crosses
 * zero, for a line that colours by sign.
 *
 * Deliberately *not* ECharts' `visualMap`, which is the obvious tool and does
 * not work here: on a two-axis cartesian its line renderer takes a gradient
 * path that cannot resolve the mapped dimension and throws
 * "Cannot read properties of undefined (reading 'coord')" — piecewise or
 * continuous alike. A gradient needs no extra component registered, cannot be
 * silently tree-shaken away, and places the switch at the same pixel either way.
 *
 * Offsets are fractions of the shape's own bounding box, top to bottom, so the
 * caller passes the extent that box actually spans: the line's own min/max, and
 * for a band closing to zero, that range widened to include zero. An all-
 * positive or all-negative series clamps to a single colour, which is correct.
 */
function signedGradient(signed: { positive: string; negative: string }, lo: number, hi: number) {
  const span = hi - lo;
  const zero = span === 0 ? 0.5 : clamp01((hi - 0) / span);
  return {
    type: 'linear' as const,
    x: 0,
    y: 0,
    x2: 0,
    y2: 1,
    colorStops: [
      { offset: 0, color: signed.positive },
      { offset: zero, color: signed.positive },
      // A hair below the same offset: two stops at an identical offset is a
      // hard switch in every renderer that honours it, and a nudge guarantees
      // strictly increasing offsets for the ones that do not.
      { offset: Math.min(1, zero + 1e-6), color: signed.negative },
      { offset: 1, color: signed.negative }
    ]
  };
}

function clamp01(value: number): number {
  return Math.min(1, Math.max(0, value));
}

/** The colour a signed series ends on — the sign of its last real value. */
function endColor(line: SeriesLine): string {
  const signed = line.signed;
  if (!signed) return line.color;
  const last = [...line.values].reverse().find((value) => value != null) ?? 0;
  return last >= 0 ? signed.positive : signed.negative;
}

/** The drawn extent of a signed series, and of the band it closes to zero. */
function signedExtent(values: (number | null)[]) {
  const real = values.filter((value): value is number => value != null);
  const min = real.length > 0 ? Math.min(...real) : 0;
  const max = real.length > 0 ? Math.max(...real) : 0;
  return {
    line: { lo: min, hi: max },
    // The band reaches the zero line even when no point does.
    area: { lo: Math.min(0, min), hi: Math.max(0, max) }
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

function contractSeries(
  xs: number[],
  line: SeriesLine,
  formatValue: (value: number) => string,
  yAxisIndex: number
) {
  const extent = line.signed ? signedExtent(line.values) : null;
  const lineColor =
    line.signed && extent
      ? signedGradient(line.signed, extent.line.lo, extent.line.hi)
      : line.color;
  const areaColor =
    line.signed && extent
      ? signedGradient(line.signed, extent.area.lo, extent.area.hi)
      : withAlpha(line.color, 0.18);

  return {
    id: line.id,
    name: line.label,
    type: 'line',
    yAxisIndex,
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
    // Holds each value to the next point rather than sloping between them —
    // see `SeriesLine.step`. Omitted entirely when off, so nothing else changes.
    ...(line.step ? { step: 'end' as const } : {}),
    lineStyle: {
      width: line.dashed ? 1.25 : 2,
      color: lineColor,
      ...(line.dashed ? { type: 'dotted' as const } : {})
    },
    // A flat colour, because a dot or a pill filled with a gradient is the
    // wrong colour wherever it lands. For a signed series that flat colour
    // follows the *last* value's sign — the pill holds the closing number, and
    // a green pill on a loss of eleven thousand says the opposite of the figure
    // printed inside it.
    itemStyle: { color: line.signed ? endColor(line) : line.color },
    // A faint fill under the line when the caller asks for one. Left off the
    // object entirely otherwise, so a stack of lines is never quietly banded.
    // `origin` closes the band to a fixed y (e.g. 0) rather than the axis floor,
    // so a signed change series fills up above zero and down below it.
    ...(line.fill
      ? {
          areaStyle: {
            color: areaColor,
            // The signed band carries its colour in a gradient, which cannot
            // also carry alpha per stop here — so the faintness is set once.
            ...(line.signed ? { opacity: 0.18 } : {}),
            ...(line.fillOrigin !== undefined ? { origin: line.fillOrigin } : {})
          }
        }
      : {}),
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
      // Follows the closing value's sign on a signed series, for the same
      // reason the dot does: the tag holds that number.
      backgroundColor: line.signed ? endColor(line) : line.color,
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
function markerSeries(
  reference: { value: number; label: string },
  theme: ChartTheme,
  yAxisIndex: number
) {
  return {
    id: 'reference',
    type: 'line',
    yAxisIndex,
    data: [],
    silent: true,
    markLine: {
      silent: true,
      symbol: 'none',
      data: [{ yAxis: reference.value }],
      // Red rather than the marker amber. `--cn-warning` is tuned to sit on a
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
