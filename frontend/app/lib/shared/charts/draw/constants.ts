/**
 * The numbers the feel of the tools depends on.
 *
 * Collected here rather than inlined because several are shared across tool
 * families that otherwise have nothing to do with each other — the fib ratios
 * drive retracement, extension and the channel; UP/DOWN colour the position
 * tools and the forecast alike — and because a drawing whose dash length or
 * handle radius drifts from its neighbours looks broken long before anyone can
 * say which number changed.
 */

/** Profit/target green and loss/stop red. Not the theme's up/down: a drawing keeps its meaning across themes. */
export const UP = '#26a69a';
export const DOWN = '#ef5350';

export const FIB_LEVELS = [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1];
export const FAN_LEVELS = [0.236, 0.382, 0.5, 0.618, 0.786, 1];
export const FIB_TIME_ZONES = [0, 1, 2, 3, 5, 8, 13, 21, 34, 55];

/** Gann's ratios as [time, price] pairs — 1x1 is the middle one. */
export const GANN_RATIOS: readonly (readonly [number, number])[] = [
  [1, 0.125],
  [1, 0.25],
  [1, 0.5],
  [1, 1],
  [0.5, 1],
  [0.25, 1],
  [0.125, 1]
];

export const LINE_HEIGHT = 1.35;

export const FONT_STACK = 'ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, sans-serif';

/** Grab radius for a handle, CSS px. Larger than the 5px handle so it is catchable. */
export const HANDLE_HIT = 7;

/** Grab tolerance for a drawing's body, CSS px. */
export const BODY_HIT = 6;

/** Drawn radius of a handle, device px (multiplied by dpr at draw time). */
export const HANDLE_RADIUS = 5;

/** The in-progress shape is dimmed so it reads as "not placed yet". */
export const PREVIEW_ALPHA = 0.7;

export const DEFAULT_FILL_OPACITY = 0.12;
export const DEFAULT_LINE_WIDTH = 1.5;
