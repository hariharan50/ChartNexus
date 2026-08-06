import type { EChartsCoreOption } from '../echarts-modules';
import type { ChartTheme } from '../theme/types';

/**
 * The sentiment gauge on the Max Pain page, in TradingView's "Summary" styling.
 *
 * A half circle over five zones — Strong sell through Strong buy — drawn as a
 * pale track with a gradient arc filled up to the needle. What it measures is
 * the **signed** gap between spot and max pain, which is why it replaced the
 * donut it grew out of: a ring can only show magnitude, and direction is the
 * whole signal here.
 *
 * Pure, like its siblings in this folder: it takes an already-derived 0–1
 * position and returns an ECharts option. Which zone that position falls in is
 * decided in `max-pain-data.ts` and passed in, so the arc and the word beneath
 * it read the same number.
 */

/** Zone names, left (most bearish) to right (most bullish). */
const ZONE_LABELS = ['Strong sell', 'Sell', 'Neutral', 'Buy', 'Strong buy'] as const;

/** Midpoint of each fifth — the only axis positions that carry a label. */
const MIDPOINTS = [0.1, 0.3, 0.5, 0.7, 0.9];

/**
 * The filled arc's ramp, red at the bearish end through to indigo at the
 * bullish one.
 *
 * A gradient rather than five painted bands, because the bands are already
 * named around the rim: colouring them too would say the same thing twice and
 * leave five hard edges competing with the needle for attention.
 */
const RAMP = [
  { offset: 0, color: '#ef4444' },
  { offset: 0.4, color: '#c026a3' },
  { offset: 0.7, color: '#7c3aed' },
  { offset: 1, color: '#4f46e5' }
];

export interface MaxPainGaugeInput {
  /**
   * 0–1 across the arc: 0.5 is spot exactly on max pain, 0 and 1 are the ends
   * of the range the page considers a full move.
   */
  position: number;
  /** Signed gap between spot and max pain, in percent — the centre readout. */
  gapPct: number;
  /** Which zone `position` falls in, so the right rim label can be picked out. */
  zone: string;
  /** The zone's colour, shared with the verdict rendered beneath the gauge. */
  zoneColor: string;
}

export function buildMaxPainGaugeOption(
  input: MaxPainGaugeInput,
  theme: ChartTheme
): EChartsCoreOption {
  const { position, gapPct, zone, zoneColor } = input;

  return {
    backgroundColor: 'transparent',
    series: [
      {
        type: 'gauge',
        // A half circle, reading left-to-right from bearish to bullish — the
        // same direction as the price axis on every other chart here.
        startAngle: 180,
        endAngle: 0,
        min: 0,
        max: 1,
        center: ['50%', '72%'],
        // Short of the box on purpose: the zone names sit *outside* the arc, so
        // the last of the radius is the room they need.
        radius: '78%',
        // The unreached part of the scale. Pale rather than absent: the arc has
        // to read as a fraction of something.
        axisLine: {
          roundCap: true,
          lineStyle: { width: 14, color: [[1, theme.grid]] }
        },
        progress: {
          show: true,
          roundCap: true,
          width: 14,
          itemStyle: {
            color: {
              type: 'linear',
              // Across the arc's bounding box, so the ramp runs bearish-end to
              // bullish-end regardless of where the needle stops.
              x: 0,
              y: 0,
              x2: 1,
              y2: 0,
              colorStops: RAMP
            }
          }
        },
        pointer: {
          // A plain tapered needle. The reference's is a bare line from a pivot
          // dot, which reads more precisely than a wedge at this size.
          icon: 'path://M2.9,0.7L2.9,0.7c1.2,0,2.2,1,2.2,2.2v50c0,1.2-1,2.2-2.2,2.2l0,0c-1.2,0-2.2-1-2.2-2.2V2.9C0.7,1.7,1.7,0.7,2.9,0.7z',
          length: '62%',
          width: 4,
          offsetCenter: [0, 0],
          // From the theme, not the black of the reference: a hardcoded black
          // needle disappears against the dark and terminal themes.
          itemStyle: { color: theme.tooltipText }
        },
        anchor: {
          show: true,
          size: 12,
          showAbove: true,
          itemStyle: { color: theme.tooltipText }
        },
        axisTick: { show: false },
        splitLine: { show: false },
        axisLabel: {
          // Negative distance pushes the zone names outside the arc, as in the
          // reference. Only the five midpoints are labelled.
          distance: -26,
          color: theme.axis,
          fontSize: 11,
          rotate: 'tangential',
          formatter: (value: number) => {
            const i = MIDPOINTS.findIndex((mid) => Math.abs(value - mid) < 1e-6);
            if (i < 0) return '';
            const text = ZONE_LABELS[i]!;
            // The reading itself is picked out; the other four recede. Done
            // with a rich style rather than a colour callback, which ECharts
            // supports far less consistently across versions.
            return text === zone ? `{active|${text}}` : text;
          },
          rich: { active: { color: zoneColor, fontSize: 11, fontWeight: 700 } }
        },
        // No `title`: the verdict under the gauge is markup, so it survives into
        // a screen reader and a find-in-page. Two of them would just repeat.
        detail: {
          offsetCenter: [0, '42%'],
          color: zoneColor,
          fontSize: 24,
          fontWeight: 700,
          // The reading people act on is the gap, not the 0–1 arc position.
          formatter: () => `${gapPct >= 0 ? '+' : ''}${gapPct.toFixed(2)}%`
        },
        // Ten splits so the label midpoints (every 0.1) land on real axis
        // positions; nothing is drawn at them.
        splitNumber: 10,
        data: [{ value: position }]
      }
    ]
  };
}
