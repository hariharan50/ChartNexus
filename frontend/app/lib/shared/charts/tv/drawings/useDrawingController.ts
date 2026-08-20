import { useCallback, useEffect, useMemo, useRef, useState, type RefObject } from 'react';
import type { ISeriesApi, MouseEventParams, SeriesType, Time } from 'lightweight-charts';
import type { Candle, LwChartHandle } from '../LwChart';
import type { DrawingPrimitive } from './DrawingPrimitive';
import { buildPrimitive } from './factory';
import { barsBetween, candleAt, snapToCandle } from './snap';
import type { Drawing, DrawingPoint, DrawingTool, Measurement, TwoPointPrimitive } from './types';

let nextId = 0;
function newId(): string {
  nextId += 1;
  return `drawing-${nextId}`;
}

interface Options {
  handleRef: RefObject<LwChartHandle | null>;
  /** For magnet snapping and the measure tool's bar count. */
  candles: Candle[];
  /** `null` is the plain cursor — no tool selected. */
  tool: DrawingTool | null;
  /** Every tool here is single-shot: draw one, land back on the cursor. */
  onToolDone: () => void;
  magnet: boolean;
  /** Freezes the chart's drawings: no new ones, and clear-all refuses. */
  locked: boolean;
  visible: boolean;
  color: string;
  /**
   * Bumped by the host whenever `LwChart` builds a new chart and series — see
   * that component's `onReady`. Primitives belong to the series they were
   * attached to, so a rebuild (switching candle→line, say) invalidates every
   * one of them; without this the drawings would disappear on the switch and
   * never come back, since the reconciler below would still believe them
   * attached.
   */
  chartEpoch: number;
}

export interface MeasurementStats extends Measurement {
  deltaPrice: number;
  deltaPercent: number;
  bars: number;
}

export interface DrawingController {
  drawings: Drawing[];
  measurement: MeasurementStats | null;
  clearAll: () => void;
}

/**
 * Turns clicks on the chart into `Drawing`s, and keeps the attached
 * primitives in step with them.
 *
 * `lightweight-charts` has no drawing-tool concept of its own — this is what
 * stands in for it: `chart.subscribeClick`/`subscribeCrosshairMove` already
 * report the clicked point pre-converted to pane-relative pixels, which is
 * what `series.coordinateToPrice` needs, so there is no raw DOM event math to
 * get wrong here the way there would be listening on the container directly.
 *
 * One instance per chart cell (used from `ChartCell.tsx`), the same way that
 * component already owns its own replay and hover state — a drawing belongs
 * to the chart the reader drew it on, not to the page.
 */
