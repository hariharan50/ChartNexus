import type { EChartsCoreOption } from './echarts-modules';

/**
 * Settings › Global › Show chart tooltip, as an option transform.
 *
 * `showContent: false` rather than `show: false`, and the difference matters:
 *
 * - `show: false` removes the tooltip component outright, and with it the axis
 *   pointer and the `updateAxisPointer` event. Gamma Exposure reads that event
 *   to drive the readout panel beside its plot, so switching the tooltip off
 *   would have left that page's panel dead on hover.
 * - `showContent: false` suppresses only the floating box. The shadow band
 *   still says which strike is under the cursor, and every page that reads the
 *   hover somewhere other than a tooltip keeps working.
 *
 * The preference is about the box that covers the chart, not about losing
 * track of where the pointer is — Gamma Exposure already ships `showContent:
 * false` for exactly that reason, which is where this reading comes from.
 *
 * Pure, and applied in `EChart` rather than in each `charts/options/` builder:
 * one seam every chart already passes through, so a chart added tomorrow obeys
 * the preference without its author knowing it exists.
 */
export function withoutTooltipContent(option: EChartsCoreOption): EChartsCoreOption {
  const tooltip = (option as { tooltip?: unknown }).tooltip;
  if (tooltip === undefined || tooltip === null) return option;

  const suppress = (one: unknown) =>
    typeof one === 'object' && one !== null ? { ...(one as object), showContent: false } : one;

  return {
    ...option,
    tooltip: Array.isArray(tooltip) ? tooltip.map(suppress) : suppress(tooltip)
  };
}
