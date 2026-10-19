import type { EChartsCoreOption } from '../echarts-modules';
import { withAlpha } from '../theme/tokens';
import type { ChartTheme } from '../theme/types';

/**
 * The Relative Rotation Graph: every sector's path against one benchmark.
 *
 * **x** is JdK RS-Ratio — the sector's relative strength as a z-score of its
 * own recent range. **y** is JdK RS-Momentum — the normalised rate of change
 * of that ratio. Both are centred on 100 and unitless, which is the whole
 * point: it is what lets a dozen sectors trading at wildly different levels
 * share one grid.
 *
 * Each sector draws a *tail* — a line through its last N periods, ending in a
 * head marker and a label. Because momentum leads ratio, tails tend to rotate
 * clockwise: improving (top-left) → leading (top-right) → weakening
 * (bottom-right) → lagging (bottom-left).
 *
 * **Colour is redundant with position, on purpose.** A sector's quadrant is
 * already given by where its head sits, so the four hues repeat what the
 * geometry says — which is exactly what makes them safe. Nothing is lost if
 * two are confused, and it sidesteps the all-pairs separation problem a
 * categorical palette would have with a dozen overlapping tails. The tail
 * takes its colour from the quadrant its *head* is in, so a sector that has
 * just crossed reads as where it arrived rather than where it came from.
 *
 * **The tail fades toward its tail-end.** Opacity ramps from faint at the
 * oldest point to solid at the head, so direction is readable without an
 * arrowhead on every segment — on a grid holding twelve sectors, arrowheads
 * turn into visual noise long before they become informative.
 */

export interface RrgTailPoint {
  at: string;
  x: number;
  y: number;
}

export interface RrgSeries {
  sector: string;
  quadrant: 'leading' | 'weakening' | 'lagging' | 'improving';
  points: RrgTailPoint[];
  measured: number;
  members: number;
}

interface Options {
  /** Draw the sector name beside each head. */
  labels?: boolean;
  /** Formats a point's timestamp for the tooltip. */
  formatStamp?: (iso: string) => string;
}

/** The axes cross here; every number on this plane is an offset from it. */
const CENTRE = 100;

/**
 * Smallest half-width the axes will shrink to, in z-score units.
 *
 * A quiet session can put every sector within a tenth of a point of the
 * centre, and an axis auto-fitted to that magnifies noise into what looks like
 * violent rotation. Holding a floor keeps a calm board looking calm.
 */
const MIN_SPAN = 1.5;

/** Headroom around the widest point so labels are not clipped at the frame. */
const SPAN_PADDING = 1.35;

function quadrantColor(quadrant: RrgSeries['quadrant'], theme: ChartTheme): string {
  switch (quadrant) {
    case 'leading':
      return theme.up;
    case 'lagging':
      return theme.down;
    case 'improving':
      return theme.accent;
    case 'weakening':
      return theme.marker;
  }
}

/**
 * A symmetric half-width that contains every point of every tail.
 *
 * Symmetric because the origin is the benchmark itself. An axis running 99.8
 * to 104 would put the benchmark hard against the left frame and make a
 * broadly strong board look like a balanced one.
 */
export function rrgSpan(series: RrgSeries[]): number {
  const offsets = series.flatMap((entry) =>
    entry.points.flatMap((point) => [Math.abs(point.x - CENTRE), Math.abs(point.y - CENTRE)])
  );
  const widest = Math.max(...offsets, MIN_SPAN);
  return Number((widest * SPAN_PADDING).toFixed(2));
}

export function buildSectorRrgOption(
  series: RrgSeries[],
  theme: ChartTheme,
  { labels = true, formatStamp }: Options = {}
): EChartsCoreOption {
  const span = rrgSpan(series);
  const low = CENTRE - span;
  const high = CENTRE + span;

  return {
    animation: false,
    grid: { left: 56, right: 24, top: 28, bottom: 44 },
    tooltip: {
      trigger: 'item',
      backgroundColor: theme.tooltipBg,
      borderWidth: 0,
      textStyle: { color: theme.tooltipText, fontSize: 12 },
      formatter: (params: unknown) => {
        const point = params as { data?: unknown; seriesName?: string };
        const data = point.data as [number, number, string, string] | undefined;
        if (!data) return '';
        const [x, y, , at] = data;
        const when = formatStamp && at ? formatStamp(at) : at;
        return [
          `<strong>${point.seriesName ?? ''}</strong>`,
          `RS-Ratio ${x.toFixed(2)}`,
          `RS-Momentum ${y.toFixed(2)}`,
          when ? `<span style="opacity:.7">${when}</span>` : ''
        ]
          .filter(Boolean)
          .join('<br/>');
      }
    },
    xAxis: {
      type: 'value',
      name: 'JdK RS-Ratio',
      nameLocation: 'middle',
      nameGap: 26,
      nameTextStyle: { color: theme.axis, fontSize: 10 },
      min: low,
      max: high,
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: theme.axis, fontSize: 10, formatter: (v: number) => v.toFixed(1) },
      splitLine: { lineStyle: { color: withAlpha(theme.grid, 0.5) } }
    },
    yAxis: {
      type: 'value',
      name: 'JdK RS-Momentum',
      nameLocation: 'middle',
      nameGap: 40,
      nameTextStyle: { color: theme.axis, fontSize: 10 },
      min: low,
      max: high,
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: theme.axis, fontSize: 10, formatter: (v: number) => v.toFixed(1) },
      splitLine: { lineStyle: { color: withAlpha(theme.grid, 0.5) } }
    },
    series: [
      quadrantLayer(span, theme),
      ...series.flatMap((entry) => tailSeries(entry, theme, labels))
    ]
  };
}

