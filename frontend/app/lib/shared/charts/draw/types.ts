/**
 * The drawing engine's vocabulary — tier 1 of three.
 *
 * Nothing in this folder may reference `window`, `document`, React or a CSS
 * framework. It knows about a canvas context and a projection, and that is all.
 * The chart it draws on reaches it through `HostChart` below, which the
 * lightweight-charts adapter in `../tv/drawings/lw-host.ts` implements.
 *
 * That separation is what lets the whole engine load behind a dynamic
 * `import()`: a chart the reader never draws on never pays for 43 tools.
 */

/** An anchor. Chart space, not pixels — see the module docstring in `Layer.ts`. */
export interface Point {
  /** Epoch seconds, the same unit `Candle.time` uses. */
  time: number;
  price: number;
}

export interface DrawingStyle {
  color?: string;
  lineWidth?: number;
  lineStyle?: 'solid' | 'dashed' | 'dotted';
  fill?: boolean;
  fillColor?: string;
  fillOpacity?: number;
  showLabels?: boolean;
  /** Fib-family ratios. */
  levels?: number[];
  // -- text-bearing tools --
  text?: string;
  fontSize?: number;
  fontWeight?: 'normal' | 'bold';
  fontStyle?: 'normal' | 'italic';
  background?: boolean;
  backgroundColor?: string;
  backgroundOpacity?: number;
  border?: boolean;
  borderColor?: string;
  wrap?: boolean;
  wrapWidth?: number;
  textAlign?: 'left' | 'center' | 'right';
  textVAlign?: 'top' | 'middle' | 'bottom';
  textPosition?: 'inside' | 'outside';
  // -- position tools --
  accountSize?: number;
  /** Percent of the account risked, so 1 means one percent. */
  risk?: number;
  /** Unknown keys survive a JSON round trip — see `Drawing`. */
  [key: string]: unknown;
}

/**
 * One placed shape.
 *
 * `DrawingStyle`'s index signature is deliberate: a workspace saved by a newer
 * build carries style keys this build has never heard of, and dropping them on
 * load would quietly degrade the drawing the next time it is saved back.
 */
export interface Drawing {
  /** `d0`, `d1`, … from a monotonic counter. */
  id: string;
  /** Registry id, e.g. `trend-line`. */
  tool: string;
  points: Point[];
  style: DrawingStyle;
  /** 0 is the main price pane; higher indices are indicator sub-panes. */
  paneIndex: number;
  locked?: boolean;
  /** `false` hides without deleting. */
  visible?: boolean;
}

/** Everything a tool needs to turn chart space into canvas space. */
export interface RenderContext {
  dpr: number;
  /** CSS px. */
  plotWidth: number;
  plotHeight: number;
  timeScale: { indexToX(i: number): number };
  priceScale: { priceToY(p: number): number; format(p: number): string };
  dataLayer: {
    timeToIndexFloat(t: number): number;
    indexToTime(i: number): number;
    baseIndex: number;
  };
  theme: { background: string; lineColor: string };
  /** The bars on screen, for `forecast`'s SUCCESS/MISSED test. */
  bars?(): readonly Bar[];
}

export interface Bar {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
}

export interface HitResult {
  externalId: string;
  cursor: 'move' | 'grabbing';
  draggable: true;
  distance: number;
}

/** A per-pane canvas layer. The host wraps this in whatever its chart calls a primitive. */
export interface Primitive {
  draw(ctx: CanvasRenderingContext2D, rc: RenderContext): void;
  hitTest(x: number, y: number, rc: RenderContext): HitResult | null;
  zOrder(): 'top';
  /** Always `null`: a drawing must never move the price scale. */
  autoscaleInfo(): null;
}

export interface ChartPointerEvent {
  /** CSS px inside the plot. */
  x: number;
  y: number;
  time: number | null;
  price: number | null;
  paneIndex: number;
  /** Hit-test result under the cursor, if any. */
  externalId?: string | null;
  /** This click merely terminated a drag gesture. */
  viaDrag?: boolean;
}

export interface ChartDragEvent extends ChartPointerEvent {
  /** Gesture origin, chart space. */
  fromTime: number;
  fromPrice: number;
}

export type DrawEventName =
  'draw:tool' | 'draw:add' | 'draw:update' | 'draw:remove' | 'draw:select';

export interface DrawEventPayload {
  'draw:tool': { tool: string | null };
  'draw:add': { drawing: Drawing };
  'draw:update': { drawing: Drawing };
  'draw:remove': { id: string };
  'draw:select': { id: string | null };
}

export interface HostPointerEvents {
  click: ChartPointerEvent;
  'crosshair:move': ChartPointerEvent;
  drag: ChartDragEvent;
  'drag:end': ChartDragEvent;
  dblclick: ChartPointerEvent;
}

/**
 * The entire integration surface. A chart that cannot do these things gets an
 * adapter that can — which is exactly what `lw-host.ts` is, since
 * lightweight-charts has no drag stream, no hit-testing and no notion of
 * suppressing its own pan while a tool is armed.
 */
export interface HostChart {
  on<K extends keyof HostPointerEvents>(
    event: K,
    cb: (p: HostPointerEvents[K]) => void
  ): () => void;

  emit<K extends DrawEventName>(event: K, payload: DrawEventPayload[K]): void;

  /** Suppress the chart's own click and pan behaviour while a tool is armed. */
  setPlacementMode(on: boolean): void;

  /** Opaque persisted state the chart carries across rebuilds. */
  drawingState(): Drawing[];
  setDrawingState(d: Drawing[]): void;

  getVisibleLogicalRange(): { from: number; to: number } | null;

  dataLayer: {
    baseIndex: number;
    indexToTime(i: number): number;
    timeToIndexFloat(t: number): number;
  };

  addPrimitive(paneIndex: number, primitive: Primitive): void;
  removePrimitive(paneIndex: number, primitive: Primitive): void;

  /** The bar under the crosshair, for the magnet. `null` off-data. */
  barAt(time: number): Bar | null;
}
