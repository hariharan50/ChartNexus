import { useEffect, useRef, type CSSProperties } from 'react';
import { cx } from '$shared/ui/cx';
import type { EChartsCoreOption } from './echarts-modules';
import s from './EChart.module.css';
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
 */
export default function EChart({ option, resetKey, group, className, style, onAxisHover }: Props) {
  const container = useRef<HTMLDivElement>(null);
  const chartRef = useEChart({ option, resetKey, group }, container);
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
