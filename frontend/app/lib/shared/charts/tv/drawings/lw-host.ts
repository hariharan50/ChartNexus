/**
 * The lightweight-charts adapter — tier 2.
 *
 * The engine asks for five inbound pointer events, a way to suppress the
 * chart's own gestures, per-pane canvas layers and a projection. lightweight
 * -charts offers none of those directly, so this is where the gap is closed:
 *
 *   - **Drag.** The library has click and crosshair-move subscriptions and no
 *     drag stream at all. Rather than mixing its clicks with our own pointer
 *     handling and getting two of everything, all five events are synthesised
 *     from raw pointer events on the chart container. One source, one set of
 *     coordinates, no double-fire.
 *   - **Hit testing.** The library has no notion of an object under the cursor,
 *     so the host runs the layer's own `hitTest` and stamps the result onto
 *     each event as `externalId`. That is also what drives the cursor shape.
 *   - **Placement mode.** Suppressing the chart's pan while a tool is armed is
 *     `handleScroll`/`handleScale` off — and, critically, off for the duration
 *     of a drag that grabbed a drawing, or moving a trend line would scroll the
 *     chart out from under it.
 *   - **Panes.** Primitives attach to a *series*, so a layer lives on the price
 *     series and pane 0 is the only one that can currently hold drawings. The
 *     pane index is plumbed through anyway, because the engine is written for
 *     charts that can do better and this is the only file that would change.
 */

import type {
  IChartApi,
  IPrimitivePaneRenderer,
  IPrimitivePaneView,
  ISeriesApi,
  ISeriesPrimitive,
  Logical,
  SeriesAttachedParameter,
  SeriesType,
  Time
} from 'lightweight-charts';
import type {
  Bar,
  ChartDragEvent,
  ChartPointerEvent,
  Drawing,
  HostChart,
  HostPointerEvents,
  Primitive,
  RenderContext
} from '../../draw/types';
import type { ChartTheme } from '../../theme/types';
import type { Candle } from '../LwChart';
import { barSeconds, makeDataLayer, type DataLayer } from './data-layer';

/** Pointer travel, in CSS px, before a press counts as a drag rather than a click. */
const DRAG_SLOP = 3;

export interface HostDeps {
  chart: IChartApi;
  series: ISeriesApi<SeriesType>;
  /** The chart's own container — where the pointer listeners go. */
  container: HTMLElement;
  candles: readonly Candle[];
  theme: ChartTheme;
  /** Called whenever the controller commits new state, for persistence. */
  onState?: (drawings: Drawing[]) => void;
  /** Seed from storage. */
  initial?: Drawing[];
}

type Listeners = {
  [K in keyof HostPointerEvents]: Set<(p: HostPointerEvents[K]) => void>;
};

export class LightweightHost implements HostChart {
  private deps: HostDeps;
  private state: Drawing[];
  private layer: DataLayer;
  private placement = false;
  /** Suppressed for a drag even when no tool is armed — see the class docstring. */
  private gestureLock = false;
  private destroyed = false;

  private readonly primitives = new Map<number, { layer: Primitive; wrapper: LayerPrimitive }>();

  private readonly listeners: Listeners = {
    click: new Set(),
    'crosshair:move': new Set(),
    drag: new Set(),
    'drag:end': new Set(),
    dblclick: new Set()
  };

  private readonly emitListeners = new Map<string, Set<(p: unknown) => void>>();

  // -- gesture state --
  private downAt: { x: number; y: number; time: number; price: number } | null = null;
  private dragging = false;
  private grabbedId: string | null = null;

  constructor(deps: HostDeps) {
    this.deps = deps;
    this.state = deps.initial ?? [];
    this.layer = makeDataLayer(deps.candles);
    this.bind();
  }

  /**
   * Swaps in a new series, candle set or theme without losing state.
   *
   * `LwChart` rebuilds its chart and series whenever the chart type changes, and
   * the drawings must survive that — which they do, because they are stored as
   * `{time, price}` and re-projected. Only the plumbing needs replacing.
   */
  update(deps: Partial<HostDeps>): void {
    const seriesChanged = deps.series !== undefined && deps.series !== this.deps.series;
    const containerChanged = deps.container !== undefined && deps.container !== this.deps.container;
    if (containerChanged) this.unbind();
    this.deps = { ...this.deps, ...deps };
    if (deps.candles) this.layer = makeDataLayer(deps.candles);
    if (containerChanged) this.bind();
    if (seriesChanged) {
      // Every wrapper was attached to the series that just went away. Re-attach
      // to the new one; the wrappers themselves are still valid.
      for (const { wrapper } of this.primitives.values()) {
        wrapper.rebind(this);
        this.deps.series.attachPrimitive(wrapper);
      }
    }
    this.repaint();
  }

