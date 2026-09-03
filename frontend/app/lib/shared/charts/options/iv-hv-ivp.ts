import type { EChartsCoreOption } from '../echarts-modules';
import type { ChartTheme } from '../theme/types';
import { withAlpha } from '../theme/tokens';

/**
 * Implied against historical volatility over months of sessions, with the index
 * behind it.
 *
 * Pure: takes already-derived rows and returns an ECharts option, like its
 * siblings in this folder.
 *
 * **The app's first date axis, and it is a category axis on purpose.** Every
 * other builder here is either a strike category or elapsed session minutes.
 * Calendar time offers a third option — `type: 'time'` — and it is the wrong
 * one: a market is shut two days in seven, and a proportional time axis draws
 * that as fifty-two gaps a year, turning a year of trading into a picket fence.
 * A category of session dates closes them, which is what every financial chart
 * does and what the reference draws.
 *
 * **Three axes, because three units.** The index runs to five figures; IV, HV
 * and RV are volatility points in the teens; IVR and IVP are percentages of a
 * hundred. Sharing one right axis between the last two groups looked reasonable
 * on paper and was wrong in practice: switching the percentiles on stretched the
 * axis to 0-70 and squashed the volatility lines the page is named for into the
 * bottom fifth of the plot. The percentiles get their own scale, pinned to
 * 0-100 so it never moves, offset outward from the volatility one.
 *
 * **The window is the reader's.** A year of sessions at 250 categories is far
 * more than anyone reads at once, so the axis takes the wheel and the drag —
 * the same gesture as the intraday charts, via the shared `installAxisDrag`.
 */

/** One session's row. Structurally the `SkewRow` the page derives. */
export interface IvHvIvpRow {
  /** IST trading date, `YYYY-MM-DD`. */
  d: string;
  close: number | null;
  iv: number | null;
  hv: number | null;
  rv: number | null;
  ivr: number | null;
  ivp: number | null;
}

/** Which of the six lines is currently drawn. */
export interface IvHvIvpVisible {
  iv: boolean;
  hv: boolean;
  rv: boolean;
  ivr: boolean;
  ivp: boolean;
  price: boolean;
}

export interface IvHvIvpInput {
  rows: IvHvIvpRow[];
  visible: IvHvIvpVisible;
  /** Colour per series id, so the legend and the plot cannot disagree. */
  colors: Record<keyof IvHvIvpVisible, string>;
  /** Formats the left-axis index level. */
  formatPrice: (value: number) => string;
  /** Formats a right-axis volatility or percentile. */
  formatIv: (value: number) => string;
  /** `2026-07-30` → `30 Jul 26`, for the ticks and the tooltip header. */
  formatDay: (d: string) => string;
  /**
   * Let the reader work the date axis: wheel to zoom, drag inside the plot to
   * pan, drag the strip under it to stretch the window.
   *
   * On a year of daily sessions this is not a nicety. The stretch anyone
   * actually wants to read is usually the last few weeks, and without it they
   * are stuck with 250 sessions squeezed into the panel width.
   */
  zoomable?: boolean | undefined;
}

/** Human names, in the order the tooltip lists them. */
const SERIES_LABELS: Record<keyof IvHvIvpVisible, string> = {
  iv: 'IV',
  hv: 'HV',
  rv: 'RV',
  ivr: 'IVR',
  ivp: 'IVP',
  price: 'Index Price'
};

/** Volatility points — the inner right axis. */
const VOL_KEYS = ['iv', 'hv', 'rv'] as const;

/** Percentages of a hundred — the outer right axis, fixed at 0-100. */
const PCT_KEYS = ['ivr', 'ivp'] as const;

/** Every series drawn against a right-hand axis, in drawing order. */
const LINE_KEYS = [...VOL_KEYS, ...PCT_KEYS] as const;

type LineKey = (typeof LINE_KEYS)[number];

function isPct(key: LineKey): boolean {
  return (PCT_KEYS as readonly string[]).includes(key);
}

