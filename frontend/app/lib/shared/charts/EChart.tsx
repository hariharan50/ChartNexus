import { useRef, type CSSProperties } from 'react';
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
  className?: string | undefined;
  style?: CSSProperties | undefined;
}

/**
 * The app's only ECharts mount point.
 *
 * On the server this renders the sized container and nothing else, so the
 * layout is identical before and after hydration and the chart never causes a
 * shift when it appears.
 */
export default function EChart({ option, resetKey, className, style }: Props) {
  const container = useRef<HTMLDivElement>(null);
  useEChart({ option, resetKey }, container);

  return <div ref={container} className={cx(s.chart, className)} style={style} />;
}