  get dataLayer(): DataLayer {
    return this.layer;
  }

  // -- engine-facing API -----------------------------------------------------

  on<K extends keyof HostPointerEvents>(
    event: K,
    cb: (p: HostPointerEvents[K]) => void
  ): () => void {
    const set = this.listeners[event] as Set<(p: HostPointerEvents[K]) => void>;
    set.add(cb);
    return () => set.delete(cb);
  }

  emit(event: string, payload: unknown): void {
    for (const cb of this.emitListeners.get(event) ?? []) cb(payload);
    this.repaint();
  }

  /** How the React layer listens to `draw:add` and friends. */
  onEmit(event: string, cb: (p: unknown) => void): () => void {
    let set = this.emitListeners.get(event);
    if (!set) {
      set = new Set();
      this.emitListeners.set(event, set);
    }
    set.add(cb);
    return () => set?.delete(cb);
  }

  setPlacementMode(on: boolean): void {
    this.placement = on;
    this.applyGestures();
    this.deps.container.style.cursor = on ? 'crosshair' : '';
  }

  drawingState(): Drawing[] {
    return this.state;
  }

  setDrawingState(drawings: Drawing[]): void {
    this.state = drawings;
    this.deps.onState?.(drawings);
    this.repaint();
  }

  getVisibleLogicalRange(): { from: number; to: number } | null {
    const range = this.deps.chart.timeScale().getVisibleLogicalRange();
    return range ? { from: range.from, to: range.to } : null;
  }

  addPrimitive(paneIndex: number, primitive: Primitive): void {
    if (this.primitives.has(paneIndex)) return;
    const wrapper = new LayerPrimitive(primitive, this);
    this.primitives.set(paneIndex, { layer: primitive, wrapper });
    this.deps.series.attachPrimitive(wrapper);
  }

  removePrimitive(paneIndex: number, primitive: Primitive): void {
    const entry = this.primitives.get(paneIndex);
    if (!entry || entry.layer !== primitive) return;
    this.primitives.delete(paneIndex);
    try {
      this.deps.series.detachPrimitive(entry.wrapper);
    } catch {
      // The series may already be gone — a rebuild racing a teardown.
    }
  }

  barAt(time: number): Bar | null {
    const candles = this.deps.candles;
    if (candles.length === 0) return null;
    const index = Math.round(this.layer.timeToIndexFloat(time));
    return candles[Math.max(0, Math.min(candles.length - 1, index))] ?? null;
  }

  // -- rendering -------------------------------------------------------------

  /**
   * The projection handed to every tool.
   *
   * Built fresh per frame on purpose: the price scale's mapping changes with
   * autoscale, so a context cached across frames would draw last frame's prices
   * at this frame's pixels.
   */
  renderContext(dpr: number, width: number, height: number): RenderContext {
    const { chart, series, theme } = this.deps;
    const timeScale = chart.timeScale();
    const formatter = series.priceFormatter();
    return {
      dpr,
      plotWidth: width,
      plotHeight: height,
      timeScale: {
        indexToX: (i) => timeScale.logicalToCoordinate(i as Logical) ?? Number.NaN
      },
      priceScale: {
        priceToY: (p) => series.priceToCoordinate(p) ?? Number.NaN,
        format: (p) => formatter.format(p)
      },
      dataLayer: this.layer,
      // `surface` is the panel the chart sits on, which is what a handle's fill
      // and a label plate need to match; `axis` is the theme's readable
      // foreground. The *default drawing* colour is not set here — the hook
      // passes `theme.accent` as the controller's `defaultStyle`, so a new
      // drawing is the app's accent and only falls back to `lineColor` if a
      // saved drawing somehow has no colour of its own.
      theme: { background: theme.surface, lineColor: theme.axis },
      bars: () => this.deps.candles as readonly Bar[]
    };
  }

  repaint(): void {
    for (const { wrapper } of this.primitives.values()) wrapper.repaint();
  }

  // -- pointer plumbing ------------------------------------------------------

