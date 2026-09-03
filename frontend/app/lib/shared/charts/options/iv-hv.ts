import type { EChartsCoreOption } from '../echarts-modules';
import type { ChartTheme } from '../theme/types';
import { withAlpha } from '../theme/tokens';

/**
 * The volatility risk premium: what options charged for movement, against how
 * much movement there was.
 *
 * Pure: takes already-derived rows and returns an ECharts option, like its
 * siblings in this folder.
 *
 * **The sign is the chart.** A bar above zero means implied volatility sat above
 * historical — options priced rich against what the index actually did — and
 * below means the opposite. So the bar's side of zero is the entire reading,
 * which drives three decisions the rest of this file exists to protect:
 *
 * * the spread axis is **not** `scale: true`. That option lets ECharts drop zero
 *   out of the range when the data does not straddle it, which would leave a
 *   chart of "positive premium" bars floating above a baseline that is not
 *   there;
 * * zero gets its own drawn rule, on its own silent series, so hiding a series
 *   from the legend cannot take the reference with it — the treatment
 *   `vega-analysis.ts` established;
 * * colour comes from the datum's sign, not from its position, following
 *   `gamma-exposure.ts`'s net-exposure bars.
 *
 * **Two stacked panes, not one plot with two axes.** The first cut drew the
 * premium and the price over each other on a shared grid, and it was a mess:
 * the dotted price line wandered through the bars, the two scales had no
 * relationship, and the zero rule — the one line the whole chart is measured
 * against — was just another horizontal in the pile. Price on top, premium
 * below, is how every platform draws an oscillator under its subject, and it
 * gives the bars a pane whose vertical centre *is* zero.
 *
 * The two share one x axis window: a single `dataZoom` drives both, and
 * `axisPointer.link` runs the crosshair straight down through them, so they
 * read as one chart in two registers rather than two charts that happen to be
 * stacked.
 *
 * **Grid 0 is the bottom pane, deliberately.** `installAxisDrag` in
 * `use-echart.ts` finds the date strip by measuring grid index 0, so the pane
 * whose bottom edge is the chart's bottom has to be that one. Ordering them
 * the other way puts the drag strip through the middle of the chart.
 *
 * **A category date axis, at ~250 categories.** Same reasoning as its sibling
 * `iv-hv-ivp.ts`: a proportional time axis draws two closed days in seven as
 * fifty-two gaps a year. But unlike that page this one draws *bars*, and bars
 * on a dense category axis have their own failure modes — see the notes on
 * `spreadBars`.
 */

/** One session's row. Structurally the `SpreadRow` the page derives. */
export interface IvHvRow {
  /** IST trading date, `YYYY-MM-DD`. */
  d: string;
  /** IV − HV in volatility points; `null` where either side was missing. */
  spread: number | null;
  /** The index close — the axis's spine, present on every session. */
  close: number | null;
  /** The tradable future, on the sessions the archive recorded one. */
  future: number | null;
}

export interface IvHvVisible {
  spread: boolean;
  future: boolean;
  price: boolean;
}

export interface IvHvInput {
  rows: IvHvRow[];
  visible: IvHvVisible;
  /** Bars above zero. */
  callColor: string;
  /** Bars below zero. */
  putColor: string;
  futureColor: string;
  priceColor: string;
  /** Formats the left-axis index level. */
  formatPrice: (value: number) => string;
  /** Formats a spread, sign included. */
  formatSpread: (value: number) => string;
  /** `2026-07-30` → `30 Jul 26`, for the ticks and the tooltip header. */
  formatDay: (d: string) => string;
  /** Wheel to zoom the dates, drag to pan, drag the strip to stretch. */
  zoomable?: boolean | undefined;
}

/** The id of the zero rule's carrier series, so the tooltip can skip it. */
const ZERO_ID = 'zero';

export function buildIvHvOption(input: IvHvInput, theme: ChartTheme): EChartsCoreOption {
  const dates = input.rows.map((row) => row.d);

  return {
    backgroundColor: 'transparent',
    // Index 0 is the lower pane — see the module note on `installAxisDrag`.
    grid: [
      { left: 8, right: 8, top: '66%', bottom: 8, containLabel: true },
      { left: 8, right: 8, top: 28, height: '50%', containLabel: true }
    ],
    // One crosshair down both panes, so a date is read in both registers at
    // once rather than hunted for twice.
    axisPointer: { link: [{ xAxisIndex: 'all' }] },
    tooltip: tooltip(input, theme),
    xAxis: [dateAxis(input, theme, dates, 0, true), dateAxis(input, theme, dates, 1, false)],
    yAxis: [spreadAxis(input, theme), priceAxis(input, theme)],
    ...(input.zoomable ? { dataZoom: dateZoom() } : {}),
    series: series(input, theme)
  };
}

