import type { EChartsCoreOption } from './echarts-modules';

/**
 * Chart motion, as an option transform.
 *
 * **Why this exists.** ECharts animates every data update over its own default
 * of 1000ms with `cubicOut`. Twenty-one builders live in `charts/options/` and
 * eighteen of them never said otherwise, so nearly every chart in the app was
 * settling for a full second while the surrounding UI moved in 120-320ms. On a
 * terminal that refetches on a timer, a one-second settle is also long enough
 * that the next update can arrive mid-animation.
 *
 * 260ms is the figure `futures-heatmap.ts` had already arrived at
 * independently, and it is `--cn-duration-slow` rounded to the frame — the
 * chart is the largest thing on the page, so it gets the slowest tier of the
 * scale rather than the default one.
 *
 * **Reduced motion is the real reason this is not just a CSS change.** The
 * global `prefers-reduced-motion` block in `app.css` flattens every CSS
 * duration with `!important`, but ECharts animates inside a canvas/SVG surface
 * that no stylesheet can reach. Without this transform, the charts were the one
 * part of the product that ignored the preference outright.
 *
 * Deliberately does not overwrite a builder that has already decided: the three
 * that configure animation themselves — two `animation: false`, one explicit
 * duration — keep what they set. This is a default, not a policy.
 */
export function withMotionDefaults(option: EChartsCoreOption, reduced: boolean): EChartsCoreOption {
  const declared = option as {
    animation?: unknown;
    animationDuration?: unknown;
    animationDurationUpdate?: unknown;
  };

  // Reduced motion overrides even an explicit duration: a builder asking for
  // 600ms is expressing a house style, not overriding an accessibility
  // preference. `animation: false` renders the final state immediately.
  if (reduced) return { ...option, animation: false };

  // A builder that has spoken for itself is left exactly as it is — including
  // `animation: false`, which must not be revived into a 260ms fade.
  if (
    declared.animation !== undefined ||
    declared.animationDuration !== undefined ||
    declared.animationDurationUpdate !== undefined
  ) {
    return option;
  }

  return {
    ...option,
    animationDuration: CHART_DURATION,
    animationEasing: 'cubicOut',
    // The update path matters more than the initial one here: a quote board
    // repaints far more often than it mounts.
    animationDurationUpdate: CHART_DURATION,
    animationEasingUpdate: 'cubicOut'
  };
}

/** Mirrors `--cn-duration-slow` (320ms) at the nearest frame boundary. */
export const CHART_DURATION = 260;