  private bind(): void {
    const el = this.deps.container;
    el.addEventListener('pointerdown', this.onPointerDown);
    el.addEventListener('pointermove', this.onPointerMove);
    el.addEventListener('pointerup', this.onPointerUp);
    el.addEventListener('pointercancel', this.onPointerCancel);
    el.addEventListener('pointerleave', this.onPointerCancel);
    el.addEventListener('dblclick', this.onDoubleClick);
  }

  private unbind(): void {
    const el = this.deps.container;
    el.removeEventListener('pointerdown', this.onPointerDown);
    el.removeEventListener('pointermove', this.onPointerMove);
    el.removeEventListener('pointerup', this.onPointerUp);
    el.removeEventListener('pointercancel', this.onPointerCancel);
    el.removeEventListener('pointerleave', this.onPointerCancel);
    el.removeEventListener('dblclick', this.onDoubleClick);
  }

  /**
   * Whether an event originated inside a drawing-UI overlay (the style bar or the
   * text editor), which sit *inside* the chart container this host listens on.
   *
   * Those overlays' buttons fire pointer events that bubble to this container's
   * native listeners. Left unguarded, clicking "Delete" (or a colour swatch, the
   * lock, etc.) reads as an empty-space click on the chart and deselects the very
   * drawing the button is about to act on — so the button's own handler then runs
   * with nothing selected and does nothing. React's `stopPropagation` cannot help:
   * the native container listener fires during bubbling before React's delegated
   * root listener, so the guard has to live here.
   */
  private fromOverlay(event: Event): boolean {
    const target = event.target;
    return target instanceof Element && target.closest('[data-cn-chart-overlay]') !== null;
  }

  /** Container coordinates, plus what they mean in chart space. */
  private locate(event: PointerEvent | MouseEvent): ChartPointerEvent {
    const rect = this.deps.container.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const y = event.clientY - rect.top;
    const timeScale = this.deps.chart.timeScale();
    const logical = timeScale.coordinateToLogical(x);
    const price = this.deps.series.coordinateToPrice(y);
    return {
      x,
      y,
      time: logical === null ? null : this.layer.indexToTime(logical),
      price: price === null ? null : price,
      paneIndex: 0
    };
  }

  private hit(x: number, y: number): { externalId: string; cursor: string } | null {
    const entry = this.primitives.get(0);
    if (!entry) return null;
    const rect = this.deps.container.getBoundingClientRect();
    const rc = this.renderContext(1, rect.width, rect.height);
    const result = entry.layer.hitTest(x, y, rc);
    return result ? { externalId: result.externalId, cursor: result.cursor } : null;
  }

  private dispatch<K extends keyof HostPointerEvents>(
    event: K,
    payload: HostPointerEvents[K]
  ): void {
    for (const cb of this.listeners[event] as Set<(p: HostPointerEvents[K]) => void>) cb(payload);
    this.repaint();
  }

  private onPointerDown = (event: PointerEvent): void => {
    if (this.destroyed || event.button !== 0 || this.fromOverlay(event)) return;
    const at = this.locate(event);
    if (at.time === null || at.price === null) return;
    this.downAt = { x: at.x, y: at.y, time: at.time, price: at.price };
    this.dragging = false;
    const hit = this.placement ? null : this.hit(at.x, at.y);
    this.grabbedId = hit?.externalId ?? null;
    // Grabbing a drawing must not also pan the chart underneath it.
    if (this.grabbedId) {
      this.gestureLock = true;
      this.applyGestures();
    }
  };

  private onPointerMove = (event: PointerEvent): void => {
    if (this.destroyed) return;
    // Ignore hovering over an overlay, but never abandon a drag already in
    // flight (the pointer may cross the style bar while moving a drawing).
    if (this.downAt === null && this.fromOverlay(event)) return;
    const at = this.locate(event);
    const down = this.downAt;

    if (down && (event.buttons & 1) === 1) {
      if (!this.dragging && Math.hypot(at.x - down.x, at.y - down.y) > DRAG_SLOP)
        this.dragging = true;
      if (this.dragging && at.time !== null && at.price !== null) {
        const payload: ChartDragEvent = {
          ...at,
          fromTime: down.time,
          fromPrice: down.price,
          externalId: this.grabbedId
        };
        this.dispatch('drag', payload);
        return;
      }
    }

    const hit = this.placement ? null : this.hit(at.x, at.y);
    if (!this.placement) this.deps.container.style.cursor = hit ? hit.cursor : '';
    this.dispatch('crosshair:move', { ...at, externalId: hit?.externalId ?? null });
  };

