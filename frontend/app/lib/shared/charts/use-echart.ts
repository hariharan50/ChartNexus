import { useEffect, useRef, type RefObject } from 'react';
import { echarts, type ECharts, type EChartsCoreOption } from './echarts-modules';

interface Options {
  /** The option object to paint. A new object reference triggers a repaint. */
  option: EChartsCoreOption;
  /**
   * Changing this clears the instance before repainting.
   *
   * `setOption` merges, which is what keeps live updates smooth — but a merge
   * cannot retire axis and label *formatters*. When the meaning of the numbers
   * changes (the OI chart's contracts/lots toggle), pass a different key so the
   * chart is rebuilt from scratch instead of half-repainted.
   */
  resetKey?: string | undefined;
}

/**
 * ECharts lifecycle: init on mount, resize with the container, dispose on
 * unmount, and merge new options in between.
 *
 * Deliberately a plain `useEffect`, not `useLayoutEffect`: ECharts touches
 * canvas APIs that do not exist during SSR, and this matches the `onMount`
 * timing the Svelte version had.
 */
export function useEChart<T extends HTMLElement>(
  { option, resetKey }: Options,
  containerRef: RefObject<T | null>
): RefObject<ECharts | undefined> {
  const chartRef = useRef<ECharts | undefined>(undefined);
  const paintedKey = useRef<string | undefined>(undefined);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    const chart = echarts.init(el, undefined, { renderer: 'canvas' });
    chartRef.current = chart;
    paintedKey.current = undefined;

    const observer = new ResizeObserver(() => chart.resize());
    observer.observe(el);

    return () => {
      observer.disconnect();
      chart.dispose();
      chartRef.current = undefined;
    };
    // The container element is stable for the component's lifetime; re-running
    // this would tear down and rebuild the chart on every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;

    if (resetKey !== paintedKey.current) {
      chart.clear();
      chart.setOption(option);
      paintedKey.current = resetKey;
    } else {
      // `replaceMerge: ['series']` is what makes a poll cheap: axes, grid and
      // tooltip config are left alone, only the bars are swapped.
      chart.setOption(option, { replaceMerge: ['series'] });
    }
  }, [option, resetKey]);

  return chartRef;
}
