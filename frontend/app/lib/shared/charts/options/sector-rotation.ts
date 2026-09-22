import type { EChartsCoreOption } from '../echarts-modules';
import { withAlpha } from '../theme/tokens';
import type { ChartTheme } from '../theme/types';

/**
 * Where each sector sits relative to its index, this session.
 *
 * A bubble plot with a quadrant grid: **x** is relative strength (the sector's
 * weight-averaged move minus the index's own), **y** is participation (the
 * share of its members advancing, re-centred on 50), and **area** is the
 * sector's index weight. Three encodings at once is exactly what a scatter is
 * for, and no bar chart arrangement shows all three.
 *
 * **Colour is redundant here, on purpose.** A point's quadrant is already
 * given by where it sits, so the four hues repeat information the geometry
 * carries — which is what makes them safe: nothing is lost if two of them are
 * confused. That also sidesteps the all-pairs colour-separation problem a
 * scatter normally has with a categorical palette, because these are status
 * colours (bullish, bearish, accent, warning) rather than identity slots.
 *
 * **Area, not radius.** Bubble size runs through a square root so a 30%-weight
 * sector looks three times a 3% one rather than ten times — the eye reads
 * area, and scaling the radius by the value exaggerates by squaring it.
 *
 * **This is not a classical RRG.** A real relative-rotation graph plots
 * RS-Ratio against RS-*Momentum* and traces a multi-week tail through the
 * quadrants. That needs weeks of stored constituent history the application
 * does not keep. Participation is a defensible one-session stand-in — a sector
 * carried by one heavyweight while the rest of it sinks is a different animal
 * from one where everything is bid — and the page says "participation", never
 * "momentum", and draws no tail.
 */

export interface RotationPoint {
  sector: string;
  /** Percentage points ahead of (or behind) the index — the x axis. */
  relativeStrength: number;
  /** Share advancing minus 50, so zero is neutral — the y axis. */
  participationOffset: number;
  /** Index weight, which sizes the bubble. */
  weightPercent: number;
  changePercent: number;
  advancing: number;
  declining: number;
  members: number;
  quadrant: 'leading' | 'improving' | 'weakening' | 'lagging';
  leaders: string[];
  laggards: string[];
}

export interface RotationOptions {
  formatPercent: (value: number) => string;
}

/** Smallest and largest bubble, in pixels. Both tuned to stay hoverable. */
const MIN_SYMBOL = 14;
const MAX_SYMBOL = 56;

/** Axis half-width floor, so a flat session does not zoom into the noise. */
const MIN_STRENGTH_SPAN = 1;

function quadrantColor(quadrant: RotationPoint['quadrant'], theme: ChartTheme): string {
  switch (quadrant) {
    case 'leading':
      return theme.call;
    case 'lagging':
      return theme.put;
    case 'improving':
      return theme.accent;
    case 'weakening':
      return theme.marker;
  }
}

