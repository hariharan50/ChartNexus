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
  /**
   * Charts sharing a group id share one axis pointer.
   *
   * Stacked charts over the same time axis have to move together — a crosshair
   * that reads 11:30 on one and nothing on the two below it is worse than no
   * crosshair, because the eye still tries to compare them.
   */
  group?: string | undefined;
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
  { option, resetKey, group }: Options,
  containerRef: RefObject<T | null>
): RefObject<ECharts | undefined> {
  const chartRef = useRef<ECharts | undefined>(undefined);
  const paintedKey = useRef<string | undefined>(undefined);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    // SVG so the chart stays sharp through a browser zoom or a display-scaling
    // change — see the renderer note in `echarts-modules.ts`. Nothing here
    // depends on canvas-only APIs (`getDataURL` and friends are unused).
    const chart = echarts.init(el, undefined, { renderer: 'svg' });
    chartRef.current = chart;
    paintedKey.current = undefined;

    if (group) {
      chart.group = group;
      // Idempotent: connecting an already-connected group is a no-op, so each
      // chart in the group can call it as it mounts without coordinating.
      echarts.connect(group);
    }

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
