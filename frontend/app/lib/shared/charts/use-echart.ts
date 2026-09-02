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

    const releaseAxisDrag = installAxisDrag(chart, el);

    const observer = new ResizeObserver(() => chart.resize());
    observer.observe(el);

    return () => {
      releaseAxisDrag();
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
      //
      // The zoom *window* is stripped from the merge, though the rest of the
      // dataZoom config still merges. The window in a freshly built option is
      // the one the page asked for (the whole session, or a Time Range chip),
      // so merging it would snap a reader who had zoomed into 11:00–14:00 back
      // out — every poll, mid-read. Dropping the component wholesale does not
      // work either: the chart then re-derives the window from the replaced
      // series and lands back on the full session. A rebuild (`resetKey`) still
      // carries the window, which is how the chips and Reset zoom take effect.
      chart.setOption(withoutZoomWindow(option), { replaceMerge: ['series'] });
    }
  }, [option, resetKey]);

  return chartRef;
}

/**
 * Drag the clock strip under the plot to change how much time is on screen.
 *
 * The window's right edge — the newest reading — stays put and the left edge
 * comes with the pointer: drag left and the session stretches out (more time on
 * screen), drag right and it squeezes in. It is the gesture every trading chart
 * puts on its time axis, and it is the one thing the wheel is bad at, because
 * the wheel zooms around wherever the pointer happens to be.
 *
 * Written by hand because ECharts has no axis-drag: `dataZoom` covers the wheel
 * and the in-plot pan, and its slider is a bar of chrome under the chart rather
 * than the axis itself. Everything here is public API — the current window comes
 * off `getOption`, the new one goes back through `dispatchAction`, which
 * `echarts.connect` then mirrors to the rest of the group.
 *
 * Charts with no `dataZoom` never see any of it: the handler finds no window and
 * returns, so a static chart keeps its plain cursor and its text selection.
 */
function installAxisDrag(chart: ECharts, el: HTMLElement): () => void {
  /** The clock strip: below the plot rectangle, above the container's edge. */
  const onAxis = (event: PointerEvent): boolean => {
    const box = el.getBoundingClientRect();
    const y = event.clientY - box.top;
    return y >= plotBottom(chart, box.height) && y <= box.height;
  };

  const currentWindow = (): { start: number; end: number } | null => {
    const zooms = (chart.getOption() as { dataZoom?: { start?: number; end?: number }[] }).dataZoom;
    const zoom = zooms?.[0];
    return zoom?.start != null && zoom.end != null ? { start: zoom.start, end: zoom.end } : null;
  };

  let from: { x: number; start: number; end: number } | null = null;

  const onDown = (event: PointerEvent) => {
    if (event.button !== 0 || !onAxis(event)) return;
    const open = currentWindow();
    if (!open) return;
    from = { x: event.clientX, ...open };
    el.setPointerCapture(event.pointerId);
    // Otherwise the drag selects the axis labels and the panel text past them.
    event.preventDefault();
  };

  const onMove = (event: PointerEvent) => {
    if (!from) {
      el.style.cursor = onAxis(event) ? 'ew-resize' : '';
      return;
    }
    const travelled = (event.clientX - from.x) / (el.clientWidth || 1);
    const open = from.end - from.start;
    // Percentages of the session, so the ends clamp themselves: a drag can never
    // ask for a window wider than the data or narrower than a few minutes.
    const span = Math.min(100, Math.max(MIN_ZOOM_SPAN, open * (1 - travelled * AXIS_DRAG_GAIN)));
    chart.dispatchAction({
      type: 'dataZoom',
      dataZoomIndex: 0,
      start: Math.max(0, from.end - span),
      end: from.end
    });
  };

  const onUp = (event: PointerEvent) => {
    if (!from) return;
    from = null;
    el.releasePointerCapture(event.pointerId);
  };

  el.addEventListener('pointerdown', onDown);
  el.addEventListener('pointermove', onMove);
  el.addEventListener('pointerup', onUp);
  el.addEventListener('pointercancel', onUp);

  return () => {
    el.removeEventListener('pointerdown', onDown);
    el.removeEventListener('pointermove', onMove);
    el.removeEventListener('pointerup', onUp);
    el.removeEventListener('pointercancel', onUp);
  };
}

/**
 * Where the plot rectangle stops, in pixels from the top of the container.
 *
 * Read off the live grid rather than guessed from the option, so a chart whose
 * axis labels wrapped or whose panel resized still hands back the real edge.
 * `getModel` is not in the published typings; the fallback is the axis strip a
 * default `grid.bottom` plus one line of 11px labels comes to.
 */
function plotBottom(chart: ECharts, height: number): number {
  const model = (chart as unknown as { getModel?: () => GridLookup }).getModel?.();
  const rect = model?.getComponent?.('grid', 0)?.coordinateSystem?.getRect?.();
  return rect ? rect.y + rect.height : height - AXIS_STRIP;
}

interface GridLookup {
  getComponent?: (
    type: string,
    index: number
  ) => { coordinateSystem?: { getRect?: () => { y: number; height: number } } } | undefined;
}

/** How hard the axis drag bites: a full-width drag is roughly a 1.6x rescale. */
const AXIS_DRAG_GAIN = 1.6;
/** The narrowest window a drag may leave, as a share of the session. */
const MIN_ZOOM_SPAN = 2;
/** Fallback strip height when the grid rect cannot be read. */
const AXIS_STRIP = 34;

/** The option minus each dataZoom's start/end, so a merge leaves the window be. */
function withoutZoomWindow(option: EChartsCoreOption): EChartsCoreOption {
  const zooms = (option as { dataZoom?: unknown }).dataZoom;
  if (!Array.isArray(zooms)) return option;
  return {
    ...option,
    dataZoom: zooms.map((zoom) => {
      const {
        start: _start,
        end: _end,
        startValue: _startValue,
        endValue: _endValue,
        ...rest
      } = zoom as Record<string, unknown>;
      return rest;
    })
  };
}
