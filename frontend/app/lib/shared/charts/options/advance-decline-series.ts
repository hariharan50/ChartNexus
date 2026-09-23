import type { EChartsCoreOption } from 'echarts/core';
import type { ChartTheme } from '../theme/types';
import { withAlpha } from '../theme/tokens';

/**
 * Advances and declines through the session, with the benchmark over them.
 *
 * **Two y axes, and the reason is worth stating.** Advances and declines are
 * counts and share the right-hand scale; the index level is rupees and cannot.
 * A dual axis is the one chart shape that can invent a correlation — where the
 * two scales line up is a choice, not a fact — so nothing here leans on the
 * lines crossing. The reading is in the *shapes*: an index climbing while
 * advances fall is a narrowing rally, and that is true however the axes are
 * anchored. The benchmark is drawn dotted and recessive for the same reason,
 * as context behind the subject rather than a third equal series.
 *
 * `price-vs-oi.ts` makes the same trade for price against open interest.
 */

export interface BreadthSeriesPoint {
  at: string;
  advancing: number;
  declining: number;
  level: number | null;
  advancingWeight: number | null;
  decliningWeight: number | null;
}

export interface AdvanceDeclineSeriesOptions {
  /** Plot the index weight behind each side instead of the head count. */
  weighted: boolean;
  /** Names the benchmark line, e.g. "NIFTY 50". Omitted for a sector. */
  levelName: string | null;
  formatTime: (iso: string) => string;
  formatLevel: (value: number) => string;
}

const ADVANCES = 'Advances';
const DECLINES = 'Declines';

export function buildAdvanceDeclineSeriesOption(
  points: BreadthSeriesPoint[],
  theme: ChartTheme,
  options: AdvanceDeclineSeriesOptions
): EChartsCoreOption {
  const times = points.map((point) => point.at);
  const hasLevel = Boolean(options.levelName) && points.some((point) => point.level !== null);
  const pick = (point: BreadthSeriesPoint, side: 'up' | 'down'): number | null =>
    options.weighted
      ? side === 'up'
        ? point.advancingWeight
        : point.decliningWeight
      : side === 'up'
        ? point.advancing
        : point.declining;

  return {
    backgroundColor: 'transparent',
    grid: { left: 8, right: 8, top: 32, bottom: 8, containLabel: true },
    // One crosshair, one readout: the reader aims at a time, never at a line.
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'line', lineStyle: { color: theme.axis, width: 1 } },
      backgroundColor: theme.tooltipBg,
      borderWidth: 0,
      textStyle: { color: theme.tooltipText, fontSize: 12 },
      formatter: (params: unknown) => tooltip(params, options)
    },
    legend: {
      top: 0,
      left: 0,
      itemWidth: 14,
      itemHeight: 2,
      icon: 'roundRect',
      textStyle: { color: theme.axis, fontSize: 11 },
      inactiveColor: withAlpha(theme.axis, 0.35)
    },
    xAxis: {
      type: 'category',
      data: times,
      boundaryGap: false,
      axisLine: { lineStyle: { color: theme.grid } },
      axisTick: { show: false },
      axisLabel: {
        color: theme.axis,
        fontSize: 11,
        hideOverlap: true,
        formatter: (value: string) => options.formatTime(value)
      }
    },
    yAxis: [
      {
        // Index 0 is the level, on the left, exactly as the reference has it.
        type: 'value',
        position: 'left',
        scale: true,
        show: hasLevel,
        axisLine: { show: false },
        axisTick: { show: false },
        splitLine: { lineStyle: { color: theme.grid, type: 'solid' } },
        axisLabel: {
          color: theme.axis,
          fontSize: 11,
          formatter: (value: number) => options.formatLevel(value)
        }
      },
      {
        // Counts, on the right. Anchored at zero: a count axis that floats
        // makes four advances look like forty.
        type: 'value',
        position: 'right',
        min: 0,
        axisLine: { show: false },
        axisTick: { show: false },
        splitLine: { show: false },
        axisLabel: { color: theme.axis, fontSize: 11 }
      }
    ],
    series: [
      line(
        ADVANCES,
        points.map((point) => pick(point, 'up')),
        theme.call,
        theme
      ),
      line(
        DECLINES,
        points.map((point) => pick(point, 'down')),
        theme.put,
        theme
      ),
      ...(hasLevel
        ? [
            {
              name: options.levelName,
              type: 'line' as const,
              yAxisIndex: 0,
              data: points.map((point) => point.level),
              showSymbol: false,
              connectNulls: true,
              // Dotted and dimmed: context behind the subject, never a third
              // series competing with the two the card is about.
              lineStyle: { width: 1.5, type: 'dotted' as const, color: withAlpha(theme.axis, 0.9) },
              z: 1
            }
          ]
        : [])
    ]
  };
}

function line(name: string, data: (number | null)[], color: string, theme: ChartTheme) {
  return {
    name,
    type: 'line' as const,
    yAxisIndex: 1,
    data,
    showSymbol: false,
    connectNulls: true,
    lineStyle: { width: 2, color },
    itemStyle: { color },
    // A wash, not a block — the fill says "this is the area under a count",
    // and at full saturation it would bury the benchmark behind it.
    areaStyle: { color: withAlpha(color, 0.1) },
    z: 2,
    emphasis: { focus: 'series' as const },
    // A 2px ring in the surface colour keeps the hover dot legible where the
    // two lines cross.
    symbolSize: 8,
    emphasisSymbolSize: 8,
    itemStyleEmphasis: { borderColor: theme.surface, borderWidth: 2 }
  };
}

interface TooltipRow {
  seriesName?: string;
  axisValue?: string;
  value?: number | null;
  color?: string;
}

function tooltip(params: unknown, options: AdvanceDeclineSeriesOptions): string {
  const rows = (Array.isArray(params) ? params : [params]) as TooltipRow[];
  if (rows.length === 0) return '';

  const head = options.formatTime(rows[0]?.axisValue ?? '');
  const lines = rows
    .filter((row) => row.value !== null && row.value !== undefined)
    .map((row) => {
      const isLevel = row.seriesName === options.levelName;
      const value = isLevel
        ? options.formatLevel(Number(row.value))
        : options.weighted
          ? `${Number(row.value).toFixed(1)}%`
          : String(row.value);
      // Value first, series second: the reader already knows which series
      // they are looking at and came here for the number.
      return `<div style="display:flex;gap:8px;align-items:baseline">
        <span style="width:10px;height:2px;background:${row.color ?? 'currentColor'};display:inline-block"></span>
        <strong>${escape(value)}</strong>
        <span style="opacity:.7">${escape(row.seriesName ?? '')}</span>
      </div>`;
    })
    .join('');

  return `<div style="font-size:11px;opacity:.7;margin-bottom:4px">${escape(head)}</div>${lines}`;
}

/**
 * Series names reach this from an API response, so they are untrusted text.
 * The tooltip is built as an HTML string by ECharts' own contract, which makes
 * escaping the caller's job rather than the DOM's.
 */
function escape(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}
