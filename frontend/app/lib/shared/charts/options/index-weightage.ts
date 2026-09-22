import type { EChartsCoreOption } from '../echarts-modules';
import { seriesPalette } from '../theme/tokens';
import type { ChartTheme } from '../theme/types';

/**
 * How an index's weight is distributed, as a donut.
 *
 * A pie is the wrong chart for almost everything and the right one here: the
 * question is literally "what share of the whole is this", the slices sum to a
 * meaningful 100%, and the count is capped so no slice is a sliver. A donut
 * rather than a full pie because the hole carries the total — the number a
 * reader wants first — without a second element competing for the centre.
 *
 * **Eight slices, hard.** The categorical palette has eight slots assigned in
 * a fixed order, and a ninth category is never a generated hue: the caller
 * folds the tail into "Other" before it gets here (see `foldToSlots`). Folding
 * rather than truncating is what keeps the slices summing to the whole.
 *
 * **Colour is never the only label.** On the app's light themes three of the
 * palette slots sit below 3:1 against the surface, so this chart always ships
 * with its labelled table beside it and every slice carries a direct label.
 * That is a requirement of the palette, not a stylistic choice.
 */

export interface WeightageSlice {
  label: string;
  /** Share of the priced index, 0-100. */
  share: number;
  /** How many index members this slice stands for. */
  members: number;
  /** Weight-averaged move of those members, or null when unmeasured. */
  changePercent: number | null;
}

export interface WeightageOptions {
  /** Drawn in the hole — the whole this chart is a share of. */
  centreLabel: string;
  centreValue: string;
  formatPercent: (value: number | null) => string;
}

export function buildWeightageOption(
  slices: WeightageSlice[],
  theme: ChartTheme,
  options: WeightageOptions
): EChartsCoreOption {
  const palette = seriesPalette(theme);

  return {
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'item',
      appendTo: 'body',
      backgroundColor: theme.tooltipBg,
      borderColor: theme.grid,
      textStyle: { color: theme.tooltipText, fontSize: 12 },
      padding: [8, 12],
      formatter: (params: unknown) => {
        const hit = params as { dataIndex: number };
        const slice = slices[hit.dataIndex];
        if (!slice) return '';
        const members = slice.members === 1 ? '1 member' : `${slice.members} members`;
        return `
          <div style="font-weight:700;margin-bottom:4px">${slice.label}</div>
          <div>${slice.share.toFixed(2)}% of index · ${members}</div>
          <div>Move: ${options.formatPercent(slice.changePercent)}</div>`;
      }
    },
    series: [
      {
        type: 'pie',
        // A donut, not a pie: the hole holds the total.
        radius: ['58%', '84%'],
        center: ['50%', '50%'],
        avoidLabelOverlap: true,
        // A 2px ring in the surface colour between slices, so two adjacent
        // hues read as two slices rather than one gradient.
        itemStyle: { borderColor: theme.surface, borderWidth: 2 },
        label: {
          // Direct labels on every slice — the relief the palette requires on
          // the light themes, and a faster read than a legend on every theme.
          show: true,
          color: theme.axis,
          fontSize: 11,
          formatter: (params: unknown) => {
            const hit = params as { dataIndex: number };
            const slice = slices[hit.dataIndex];
            return slice ? `${slice.label}\n${slice.share.toFixed(1)}%` : '';
          }
        },
        labelLine: { lineStyle: { color: theme.grid }, length: 8, length2: 10 },
        emphasis: { scale: false, itemStyle: { borderWidth: 2 } },
        data: slices.map((slice, index) => ({
          name: slice.label,
          value: slice.share,
          // Fixed order, never cycled: the fold guarantees there are never
          // more slices than slots, so the modulo is a belt-and-braces guard
          // rather than a rotation anyone should rely on.
          itemStyle: { color: palette[index % palette.length] }
        }))
      }
    ],
    // The hole's contents. Graphic rather than a pie label so it stays put
    // when a slice is hovered.
    graphic: [
      {
        type: 'text',
        left: 'center',
        top: '46%',
        style: {
          text: options.centreValue,
          fill: theme.tooltipText,
          fontSize: 20,
          fontWeight: 700,
          textAlign: 'center'
        }
      },
      {
        type: 'text',
        left: 'center',
        top: '57%',
        style: {
          text: options.centreLabel,
          fill: theme.axis,
          fontSize: 11,
          textAlign: 'center'
        }
      }
    ]
  };
}