  private onPointerUp = (event: PointerEvent): void => {
    if (this.destroyed || event.button !== 0) return;
    // A release on a drawing-UI overlay must not read as an empty-space click
    // (which would deselect). Still clean up any gesture state so a press that
    // began on the chart and ended on the overlay does not leave the host armed.
    if (this.fromOverlay(event)) {
      this.downAt = null;
      this.dragging = false;
      this.grabbedId = null;
      if (this.gestureLock) {
        this.gestureLock = false;
        this.applyGestures();
      }
      return;
    }
    const at = this.locate(event);
    const down = this.downAt;
    this.downAt = null;

    if (this.dragging && down) {
      this.dispatch('drag:end', {
        ...at,
        fromTime: down.time,
        fromPrice: down.price,
        externalId: this.grabbedId
      });
    }

    const hit = this.placement ? null : this.hit(at.x, at.y);
    // Every gesture ends in a click, flagged with whether it was also a drag.
    // The engine needs that flag to tell a pan from a placement and to swallow
    // the click that merely terminated a freehand stroke.
    this.dispatch('click', {
      ...at,
      externalId: hit?.externalId ?? null,
      viaDrag: this.dragging
    });

    this.dragging = false;
    this.grabbedId = null;
    if (this.gestureLock) {
      this.gestureLock = false;
      this.applyGestures();
    }
  };

  private onPointerCancel = (): void => {
    this.downAt = null;
    this.dragging = false;
    this.grabbedId = null;
    if (this.gestureLock) {
      this.gestureLock = false;
      this.applyGestures();
    }
  };

  private onDoubleClick = (event: MouseEvent): void => {
    if (this.destroyed || this.fromOverlay(event)) return;
    this.dispatch('dblclick', this.locate(event));
  };

  private applyGestures(): void {
    const free = !this.placement && !this.gestureLock;
    this.deps.chart.applyOptions({ handleScroll: free, handleScale: free });
  }

  destroy(): void {
    this.destroyed = true;
    this.unbind();
    for (const { wrapper } of this.primitives.values()) {
      try {
        this.deps.series.detachPrimitive(wrapper);
      } catch {
        // Already gone with its series.
      }
    }
    this.primitives.clear();
    this.listeners.click.clear();
    this.listeners['crosshair:move'].clear();
    this.listeners.drag.clear();
    this.listeners['drag:end'].clear();
    this.listeners.dblclick.clear();
    this.emitListeners.clear();
    this.deps.container.style.cursor = '';
    this.deps.chart.applyOptions({ handleScroll: true, handleScale: true });
  }
}

/**
 * Bridges one engine `Layer` onto a lightweight-charts series primitive.
 *
 * The bitmap coordinate space, not the media one, because the engine draws in
 * device pixels by design — its dash lengths, handle radii and font sizes are
 * all expressed as `n * dpr`, which is what keeps a 1px line one physical pixel
 * on a retina display instead of a blurred pair.
 */
class LayerPrimitive implements ISeriesPrimitive<Time> {
  private requestUpdate: (() => void) | null = null;

  private readonly renderer: IPrimitivePaneRenderer = {
    draw: (target) => {
      target.useBitmapCoordinateSpace(({ context, bitmapSize, horizontalPixelRatio }) => {
        const dpr = horizontalPixelRatio;
        const rc = this.host.renderContext(dpr, bitmapSize.width / dpr, bitmapSize.height / dpr);
        this.layer.draw(context, rc);
      });
    }
  };

  private readonly paneView: IPrimitivePaneView = {
    renderer: () => this.renderer,
    // Above the series, which is what `zOrder(): 'top'` means on this chart.
    zOrder: () => 'top'
  };

  private readonly views: readonly IPrimitivePaneView[] = [this.paneView];

  constructor(
    private readonly layer: Primitive,
    private host: LightweightHost
  ) {}

  rebind(host: LightweightHost): void {
    this.host = host;
  }

  attached(param: SeriesAttachedParameter<Time, SeriesType>): void {
    this.requestUpdate = param.requestUpdate;
  }

  detached(): void {
    this.requestUpdate = null;
  }

  updateAllViews(): void {
    // Nothing cached: the layer re-projects from chart space every frame.
  }

  /** Drawings changed without the chart changing, so ask for a frame. */
  repaint(): void {
    this.requestUpdate?.();
  }

  paneViews(): readonly IPrimitivePaneView[] {
    return this.views;
  }

  autoscaleInfo(): null {
    return this.layer.autoscaleInfo();
  }
}

export { barSeconds };