/**
 * The shared date axis, once per pane.
 *
 * Only the lower one carries labels; repeating them between the panes would
 * spend a row of plot height saying the same thing twice.
 */
function dateAxis(
  input: IvHvInput,
  theme: ChartTheme,
  dates: string[],
  gridIndex: number,
  labelled: boolean
) {
  return {
    type: 'category' as const,
    gridIndex,
    data: dates,
    // NOT `false`, which is right for a line chart and wrong here: it centres
    // the first and last category on the plot's edge, so half of each end bar
    // is drawn outside the grid.
    boundaryGap: true,
    axisLine: { lineStyle: { color: theme.grid } },
    axisTick: { show: false },
    axisLabel: {
      show: labelled,
      color: theme.axis,
      fontSize: 11,
      // A year of sessions is ~250 categories; letting ECharts drop what does
      // not fit beats picking an interval that is wrong at some widths.
      hideOverlap: true,
      margin: 10,
      formatter: (value: string) => input.formatDay(value)
    }
  };
}

function priceAxis(input: IvHvInput, theme: ChartTheme) {
  return {
    type: 'value' as const,
    gridIndex: 1,
    name: 'Index',
    nameTextStyle: { color: theme.axis, fontSize: 10 },
    // The index never approaches zero, and anchoring there flattens a year of
    // movement into a band at the top of the plot.
    scale: true,
    splitLine: { lineStyle: { color: theme.grid, type: 'dashed' as const } },
    axisLabel: { color: theme.axis, fontSize: 11, formatter: input.formatPrice }
  };
}

/**
 * The spread axis — deliberately without `scale`.
 *
 * `scale: true` would let the range exclude zero on a stretch where every
 * session happened to be rich, and a signed chart whose baseline has wandered
 * off the bottom of the plot is worse than no chart. Only one grid of split
 * lines, too, or the two axes draw a lattice nothing can be read through.
 */
function spreadAxis(input: IvHvInput, theme: ChartTheme) {
  return {
    type: 'value' as const,
    gridIndex: 0,
    name: 'IV − HV',
    nameTextStyle: { color: theme.axis, fontSize: 10 },
    // Its own pane, so it keeps its own grid lines — there is no second axis
    // here to draw a lattice against.
    splitLine: { lineStyle: { color: theme.grid, type: 'dashed' as const } },
    axisLabel: { color: theme.axis, fontSize: 11, formatter: input.formatSpread }
  };
}

/**
 * Wheel to zoom, drag to pan, on the date axis.
 *
 * `filterMode: 'none'` scales the axis rather than dropping what falls outside
 * it, which matters more here than on a line chart: `'filter'` recomputes the
 * value axis from the visible window, so the zero line would jump position as
 * the reader panned — on the one chart where zero is the whole point.
 *
 * `installAxisDrag` in `use-echart.ts` picks this up unaided; emitting the
 * component is the only wiring a chart needs.
 */
