import type {
  IChartApi,
  IPrimitivePaneRenderer,
  IPrimitivePaneView,
  ISeriesApi,
  ISeriesPrimitive,
  SeriesAttachedParameter,
  SeriesType,
  Time,
  UTCTimestamp
} from 'lightweight-charts';
import type { DrawingPoint } from './types';

/** Shared, so a hidden drawing costs no allocation per frame either. */
const NO_PANE_VIEWS: readonly IPrimitivePaneView[] = [];

/**
 * Shared plumbing for every drawing type: v5's Series Primitives lifecycle
 * (`attached`/`detached`), the point → pixel conversion every concrete
 * drawing needs, and the canvas handoff. Each subclass only has to say what
 * points it needs and how to draw them — see `TrendLinePrimitive` for the
 * simplest example.
 *
 * lightweight-charts has no built-in drawing tools; primitives are the
 * library's supported extension point for exactly this, which is why a
 * drawing is data (`{ time, price }`) redrawn every frame rather than a
 * fixed shape pasted onto the canvas once — that's what keeps it correctly
 * placed as the reader pans and zooms.
 */
export abstract class DrawingPrimitive implements ISeriesPrimitive<Time> {
  protected chart: IChartApi | null = null;
  protected series: ISeriesApi<SeriesType> | null = null;
  private requestUpdate: (() => void) | null = null;

  visible = true;

  /**
   * Built once and handed back on every frame.
   *
   * The library calls `paneViews()` and then the view's `renderer()` on each
   * repaint — every pan, zoom and crosshair move — so allocating a fresh view,
   * renderer and closure there would mint three objects per drawing per frame
   * for a result that never varies. Only `draw` reads anything mutable.
   */
  private readonly paneView: IPrimitivePaneView = {
    renderer: (): IPrimitivePaneRenderer => this.renderer
  };

  private readonly renderer: IPrimitivePaneRenderer = {
    draw: (target) => {
      target.useMediaCoordinateSpace(({ context }) => this.draw(context));
    }
  };

  private readonly paneViewList: readonly IPrimitivePaneView[] = [this.paneView];

  attached(param: SeriesAttachedParameter<Time, SeriesType>): void {
    this.chart = param.chart;
    this.series = param.series;
    this.requestUpdate = param.requestUpdate;
  }

  detached(): void {
    this.chart = null;
    this.series = null;
    this.requestUpdate = null;
  }

  /** Series data changed, or the caller mutated the drawing's own points. */
  updateAllViews(): void {
    this.requestUpdate?.();
  }

  paneViews(): readonly IPrimitivePaneView[] {
    return this.visible ? this.paneViewList : NO_PANE_VIEWS;
  }

  /** `null` when the point has scrolled off the currently visible range. */
  protected toPixel(point: DrawingPoint): { x: number; y: number } | null {
    if (!this.chart || !this.series) return null;
    const x = this.chart.timeScale().timeToCoordinate(point.time as UTCTimestamp);
    const y = this.series.priceToCoordinate(point.price);
    if (x === null || y === null) return null;
    return { x, y };
  }

  /** The full width of the pane currently on screen, in CSS pixels. */
  protected paneWidth(): number {
    return this.chart?.timeScale().width() ?? 0;
  }

  /** Draw in CSS-pixel (media) coordinate space — the library handles device-pixel scaling. */
  protected abstract draw(ctx: CanvasRenderingContext2D): void;
}