export function useDrawingController({
  handleRef,
  candles,
  tool,
  onToolDone,
  magnet,
  locked,
  visible,
  color,
  chartEpoch
}: Options): DrawingController {
  const [drawings, setDrawings] = useState<Drawing[]>([]);
  const [measurement, setMeasurement] = useState<Measurement | null>(null);
  // The first click of a two-click tool, waiting for its second.
  const pendingRef = useRef<DrawingPoint | null>(null);
  // Committed primitives, kept in step with `drawings` by the effect below.
  const primitivesRef = useRef(new Map<string, DrawingPrimitive>());
  // The live in-progress shape, redrawn on every mouse move and thrown away
  // on commit or cancel — never part of `drawings`.
  const previewRef = useRef<DrawingPrimitive | null>(null);
  // The series everything above is currently attached to. Compared by identity
  // rather than trusting `chartEpoch` alone, so a detach is never attempted
  // against a series that has already been disposed.
  const attachedTo = useRef<ISeriesApi<SeriesType> | null>(null);

  // Everything the click/move handlers need but must not resubscribe for.
  // `candles` alone is a new array on every replay tick and every poll; reading
  // these through a ref is what keeps the subscription effect below firing once
  // per tool change instead of once per repaint.
  const latest = useRef({ candles, magnet, locked, color, onToolDone });
  latest.current = { candles, magnet, locked, color, onToolDone };

  const clearPreview = useCallback(() => {
    const preview = previewRef.current;
    previewRef.current = null;
    if (!preview) return;
    const api = handleRef.current?.getApi();
    // Only detach from the series it was actually attached to — after a rebuild
    // that series is gone, and the new one never knew about this primitive.
    if (api && api.series === attachedTo.current) api.series.detachPrimitive(preview);
  }, [handleRef]);

  // A tool switch (or turning drawing off entirely) abandons whatever was
  // half-drawn — a stale pending anchor from the last tool must not silently
  // attach itself to the next one.
  useEffect(() => {
    pendingRef.current = null;
    setMeasurement(null);
    clearPreview();
  }, [tool, clearPreview]);

  const toPoint = useCallback(
    (param: MouseEventParams<Time>): DrawingPoint | null => {
      const api = handleRef.current?.getApi();
      if (!api || param.time === undefined || param.point === undefined) return null;
      const rawPrice = api.series.coordinateToPrice(param.point.y);
      if (rawPrice === null) return null;
      const time = Number(param.time);
      const { candles: bars, magnet: snap } = latest.current;
      const price = snap ? snapToCandle(rawPrice, candleAt(bars, time)) : rawPrice;
      return { time, price };
    },
    [handleRef]
  );

  // Reconciles `drawings` against attached primitives — add what's new, drop
  // what's gone, and re-attach everything after a chart rebuild. The same
  // add/update/remove shape `LwChart`'s own overlay reconciler uses, and for
  // the same reason: a clear-and-readd would flash every drawing on every
  // edit rather than updating it in place.
  useEffect(() => {
    const api = handleRef.current?.getApi();
    if (!api) return;

    // A rebuilt series took the old primitives down with it. Forget them
    // without detaching — the object that owned them no longer exists — and let
    // the loop below re-attach a fresh set to the new series.
    if (attachedTo.current !== api.series) {
      primitivesRef.current.clear();
      previewRef.current = null;
      attachedTo.current = api.series;
    }

    for (const drawing of drawings) {
      let primitive = primitivesRef.current.get(drawing.id);
      if (!primitive) {
        primitive = buildPrimitive(drawing);
        primitivesRef.current.set(drawing.id, primitive);
        api.series.attachPrimitive(primitive);
      }
      // Only ever a repaint when something actually changed: `visible` is the
      // one attribute this reconciler owns, and a no-op assignment still costs
      // a full frame through `requestUpdate`.
      if (primitive.visible !== visible) {
        primitive.visible = visible;
        primitive.updateAllViews();
      }
    }

    if (primitivesRef.current.size > drawings.length) {
      const live = new Set(drawings.map((drawing) => drawing.id));
      for (const [id, primitive] of primitivesRef.current) {
        if (!live.has(id)) {
          api.series.detachPrimitive(primitive);
          primitivesRef.current.delete(id);
        }
      }
    }
  }, [drawings, visible, chartEpoch, handleRef]);

  // The click/move subscriptions that drive the draw-in-progress state
  // machine. Kept in its own effect, separate from the reconciler above, so a
  // mid-draw preview repaint never tears down and resubscribes the handlers.
  useEffect(() => {
    const api = handleRef.current?.getApi();
    if (!api || !tool) return;
    // Captured once, non-null, so the nested handlers below don't have to
    // re-check what the outer guard already established — TS can't carry a
    // narrowing across a function boundary, but a `const` copy survives it.
    const { chart, series } = api;
    const activeTool: DrawingTool = tool;

    function commit(a: DrawingPoint, b: DrawingPoint): void {
      const id = newId();
      const { color: stroke } = latest.current;
      const drawing: Drawing =
        activeTool === 'trendline'
          ? { id, kind: 'trendline', a, b, color: stroke }
          : activeTool === 'fib'
            ? { id, kind: 'fib', a, b, color: stroke }
            : activeTool === 'rectangle'
              ? { id, kind: 'rectangle', a, b, color: stroke }
              : activeTool === 'horizontal'
                ? { id, kind: 'horizontal', price: a.price, color: stroke }
                : {
                    id,
                    kind: 'text',
                    at: a,
                    text: window.prompt('Label text', '') ?? '',
                    color: stroke
                  };
      if (drawing.kind !== 'text' || drawing.text.trim() !== '') {
        setDrawings((current) => [...current, drawing]);
      }
    }

    function onClick(param: MouseEventParams<Time>): void {
      const point = toPoint(param);
      if (!point) return;
      // Locked means locked: measuring still works (it draws nothing), but
      // nothing new lands on a chart the reader has pinned.
      if (latest.current.locked && activeTool !== 'measure') return;

      // Single-click tools commit immediately — there is no second anchor to wait for.
      if (activeTool === 'horizontal' || activeTool === 'text') {
        commit(point, point);
        latest.current.onToolDone();
        return;
      }

      if (!pendingRef.current) {
        pendingRef.current = point;
        if (activeTool === 'measure') setMeasurement({ a: point, b: point });
        return;
      }

      const anchor = pendingRef.current;
      pendingRef.current = null;
      clearPreview();

      if (activeTool === 'measure') {
        setMeasurement({ a: anchor, b: point });
      } else {
        commit(anchor, point);
        latest.current.onToolDone();
      }
    }

    function onMove(param: MouseEventParams<Time>): void {
      const anchor = pendingRef.current;
      if (!anchor) return;
      const point = toPoint(param);
      if (!point) return;

      if (activeTool === 'measure') {
        setMeasurement((current) =>
          // The crosshair reports far more often than the readout changes —
          // several times per bar at any useful zoom. Re-rendering the readout
          // with the numbers it already shows is the one avoidable cost on this
          // path, so bail out when the far anchor has not actually moved.
          current && current.b.time === point.time && current.b.price === point.price
            ? current
            : { a: anchor, b: point }
        );
        return;
      }

      // A live preview of the shape being drawn, reusing the same primitive
      // classes the committed drawing will use — so what the reader sees
      // while dragging is exactly what they'll get on release.
      if (!previewRef.current) {
        const { color: stroke } = latest.current;
        const preview = buildPrimitive(
          activeTool === 'trendline'
            ? { id: 'preview', kind: 'trendline', a: anchor, b: point, color: stroke }
            : activeTool === 'fib'
              ? { id: 'preview', kind: 'fib', a: anchor, b: point, color: stroke }
              : { id: 'preview', kind: 'rectangle', a: anchor, b: point, color: stroke }
        );
        previewRef.current = preview;
        series.attachPrimitive(preview);
      } else {
        const preview = previewRef.current as unknown as TwoPointPrimitive;
        preview.a = anchor;
        preview.b = point;
        previewRef.current.updateAllViews();
      }
    }

    function onKeyDown(event: KeyboardEvent): void {
      if (event.key !== 'Escape') return;
      pendingRef.current = null;
      setMeasurement(null);
      clearPreview();
    }

    chart.subscribeClick(onClick);
    chart.subscribeCrosshairMove(onMove);
    document.addEventListener('keydown', onKeyDown);
    return () => {
      chart.unsubscribeClick(onClick);
      chart.unsubscribeCrosshairMove(onMove);
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [handleRef, tool, chartEpoch, toPoint, clearPreview]);

  const clearAll = useCallback(() => {
    if (latest.current.locked) return;
    setDrawings((current) => (current.length === 0 ? current : []));
  }, []);

  const measurementStats = useMemo<MeasurementStats | null>(() => {
    if (!measurement) return null;
    const { a, b } = measurement;
    const deltaPrice = b.price - a.price;
    const deltaPercent = a.price === 0 ? 0 : (deltaPrice / a.price) * 100;
    const lo = Math.min(a.time, b.time);
    const hi = Math.max(a.time, b.time);
    return { a, b, deltaPrice, deltaPercent, bars: barsBetween(candles, lo, hi) };
  }, [measurement, candles]);

  return { drawings, measurement: measurementStats, clearAll };
}