function dateZoom() {
  return [
    {
      type: 'inside' as const,
      // Both panes move together; they are one window in two registers.
      xAxisIndex: [0, 1],
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

function series(input: IvHvInput, theme: ChartTheme) {
  const out: Record<string, unknown>[] = [];

  if (input.visible.spread) out.push(spreadBars(input));
  // The rule is drawn whenever the axis it belongs to is in use, on a carrier
  // of its own — hanging it off the bar series would take the reference away
  // with the bars the moment the reader hid them.
  if (input.visible.spread) out.push(zeroRule(theme));

  if (input.visible.price) {
    out.push({
      name: 'Index Price',
      type: 'line',
      xAxisIndex: 1,
      yAxisIndex: 1,
      data: input.rows.map((row) => row.close),
      symbol: 'none',
      smooth: false,
      // Dotted and dimmed: the index is the backdrop the premium is read
      // against, not a competitor to it.
      lineStyle: { color: withAlpha(input.priceColor, 0.85), width: 1.25, type: 'dotted' as const },
      itemStyle: { color: input.priceColor },
      connectNulls: true,
      emphasis: { disabled: true },
      z: 2
    });
  }

  if (input.visible.future) {
    out.push({
      name: 'Future',
      type: 'line',
      xAxisIndex: 1,
      yAxisIndex: 1,
      data: input.rows.map((row) => row.future),
      symbol: 'none',
      smooth: false,
      lineStyle: { color: input.futureColor, width: 1.5 },
      itemStyle: { color: input.futureColor },
      // Unlike the index, the future genuinely stops where the archive stops.
      // Bridging that would draw a year of a series that has a fortnight.
      connectNulls: false,
      emphasis: { disabled: true },
      // Over the index: the future is the series with something to say, the
      // index is the backdrop.
      z: 3
    });
  }

  return out;
}

/**
 * The premium bars, coloured by sign.
 *
 * Geometry is tuned for the density this page actually runs at. A year is ~250
 * categories in ~1200px — under 5px each — and the settings the strike-ladder
 * charts use (`barCategoryGap: '34%'`, a 4px `borderRadius`, a 1px border) all
 * assume a bar an order of magnitude wider. At this width they variously eat
 * the bar, round it into a dot, or turn half of it into border. So: a small
 * gap, a cap that only binds once the reader has zoomed in, and no decoration
 * at all. Colour carries the sign, which is all it has to carry.
 *
 * `emphasis` is off because ECharts' default hover highlight fires per bar, and
 * flickering through 5px columns as the cursor crosses them is noise — the
 * axis pointer's shadow band already says which session is under the pointer.
 */
function spreadBars(input: IvHvInput) {
  const last = lastQuoted(input.rows);

  return {
    name: 'IV − HV',
    type: 'bar',
    xAxisIndex: 0,
    yAxisIndex: 0,
    barMaxWidth: 14,
    barCategoryGap: '10%',
    data: input.rows.map((row, index) => {
      if (row.spread === null) return null;
      const color = row.spread >= 0 ? input.callColor : input.putColor;
      return {
        value: row.spread,
        itemStyle: { color },
        // The newest reading gets its value tagged. `endLabel` is a line-series
        // option and renders nothing on a bar, so the label rides on the datum.
        ...(index === last
          ? {
              label: {
                show: true,
                position: (row.spread >= 0 ? 'top' : 'bottom') as 'top' | 'bottom',
                formatter: input.formatSpread(row.spread),
                color,
                fontSize: 11,
                fontWeight: 700 as const
              }
            }
          : {})
      };
    }),
    emphasis: { disabled: true },
    z: 2
  };
}

/** Index of the last session with a computable premium, or `-1`. */
function lastQuoted(rows: IvHvRow[]): number {
  for (let index = rows.length - 1; index >= 0; index--) {
    if (rows[index]?.spread != null) return index;
  }
  return -1;
}

/**
 * Zero, drawn rather than implied.
 *
 * On its own empty, silent series so that toggling anything else off cannot
 * remove the line every bar is measured against — the arrangement
 * `vega-analysis.ts` arrived at for the same reason.
 */
function zeroRule(theme: ChartTheme) {
  return {
    id: ZERO_ID,
    type: 'line',
    xAxisIndex: 0,
    yAxisIndex: 0,
    data: [],
    silent: true,
    markLine: {
      silent: true,
      symbol: 'none',
      data: [{ yAxis: 0 }],
      // Neutral, not `theme.marker`: that is the app's amber, which is a
      // *series* colour on this page. A zero rule sharing a hue with the future
      // read as a second future line running flat across the plot.
      lineStyle: { color: withAlpha(theme.axis, 0.7), type: 'solid' as const, width: 1 },
      label: {
        formatter: '0',
        position: 'insideEndTop' as const,
        color: theme.axis,
        fontSize: 10,
        fontWeight: 600 as const
      }
    },
    z: 3
  };
}

/**
 * Every visible series at one date, headed by the date.
 *
 * Hand-built because the three series carry two units — an index level and
 * volatility points — which one formatter cannot serve. A shadow band rather
 * than a line for the pointer, which is what the bar charts in this folder use:
 * it says which category is under the cursor without drawing a rule through
 * the column it is describing.
 */
function tooltip(input: IvHvInput, theme: ChartTheme) {
  return {
    trigger: 'axis' as const,
    axisPointer: { type: 'shadow' as const },
    backgroundColor: theme.tooltipBg,
    borderWidth: 0,
    textStyle: { color: theme.tooltipText, fontSize: 12 },
    formatter: (params: unknown) => {
      const list = Array.isArray(params) ? params : [params];
      // The zero rule is a carrier with no data; it must not decide the index.
      const first = list.find((entry) => (entry as { seriesId?: string }).seriesId !== ZERO_ID) as
        { dataIndex?: number } | undefined;
      const index = first?.dataIndex;
      if (index === undefined) return '';
      const row = input.rows[index];
      if (!row) return '';
      return tooltipHtml(input, row);
    }
  };
}

export function tooltipHtml(input: IvHvInput, row: IvHvRow): string {
  const lines: string[] = [];

  if (input.visible.spread) {
    const color =
      row.spread === null ? input.priceColor : row.spread >= 0 ? input.callColor : input.putColor;
    lines.push(entry(color, 'IV − HV', row.spread === null ? '—' : input.formatSpread(row.spread)));
  }
  if (input.visible.future) {
    lines.push(
      entry(input.futureColor, 'Future', row.future === null ? '—' : input.formatPrice(row.future))
    );
  }
  if (input.visible.price) {
    lines.push(
      entry(
        input.priceColor,
        'Index Price',
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
