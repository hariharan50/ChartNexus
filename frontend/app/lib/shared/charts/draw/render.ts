/**
 * The painting helpers every tool shares.
 *
 * A note on units, because it is the one thing that will bite anyone extending
 * this. The canvas here is a **device-pixel** backing store and the context is
 * not pre-scaled, so:
 *
 *   - `project()` returns CSS px, and is what `distance()` implementations see;
 *   - `Layer` multiplies those by `rc.dpr` before calling a tool's `draw()`, so
 *     every coordinate inside a `draw()` is device px;
 *   - anything a `draw()` computes itself — a line width, a radius, a font
 *     size, a dash length, a label offset — must be multiplied by `rc.dpr` too,
 *     or it will be half-size on a retina display and correct nowhere else.
 *
 * The helpers below all take `dpr` explicitly rather than reading it off a
 * shared mutable, so that rule is visible at every call site.
 */

import { DEFAULT_FILL_OPACITY, DEFAULT_LINE_WIDTH, FONT_STACK, LINE_HEIGHT } from './constants';
import type { Pt } from './geometry';
import type { Drawing, DrawingStyle, RenderContext } from './types';

/**
 * The one projection. Chart space to CSS px.
 *
 * Time goes through the data layer's float index rather than the time scale's
 * own time-to-coordinate, because a drawing may be anchored between two bars
 * (or past the last one, which is where every forecast and position target
 * lives) and a bar-quantised lookup would snap it back onto real data.
 */
export function project(rc: RenderContext, time: number, price: number): Pt {
  return {
    x: rc.timeScale.indexToX(rc.dataLayer.timeToIndexFloat(time)),
    y: rc.priceScale.priceToY(price)
  };
}

export function stroke(ctx: CanvasRenderingContext2D, style: DrawingStyle, dpr: number): void {
  ctx.strokeStyle = style.color ?? '#ffffff';
  ctx.lineWidth = Math.max(1, Math.round((style.lineWidth ?? DEFAULT_LINE_WIDTH) * dpr));
  ctx.lineJoin = 'round';
  ctx.lineCap = 'round';
  ctx.setLineDash(
    style.lineStyle === 'dashed'
      ? [6 * dpr, 4 * dpr]
      : style.lineStyle === 'dotted'
        ? [1 * dpr, 3 * dpr]
        : []
  );
}

/**
 * Runs `path` with the fill style applied, but only when the drawing asks to be
 * filled. Saves and restores, so the caller's stroke settings survive.
 */
export function withFill(
  ctx: CanvasRenderingContext2D,
  style: DrawingStyle,
  path: () => void
): void {
  if (style.fill !== true) return;
  ctx.save();
  ctx.globalAlpha = style.fillOpacity ?? DEFAULT_FILL_OPACITY;
  ctx.fillStyle = style.fillColor ?? style.color ?? '#ffffff';
  path();
  ctx.restore();
}

/** Fills an arbitrary path with an explicit colour and alpha — for the position tools' zones. */
export function fillWith(
  ctx: CanvasRenderingContext2D,
  color: string,
  alpha: number,
  path: () => void
): void {
  ctx.save();
  ctx.globalAlpha = alpha;
  ctx.fillStyle = color;
  path();
  ctx.restore();
}

export function font(size: number, dpr: number, weight = 'normal', italic = false): string {
  return `${italic ? 'italic ' : ''}${weight} ${Math.round(size * dpr)}px ${FONT_STACK}`;
}

export type LabelAnchor = 'left' | 'center' | 'right';

interface InlineLabelOptions {
  align?: LabelAnchor;
  /** Vertical placement relative to `y`. */
  place?: 'above' | 'below' | 'middle';
  background?: string;
  color?: string;
  fontSize?: number;
}

/**
 * Small text on a solid plate — fib level values, price-scale tags, the measure
 * readout.
 *
 * The plate exists because these land on top of candles: unplated text over a
 * dense wick is unreadable at any colour.
 */
export function inlineLabel(
  ctx: CanvasRenderingContext2D,
  text: string,
  x: number,
  y: number,
  rc: RenderContext,
  style: DrawingStyle,
  options: InlineLabelOptions = {}
): void {
  const dpr = rc.dpr;
  const size = options.fontSize ?? style.fontSize ?? 11;
  const pad = 4 * dpr;
  ctx.save();
  ctx.setLineDash([]);
  ctx.font = font(size, dpr);
  ctx.textBaseline = 'middle';
  const width = ctx.measureText(text).width;
  const height = Math.round(size * dpr) + pad;

  const align = options.align ?? 'left';
  const boxX = align === 'left' ? x : align === 'right' ? x - width - pad * 2 : x - width / 2 - pad;
  const place = options.place ?? 'middle';
  const boxY = place === 'above' ? y - height : place === 'below' ? y : y - height / 2;

  const plate = options.background ?? style.color ?? rc.theme.lineColor;
  ctx.fillStyle = plate;
  ctx.fillRect(boxX, boxY, width + pad * 2, height);
  ctx.fillStyle = options.color ?? contrastText(plate);
  ctx.fillText(text, boxX + pad, boxY + height / 2);
  ctx.restore();
}

