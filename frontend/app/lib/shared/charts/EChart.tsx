import { useEffect, useMemo, useRef, type CSSProperties } from 'react';
import { cx } from '$shared/ui/cx';
import { usePreferencesStore } from '$shared/ui/preferences-store';
import { useReducedMotion } from '$shared/ui/use-reduced-motion';
import type { EChartsCoreOption } from './echarts-modules';
import s from './EChart.module.css';
import { withMotionDefaults } from './motion-preference';
import { withoutTooltipContent } from './tooltip-preference';
import { useEChart } from './use-echart';

interface Props {
  /**
   * Built by a pure function in `charts/options/`, never assembled inline.
   * Keeping option construction out of the component is what makes chart
   * behaviour testable without a DOM.
   */
  option: EChartsCoreOption;
  /** See `useEChart` — changing this rebuilds rather than merges. */
  resetKey?: string | undefined;
  /** See `useEChart` — charts sharing a group share one crosshair. */
  group?: string | undefined;
  className?: string | undefined;
  style?: CSSProperties | undefined;
  /**
   * Which category the axis pointer is on, or `null` once it leaves.
   *
   * For pages that read the hovered point somewhere other than a floating
   * tooltip — Gamma Exposure puts it in a panel beside the plot, so the readout
   * never covers the bars it describes. Deliberately narrower than exposing the
   * ECharts instance: callers get the one fact they need without every page
   * growing its own event wiring.
   */
  onAxisHover?: ((dataIndex: number | null) => void) | undefined;
}

/**
 * The app's only ECharts mount point.
 *
 * On the server this renders the sized container and nothing else, so the
 * layout is identical before and after hydration and the chart never causes a
 * shift when it appears.
 *
 * Being the only mount point is also what makes Settings › Global › Show chart
 * tooltip a one-line preference rather than a flag threaded through twenty
 * option builders: it is applied here, to whatever option arrives.
 */
export default function EChart({ option, resetKey, group, className, style, onAxisHover }: Props) {
  const container = useRef<HTMLDivElement>(null);
  const showTooltip = usePreferencesStore((state) => state.showChartTooltip);
  const reducedMotion = useReducedMotion();

  const painted = useMemo(() => {
    const motioned = withMotionDefaults(option, reducedMotion);
    return showTooltip ? motioned : withoutTooltipContent(motioned);
  }, [option, showTooltip, reducedMotion]);

  /*
   * Flipping the preference has to *rebuild*, not merge.
   *
   * `setOption` merges, and a merge can set `showContent: false` but cannot
   * clear it again — switching tooltips back on would have left every chart
   * mounted at the time still silent. Folding the preference into the reset
   * key routes the change through `chart.clear()` instead.
   *
   * The key is left exactly as the caller gave it while tooltips are on and
   * motion is allowed, which is the default and every server render: a chart
   * that is not toggling must not take a different paint path because this line
   * exists.
   *
   * Reduced motion rides the same seam for the same reason. `animation: false`
   * merges in cleanly but cannot be merged back out, so a visitor turning the
   * preference off again would otherwise have been left with every mounted
   * chart permanently still.
   */
  const paintKey =
    showTooltip && !reducedMotion
      ? resetKey
      : `${resetKey ?? ''}${showTooltip ? '' : ' :no-tooltip'}${reducedMotion ? ' :still' : ''}`;

  const chartRef = useEChart({ option: painted, resetKey: paintKey, group }, container);
  // Through a ref so the subscription below is installed once, rather than
  // being torn down and re-added every time the parent re-renders with a fresh
  // inline callback.
  const hoverRef = useRef(onAxisHover);
  hoverRef.current = onAxisHover;

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;
    // `updateAxisPointer` rather than `mouseover`: it fires for the axis as a
    // whole, so it reports the hovered category even when the pointer is in the
    // empty space above a short bar.
    const onMove = (params: unknown) => {
      const index = (params as { dataIndex?: number }).dataIndex;
      hoverRef.current?.(typeof index === 'number' ? index : null);
    };
    const onOut = () => hoverRef.current?.(null);
    chart.on('updateAxisPointer', onMove);
    chart.on('globalout', onOut);
    return () => {
      chart.off('updateAxisPointer', onMove);
      chart.off('globalout', onOut);
    };
  }, [chartRef]);

  return <div ref={container} className={cx(s.chart, className)} style={style} />;
}