/**
 * The four tinted quadrants and their corner captions.
 *
 * One invisible scatter carrying `markArea` rather than four real series: the
 * bands are background, and giving them series identity would put four
 * meaningless entries in every legend and tooltip that iterates series.
 */
function quadrantLayer(span: number, theme: ChartTheme) {
  const tint = (color: string) => ({ itemStyle: { color: withAlpha(color, 0.07) } });
  const low = CENTRE - span;
  const high = CENTRE + span;

  const caption = (text: string, x: number, y: number, align: 'left' | 'right') => ({
    xAxis: x,
    yAxis: y,
    value: text,
    label: {
      show: true,
      formatter: text,
      color: withAlpha(theme.axis, 0.75),
      fontSize: 9,
      fontWeight: 700,
      align,
      verticalAlign: y > CENTRE ? 'top' : 'bottom',
      padding: [6, 8, 6, 8]
    },
    symbol: 'none'
  });

  return {
    type: 'scatter',
    name: '',
    silent: true,
    data: [],
    markArea: {
      silent: true,
      data: [
        [
          { ...tint(theme.up), xAxis: CENTRE, yAxis: CENTRE },
          { xAxis: high, yAxis: high }
        ],
        [
          { ...tint(theme.accent), xAxis: low, yAxis: CENTRE },
          { xAxis: CENTRE, yAxis: high }
        ],
        [
          { ...tint(theme.marker), xAxis: CENTRE, yAxis: low },
          { xAxis: high, yAxis: CENTRE }
        ],
        [
          { ...tint(theme.down), xAxis: low, yAxis: low },
          { xAxis: CENTRE, yAxis: CENTRE }
        ]
      ]
    },
    markPoint: {
      silent: true,
      data: [
        caption('LEADING', high, high, 'right'),
        caption('IMPROVING', low, high, 'left'),
        caption('WEAKENING', high, low, 'right'),
        caption('LAGGING', low, low, 'left')
      ]
    }
  };
}

/**
 * One sector: the fading trail, then the head on top of it.
 *
 * Two series rather than one because they need different z-orders against
 * every *other* sector — on a crowded grid each head must sit above every
 * trail, not just its own, or a heavily overlapped centre buries the one mark
 * the reader is looking for.
 */
function tailSeries(entry: RrgSeries, theme: ChartTheme, labels: boolean) {
  const color = quadrantColor(entry.quadrant, theme);
  const points = entry.points.map(
    (point) => [point.x, point.y, entry.sector, point.at] as [number, number, string, string]
  );
  const head = points.at(-1);

  return [
    {
      type: 'line',
      name: entry.sector,
      z: 2,
      data: points,
      showSymbol: true,
      symbolSize: 4,
      // Opacity ramps along the trail so the direction of travel is readable
      // without an arrowhead on every segment.
      itemStyle: {
        color: (params: { dataIndex: number }) =>
          withAlpha(color, 0.25 + (0.6 * params.dataIndex) / Math.max(points.length - 1, 1))
      },
      lineStyle: { color: withAlpha(color, 0.55), width: 1.5 },
      smooth: 0.3,
      emphasis: { focus: 'series', lineStyle: { width: 2.5 } }
    },
    {
      type: 'scatter',
      name: entry.sector,
      z: 3,
      data: head ? [head] : [],
      symbolSize: 11,
      itemStyle: { color, borderColor: theme.surface, borderWidth: 1.5 },
      label: {
        show: labels,
        position: 'right',
        distance: 6,
        formatter: entry.sector,
        color: theme.axis,
        fontSize: 10,
        fontWeight: 600
      },
      emphasis: { focus: 'series', scale: 1.3 }
    }
  ];
}