export function buildIvHvIvpOption(input: IvHvIvpInput, theme: ChartTheme): EChartsCoreOption {
  return {
    backgroundColor: 'transparent',
    grid: { left: 8, right: 8, top: 24, bottom: 8, containLabel: true },
    tooltip: tooltip(input, theme),
    xAxis: {
      type: 'category',
      data: input.rows.map((row) => row.d),
      boundaryGap: false,
      axisLine: { lineStyle: { color: theme.grid } },
      axisTick: { show: false },
      axisLabel: {
        color: theme.axis,
        fontSize: 11,
        // A year of sessions is ~250 categories; letting ECharts drop what does
        // not fit beats picking an interval that is wrong at some widths.
        hideOverlap: true,
        margin: 10,
        formatter: (value: string) => input.formatDay(value)
      }
    },
    yAxis: [priceAxis(input, theme), volAxis(input, theme), pctAxis(theme)],
    ...(input.zoomable ? { dataZoom: dateZoom() } : {}),
    series: series(input, theme)
  };
}

function priceAxis(input: IvHvIvpInput, theme: ChartTheme) {
  return {
    type: 'value' as const,
    name: 'Index',
    nameTextStyle: { color: theme.axis, fontSize: 10 },
    // The index never approaches zero, and anchoring there flattens a year of
    // movement into a band at the top of the plot.
    scale: true,
    splitLine: { lineStyle: { color: theme.grid, type: 'dashed' as const } },
    axisLabel: { color: theme.axis, fontSize: 11, formatter: input.formatPrice }
  };
}

function volAxis(input: IvHvIvpInput, theme: ChartTheme) {
  return {
    type: 'value' as const,
    name: 'IV / HV',
    nameTextStyle: { color: theme.axis, fontSize: 10 },
    scale: true,
    // Only one grid of split lines, or the two axes draw a lattice nothing can
    // be read through.
    splitLine: { show: false },
    axisLabel: { color: theme.axis, fontSize: 11, formatter: input.formatIv }
  };
}

/**
 * The percentile scale, pinned rather than fitted.
 *
 * IVR and IVP are shares of a hundred by definition, so an axis that rescaled
 * itself to whatever the window happened to contain would make "IVP 40" look
 * different from one range to the next — which is the one thing a percentile
 * must not do. Offset outward so it reads as a second, separate scale.
 */
function pctAxis(theme: ChartTheme) {
  return {
    type: 'value' as const,
    name: 'IVR / IVP',
    nameTextStyle: { color: theme.axis, fontSize: 10 },
    min: 0,
    max: 100,
    position: 'right' as const,
    offset: 46,
    splitLine: { show: false },
    axisLabel: { color: theme.axis, fontSize: 11, formatter: (value: number) => `${value}%` }
  };
}

/**
 * Wheel to zoom, drag to pan — the shared gesture, on a category axis.
 *
 * `filterMode: 'none'` scales the axis instead of dropping the points outside
 * it, which is what keeps a line continuous across the edge of the window
 * rather than ending at it.
 */
function dateZoom() {
  return [
    {
      type: 'inside' as const,
      xAxisIndex: 0,
      filterMode: 'none' as const,
      start: 0,
      end: 100,
      zoomOnMouseWheel: true,
      moveOnMouseMove: true,
      moveOnMouseWheel: false,
      preventDefaultMouseMove: true
    }
  ];
}

