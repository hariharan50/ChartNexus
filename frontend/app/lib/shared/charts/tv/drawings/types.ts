/**
 * Data-space vocabulary for chart drawings — shared by the primitives, the
 * interaction controller, and the toolbar.
 *
 * Everything a drawing needs to remember is `{ time, price }`, never a pixel:
 * pixels are recomputed at draw time from the chart's current pan/zoom, which
 * is what lets a trend line drawn last week still line up with today's
 * candles after the reader has scrolled and zoomed a dozen times since.
 */

/** One anchor of a drawing, in data space. */
export interface DrawingPoint {
  /** Epoch seconds — the same unit `Candle.time` already uses. */
  time: number;
  price: number;
}

/** Tools the drawing toolbar can select. `measure` never produces a `Drawing` — see `useDrawingController`. */
export type DrawingTool = 'trendline' | 'horizontal' | 'fib' | 'rectangle' | 'text' | 'measure';

interface DrawingBase {
  id: string;
  color: string;
}

export interface TrendLineDrawing extends DrawingBase {
  kind: 'trendline';
  a: DrawingPoint;
  b: DrawingPoint;
}

/** Spans the full visible width at one price — it has no time of its own. */
export interface HorizontalLineDrawing extends DrawingBase {
  kind: 'horizontal';
  price: number;
}

export interface FibDrawing extends DrawingBase {
  kind: 'fib';
  a: DrawingPoint;
  b: DrawingPoint;
}

export interface RectangleDrawing extends DrawingBase {
  kind: 'rectangle';
  a: DrawingPoint;
  b: DrawingPoint;
}

export interface TextDrawing extends DrawingBase {
  kind: 'text';
  at: DrawingPoint;
  text: string;
}

export type Drawing =
  TrendLineDrawing | HorizontalLineDrawing | FibDrawing | RectangleDrawing | TextDrawing;

/** A transient drag readout for the measure tool — never persisted as a `Drawing`. */
export interface Measurement {
  a: DrawingPoint;
  b: DrawingPoint;
}

/** Satisfied structurally by `TrendLinePrimitive`, `FibRetracementPrimitive` and `RectanglePrimitive`. */
export interface TwoPointPrimitive {
  a: DrawingPoint;
  b: DrawingPoint;
}