export function buildSectorRotationOption(
  points: RotationPoint[],
  theme: ChartTheme,
  options: RotationOptions
): EChartsCoreOption {
  const { formatPercent } = options;
  const span = strengthSpan(points);
  const heaviest = Math.max(...points.map((point) => point.weightPercent), 1);

  return {
    backgroundColor: 'transparent',
    grid: { left: 8, right: 24, top: 24, bottom: 8, containLabel: true },
    tooltip: {
      trigger: 'item',
      appendTo: 'body',
      backgroundColor: theme.tooltipBg,
      borderColor: theme.grid,
      textStyle: { color: theme.tooltipText, fontSize: 12 },
      padding: [8, 12],
      formatter: (params: unknown) => {
        const hit = params as { dataIndex: number };
        const point = points[hit.dataIndex];
        if (!point) return '';
        const movers = [
          point.leaders.length ? `Up: ${point.leaders.join(', ')}` : '',
          point.laggards.length ? `Down: ${point.laggards.join(', ')}` : ''
        ]
          .filter(Boolean)
          .map((line) => `<div style="color:${theme.axis}">${line}</div>`)
          .join('');
        return `
          <div style="font-weight:700;margin-bottom:4px">${point.sector}</div>
          <div>Move: ${formatPercent(point.changePercent)}</div>
          <div>vs index: ${formatPercent(point.relativeStrength)} pts</div>
          <div>Advancing: ${point.advancing} of ${point.members}</div>
          <div>Weight: ${point.weightPercent.toFixed(2)}%</div>
          ${movers}`;
      }
    },
    xAxis: {
      type: 'value',
      name: 'Relative strength',
      nameLocation: 'end',
      nameGap: 8,
      nameTextStyle: { color: theme.axis, fontSize: 10 },
      min: -span,
      max: span,
      splitLine: { lineStyle: { color: theme.grid, type: 'dashed' } },
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: {
        color: theme.axis,
        fontSize: 11,
        formatter: (value: number) => `${value > 0 ? '+' : ''}${value.toFixed(1)}`
      }
    },
    yAxis: {
      type: 'value',
      name: 'Participation',
      nameLocation: 'end',
      nameGap: 10,
      nameTextStyle: { color: theme.axis, fontSize: 10 },
      // Fixed to the full range the measure can take. An auto-scaled
      // participation axis would move the neutral line from session to
      // session, and the whole chart is read against that line.
      min: -50,
      max: 50,
      splitLine: { lineStyle: { color: theme.grid, type: 'dashed' } },
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: {
        color: theme.axis,
        fontSize: 11,
        formatter: (value: number) => `${(value + 50).toFixed(0)}%`
      }
    },
    series: [
      {
        type: 'scatter',
        data: points.map((point) => ({
          value: [point.relativeStrength, point.participationOffset],
          itemStyle: {
            color: withAlpha(quadrantColor(point.quadrant, theme), 0.75),
            // A 2px ring in the surface colour, so overlapping bubbles stay
            // countable instead of merging into one blob.
            borderColor: theme.surface,
            borderWidth: 2
          }
        })),
        symbolSize: (value: unknown, params: unknown) => {
          const index = (params as { dataIndex: number }).dataIndex;
          const weight = points[index]?.weightPercent ?? 0;
          // Square root: the eye reads area, so scaling the radius linearly
          // would exaggerate a heavy sector by squaring its weight.
          const scale = Math.sqrt(Math.max(weight, 0) / heaviest);
          return MIN_SYMBOL + (MAX_SYMBOL - MIN_SYMBOL) * scale;
        },
        label: {
          // Direct labels rather than a legend: the identity of a bubble is
          // its sector name, and a twelve-entry legend beside a twelve-bubble
          // plot is a lookup table nobody should have to use.
          show: true,
          position: 'inside',
          color: theme.tooltipText,
          fontSize: 10,
          fontWeight: 600,
          formatter: (params: unknown) => {
            const index = (params as { dataIndex: number }).dataIndex;
            return points[index]?.sector ?? '';
          }
        },
        markLine: {
          silent: true,
          symbol: 'none',
          // The two axes the quadrants are defined by. Solid and in the axis
          // colour, because everything on this chart is read against them.
          data: [{ xAxis: 0 }, { yAxis: 0 }],
          lineStyle: { color: theme.axis, width: 1 },
          label: { show: false }
        },
        markArea: {
          silent: true,
          data: quadrantBands(span, theme)
        }
      }
    ]
  };
}

/**
 * A symmetric x range that always contains every point.
 *
 * Symmetric because the origin is the index itself: an axis running -0.2 to
 * +3.0 would put the index off-centre and make a broadly strong session look
 * like a balanced one.
 */
function strengthSpan(points: RotationPoint[]): number {
  const widest = Math.max(
    ...points.map((point) => Math.abs(point.relativeStrength)),
    MIN_STRENGTH_SPAN
  );
  return Number((widest * 1.25).toFixed(2));
}

/** The four tinted quadrants, faint enough to sit under the bubbles. */
function quadrantBands(span: number, theme: ChartTheme) {
  const tint = (color: string) => ({ itemStyle: { color: withAlpha(color, 0.06) } });
  return [
    [
      { ...tint(theme.call), xAxis: 0, yAxis: 0 },
      { xAxis: span, yAxis: 50 }
    ],
    [
      { ...tint(theme.accent), xAxis: -span, yAxis: 0 },
      { xAxis: 0, yAxis: 50 }
    ],
    [
      { ...tint(theme.marker), xAxis: 0, yAxis: -50 },
      { xAxis: span, yAxis: 0 }
    ],
    [
      { ...tint(theme.put), xAxis: -span, yAxis: -50 },
      { xAxis: 0, yAxis: 0 }
    ]
  ];
}