interface BoxLabelOptions {
  align?: LabelAnchor;
  place?: 'above' | 'below' | 'middle';
  maxWidth?: number;
}

/**
 * The multi-line rounded box behind `text`, `callout` and the position tools.
 *
 * Text colour is not configurable on purpose: it is derived from whatever the
 * box ends up sitting on, so a reader who picks a pale background does not get
 * white-on-white and have to work out why their note vanished.
 */
export function boxLabel(
  ctx: CanvasRenderingContext2D,
  raw: string,
  x: number,
  y: number,
  rc: RenderContext,
  style: DrawingStyle,
  options: BoxLabelOptions = {}
): { x: number; y: number; width: number; height: number } {
  const dpr = rc.dpr;
  const size = style.fontSize ?? 14;
  const pad = 6 * dpr;
  const lineHeight = Math.round(size * dpr * LINE_HEIGHT);

  ctx.save();
  ctx.setLineDash([]);
  ctx.font = font(size, dpr, style.fontWeight ?? 'normal', style.fontStyle === 'italic');
  ctx.textBaseline = 'middle';

  const wrapWidth = (style.wrapWidth ?? 220) * dpr;
  const lines =
    style.wrap === true
      ? raw.split('\n').flatMap((line) => wrapText(ctx, line, options.maxWidth ?? wrapWidth))
      : raw.split('\n');

  let width = 0;
  for (const line of lines) width = Math.max(width, ctx.measureText(line).width);
  const boxW = width + pad * 2;
  const boxH = lines.length * lineHeight + pad * 2;

  const align = options.align ?? style.textAlign ?? 'left';
  const boxX = align === 'left' ? x : align === 'right' ? x - boxW : x - boxW / 2;
  const place = options.place ?? 'below';
  const boxY = place === 'above' ? y - boxH : place === 'middle' ? y - boxH / 2 : y;

  const bg = style.background === true ? (style.backgroundColor ?? '#434651') : rc.theme.background;
  if (style.background === true) {
    ctx.globalAlpha = style.backgroundOpacity ?? 1;
    ctx.fillStyle = bg;
    roundRect(ctx, boxX, boxY, boxW, boxH, 4 * dpr);
    ctx.fill();
    ctx.globalAlpha = 1;
  }
  if (style.border === true) {
    ctx.strokeStyle = style.borderColor ?? style.color ?? rc.theme.lineColor;
    ctx.lineWidth = Math.max(1, Math.round(1 * dpr));
    roundRect(ctx, boxX, boxY, boxW, boxH, 4 * dpr);
    ctx.stroke();
  }

  // Only auto-contrast against a plate we actually painted. Over bare chart the
  // author's colour is the right one — it is what they picked it against.
  ctx.fillStyle =
    style.background === true ? contrastText(bg) : (style.color ?? rc.theme.lineColor);
  lines.forEach((line, i) => {
    const lineW = ctx.measureText(line).width;
    const tx =
      align === 'center'
        ? boxX + (boxW - lineW) / 2
        : align === 'right'
          ? boxX + boxW - pad - lineW
          : boxX + pad;
    ctx.fillText(line, tx, boxY + pad + i * lineHeight + lineHeight / 2);
  });
  ctx.restore();

  return { x: boxX, y: boxY, width: boxW, height: boxH };
}

/** Greedy word wrap against the live font metrics. */
export function wrapText(ctx: CanvasRenderingContext2D, text: string, maxWidth: number): string[] {
  const words = text.split(/\s+/).filter(Boolean);
  if (words.length === 0) return [''];
  const lines: string[] = [];
  let line = words[0]!;
  for (const word of words.slice(1)) {
    const candidate = `${line} ${word}`;
    if (ctx.measureText(candidate).width > maxWidth) {
      lines.push(line);
      line = word;
    } else {
      line = candidate;
    }
  }
  lines.push(line);
  return lines;
}

export function roundRect(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  w: number,
  h: number,
  r: number
): void {
  const radius = Math.min(r, w / 2, h / 2);
  ctx.beginPath();
  ctx.moveTo(x + radius, y);
  ctx.arcTo(x + w, y, x + w, y + h, radius);
  ctx.arcTo(x + w, y + h, x, y + h, radius);
  ctx.arcTo(x, y + h, x, y, radius);
  ctx.arcTo(x, y, x + w, y, radius);
  ctx.closePath();
}

/**
 * Black or white, whichever the background can carry.
 *
 * The 0.45 threshold rather than 0.5 leans towards white text, which is the
 * right bias on a dark terminal: mid-grey plates read better with white on them
 * than with near-black.
 */
export function contrastText(background: string): string {
  return luminance(background) > 0.45 ? '#10131a' : '#ffffff';
}

/** Relative luminance, 0 to 1. Understands #rgb, #rrggbb, rgb() and rgba(). */
export function luminance(color: string): number {
  const rgb = parseColor(color);
  if (!rgb) return 0;
  const [r, g, b] = rgb;
  return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255;
}