function series(input: IvHvIvpInput, theme: ChartTheme) {
  const out: Record<string, unknown>[] = [];

  if (input.visible.price) {
    out.push({
      name: SERIES_LABELS.price,
      type: 'line',
      yAxisIndex: 0,
      data: input.rows.map((row) => row.close),
      symbol: 'none',
      smooth: false,
      // Dotted and dimmed: the index is the backdrop the volatility is read
      // against, not a competitor to it. Same treatment the intraday charts
      // give the future.
      lineStyle: { color: withAlpha(theme.axis, 0.9), width: 1.25, type: 'dotted' as const },
      itemStyle: { color: theme.axis },
      connectNulls: true,
      emphasis: { disabled: true },
      z: 2
    });
  }

  for (const key of LINE_KEYS) {
    if (!input.visible[key]) continue;
    const values = input.rows.map((row) => row[key]);
    // A series quoted on only some of the window's sessions gets its points
    // marked, so the reader can tell a measured session from an interpolated
    // stretch. Half is the threshold rather than a quarter: at a fortnight of
    // history inside a month of price, the markers are the whole story.
    const quoted = values.filter((value) => value !== null).length;
    const sparse = quoted > 0 && quoted < values.length / 2;
    out.push({
      name: SERIES_LABELS[key],
      type: 'line',
      yAxisIndex: isPct(key) ? 2 : 1,
      data: values,
      symbol: 'circle',
      symbolSize: sparse ? 4 : 3,
      showSymbol: sparse,
      smooth: false,
      /*
       * Bridge the missing sessions, and mark the real ones.
       *
       * The first cut broke the line at every gap, on the reasoning that a
       * gap is information. That is true of a dense series with an occasional
       * hole; it is false of this one. A volatility archive that has just
       * started is *irregularly sampled* — a day the worker did not run leaves
       * no row — and breaking on each one shattered a fortnight of readings
       * into three-point fragments that read as a rendering fault rather than
       * as missing data.
       *
       * So the line joins the observations and the markers say which points
       * are observations. Nothing is invented: the dots are the data, the
       * segments between them are a guide, and a leading run of nulls still
       * starts the line late rather than reaching back.
       */
      connectNulls: true,
      lineStyle: { color: input.colors[key], width: key === 'iv' ? 2 : 1.5 },
      itemStyle: { color: input.colors[key] },
      emphasis: { focus: 'series' as const },
      blur: { lineStyle: { opacity: 0.15 } },
      // The newest value, tagged on the axis edge — the reference's `11.31`.
      endLabel: {
        show: true,
        formatter: () => tail(input.rows, key, input.formatIv),
        color: theme.onMarker,
        backgroundColor: input.colors[key],
        padding: [2, 5],
        borderRadius: 3,
        fontSize: 11,
        fontWeight: 700 as const
      },
      labelLayout: { moveOverlap: 'shiftY' as const },
      z: key === 'iv' ? 6 : 4
    });
  }

  return out;
}

/** The last quoted value of a series, for its end-of-line tag. */
function tail(rows: IvHvIvpRow[], key: LineKey, format: (value: number) => string): string {
  for (let index = rows.length - 1; index >= 0; index--) {
    const value = rows[index]?.[key];
    if (typeof value === 'number') return format(value);
  }
  return '';
}

/**
 * Every visible series at one date, headed by the date itself.
 *
 * Hand-built rather than ECharts' default because the six series carry two
 * different units — an index level and volatility points — and the default
 * formatter would render both through one.
 */
function tooltip(input: IvHvIvpInput, theme: ChartTheme) {
  return {
    trigger: 'axis' as const,
    axisPointer: { type: 'line' as const, lineStyle: { color: theme.axis, type: 'dotted' } },
    backgroundColor: theme.tooltipBg,
    borderWidth: 0,
    textStyle: { color: theme.tooltipText, fontSize: 12 },
    formatter: (params: unknown) => {
      const list = Array.isArray(params) ? params : [params];
      const first = list[0] as { dataIndex?: number } | undefined;
      const index = first?.dataIndex;
      if (index === undefined) return '';
      const row = input.rows[index];
      if (!row) return '';
      return tooltipHtml(input, row);
    }
  };
}

export function tooltipHtml(input: IvHvIvpInput, row: IvHvIvpRow): string {
  const lines: string[] = [];
  for (const key of LINE_KEYS) {
    if (!input.visible[key]) continue;
    const value = row[key];
    lines.push(
      entry(
        input.colors[key],
        SERIES_LABELS[key],
        value === null ? '—' : isPct(key) ? `${input.formatIv(value)}%` : input.formatIv(value)
      )
    );
  }
  if (input.visible.price) {
    lines.push(
      entry(
        input.colors.price,
        SERIES_LABELS.price,
        row.close === null ? '—' : input.formatPrice(row.close)
      )
    );
  }
  return (
    `<div style="font-weight:700;margin-bottom:4px">${input.formatDay(row.d)}</div>` +
    lines.join('')
  );
}

function entry(color: string, name: string, value: string): string {
  return (
    `<div style="display:flex;align-items:center;gap:6px;line-height:1.6">` +
    `<span style="display:inline-block;width:8px;height:8px;border-radius:2px;background:${color}"></span>` +
    `<span style="flex:1">${name}:</span><b>${value}</b></div>`
  );
}