function parseColor(color: string): [number, number, number] | null {
  const value = color.trim();
  if (value.startsWith('#')) {
    const hex = value.slice(1);
    if (hex.length === 3) {
      const r = hex[0]!;
      const g = hex[1]!;
      const b = hex[2]!;
      return [parseInt(r + r, 16), parseInt(g + g, 16), parseInt(b + b, 16)];
    }
    if (hex.length === 6 || hex.length === 8) {
      return [
        parseInt(hex.slice(0, 2), 16),
        parseInt(hex.slice(2, 4), 16),
        parseInt(hex.slice(4, 6), 16)
      ];
    }
    return null;
  }
  const match = /^rgba?\(([^)]+)\)$/i.exec(value);
  if (!match) return null;
  const parts = match[1]!
    .split(/[,\s/]+/)
    .filter(Boolean)
    .map(Number);
  if (parts.length < 3 || parts.slice(0, 3).some(Number.isNaN)) return null;
  return [parts[0]!, parts[1]!, parts[2]!];
}

/** The same colour at a given alpha, for zone fills that must not lose their hue. */
export function withAlpha(color: string, alpha: number): string {
  const rgb = parseColor(color);
  if (!rgb) return color;
  return `rgba(${rgb[0]}, ${rgb[1]}, ${rgb[2]}, ${alpha})`;
}

/**
 * Extends the segment `a`-`b` to the plot edges.
 *
 * Used by `extended-line`, `ray` and the fans. Done by scaling the direction
 * vector by a multiple of the plot diagonal rather than by solving for the
 * intersection with each edge: the canvas clips for us, and the diagonal is
 * guaranteed to overshoot from any interior point.
 */
export function extend(a: Pt, b: Pt, rc: RenderContext, both: boolean): [Pt, Pt] {
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  const len = Math.hypot(dx, dy);
  if (len === 0) return [a, b];
  const reach = (Math.hypot(rc.plotWidth, rc.plotHeight) * rc.dpr * 2) / len;
  const far = { x: a.x + dx * reach, y: a.y + dy * reach };
  const near = both ? { x: a.x - dx * reach, y: a.y - dy * reach } : a;
  return [near, far];
}

export function line(ctx: CanvasRenderingContext2D, a: Pt, b: Pt): void {
  ctx.beginPath();
  ctx.moveTo(a.x, a.y);
  ctx.lineTo(b.x, b.y);
  ctx.stroke();
}

export function polyline(ctx: CanvasRenderingContext2D, pts: readonly Pt[]): void {
  if (pts.length < 2) return;
  ctx.beginPath();
  ctx.moveTo(pts[0]!.x, pts[0]!.y);
  for (const p of pts.slice(1)) ctx.lineTo(p.x, p.y);
  ctx.stroke();
}

/** An arrowhead at `b`, pointing away from `a`. */
export function arrowHead(
  ctx: CanvasRenderingContext2D,
  a: Pt,
  b: Pt,
  size: number,
  color: string
): void {
  const angle = Math.atan2(b.y - a.y, b.x - a.x);
  const wing = Math.PI / 7;
  ctx.save();
  ctx.setLineDash([]);
  ctx.fillStyle = color;
  ctx.beginPath();
  ctx.moveTo(b.x, b.y);
  ctx.lineTo(b.x - size * Math.cos(angle - wing), b.y - size * Math.sin(angle - wing));
  ctx.lineTo(b.x - size * Math.cos(angle + wing), b.y - size * Math.sin(angle + wing));
  ctx.closePath();
  ctx.fill();
  ctx.restore();
}

/**
 * Which anchor indices of a drawing get a draggable handle.
 *
 * Freehand strokes expose only their ends: a brush stroke has hundreds of
 * points and dragging one out of the middle of it deforms the stroke in a way
 * nobody ever wants.
 */
export function handleIndices(drawing: Drawing, freehand: boolean): number[] {
  const n = drawing.points.length;
  if (freehand && n > 2) return [0, n - 1];
  return Array.from({ length: n }, (_, i) => i);
}

/** The selection handles. Takes CSS-px points and scales them itself. */
export function drawHandles(
  ctx: CanvasRenderingContext2D,
  pts: readonly Pt[],
  indices: readonly number[],
  rc: RenderContext
): void {
  const dpr = rc.dpr;
  ctx.save();
  ctx.setLineDash([]);
  ctx.fillStyle = rc.theme.background;
  ctx.strokeStyle = rc.theme.lineColor;
  ctx.lineWidth = Math.max(1, Math.round(1.5 * dpr));
  for (const i of indices) {
    const p = pts[i];
    if (!p || !Number.isFinite(p.x) || !Number.isFinite(p.y)) continue;
    ctx.beginPath();
    ctx.arc(p.x * dpr, p.y * dpr, 5 * dpr, 0, Math.PI * 2);
    ctx.fill();
    ctx.stroke();
  }
  ctx.restore();
}
