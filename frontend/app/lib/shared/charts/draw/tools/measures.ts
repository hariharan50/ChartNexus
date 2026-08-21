/**
 * The three measurers.
 *
 * `price-range` reads the move, `date-range` reads the duration, and `measure`
 * reads both — which is why it is the one bound to a drag in most terminals.
 * They are the only tools whose whole output is a number, so the readout is the
 * shape: the box is just there to say which two points the number came from.
 */

import { distToRect } from '../geometry';
import { arrowHead, fillWith, inlineLabel, line, stroke } from '../render';
import { register, type DrawArgs } from '../registry';
import type { Bar, Point, RenderContext } from '../types';

export function registerMeasures(): void {
  register({
    id: 'price-range',
    name: 'Price range',
    points: 2,
    defaultStyle: { fill: true, fillOpacity: 0.1 },
    draw: (ctx, args) => measure(ctx, args, 'price'),
    distance: (x, y, { pts }) => distToRect(x, y, pts[0]!.x, pts[0]!.y, pts[1]!.x, pts[1]!.y, true)
  });

  register({
    id: 'date-range',
    name: 'Date range',
    points: 2,
    defaultStyle: { fill: true, fillOpacity: 0.1 },
    draw: (ctx, args) => measure(ctx, args, 'date'),
    distance: (x, y, { pts }) => distToRect(x, y, pts[0]!.x, pts[0]!.y, pts[1]!.x, pts[1]!.y, true)
  });

  register({
    id: 'measure',
    name: 'Measure',
    points: 2,
    defaultStyle: { fill: true, fillOpacity: 0.14, showLabels: true },
    draw: (ctx, args) => measure(ctx, args, 'both'),
    distance: (x, y, { pts }) => distToRect(x, y, pts[0]!.x, pts[0]!.y, pts[1]!.x, pts[1]!.y, true)
  });
}

type Mode = 'price' | 'date' | 'both';

function measure(
  ctx: CanvasRenderingContext2D,
  { pts, drawing, style, rc }: DrawArgs,
  mode: Mode
): void {
  const a = pts[0]!;
  const b = pts[1]!;
  const from = drawing.points[0];
  const to = drawing.points[1];
  if (!from || !to) return;

  const rising = to.price >= from.price;
  const color = style.color ?? rc.theme.lineColor;

  fillWith(ctx, style.fillColor ?? color, style.fillOpacity ?? 0.12, () =>
    ctx.fillRect(Math.min(a.x, b.x), Math.min(a.y, b.y), Math.abs(b.x - a.x), Math.abs(b.y - a.y))
  );
  stroke(ctx, style, rc.dpr);
  ctx.strokeRect(Math.min(a.x, b.x), Math.min(a.y, b.y), Math.abs(b.x - a.x), Math.abs(b.y - a.y));

  // A shaft down the middle with a head on it, so the direction of the move is
  // readable before the numbers are.
  if (mode !== 'date') {
    const midX = (a.x + b.x) / 2;
    line(ctx, { x: midX, y: a.y }, { x: midX, y: b.y });
    arrowHead(ctx, { x: midX, y: a.y }, { x: midX, y: b.y }, 8 * rc.dpr, color);
  }

  if (style.showLabels === false) return;
  inlineLabel(
    ctx,
    readout(from, to, mode, rc),
    (a.x + b.x) / 2,
    rising ? Math.min(a.y, b.y) : Math.max(a.y, b.y),
    rc,
    style,
    {
      align: 'center',
      place: rising ? 'above' : 'below'
    }
  );
}

/** The text a measurer shows. Exported because it is the part worth testing. */
export function readout(from: Point, to: Point, mode: Mode, rc: MeasureContext): string {
  const move = to.price - from.price;
  const percent = from.price === 0 ? 0 : (move / from.price) * 100;
  const bars = barCount(from.time, to.time, rc);
  const priceText = `${move >= 0 ? '+' : ''}${rc.priceScale.format(move)} (${percent >= 0 ? '+' : ''}${percent.toFixed(2)}%)`;
  const timeText = `${bars} ${bars === 1 ? 'bar' : 'bars'}, ${duration(Math.abs(to.time - from.time))}`;
  if (mode === 'price') return priceText;
  if (mode === 'date') return timeText;
  return `${priceText}   ${timeText}`;
}

interface MeasureContext {
  priceScale: { format(p: number): string };
  dataLayer: { timeToIndexFloat(t: number): number };
}

function barCount(from: number, to: number, rc: MeasureContext): number {
  const a = rc.dataLayer.timeToIndexFloat(from);
  const b = rc.dataLayer.timeToIndexFloat(to);
  if (!Number.isFinite(a) || !Number.isFinite(b)) return 0;
  return Math.abs(Math.round(b - a));
}

/** Seconds as the largest unit that still reads as a whole number. */
export function duration(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const minutes = seconds / 60;
  if (minutes < 60) return `${Math.round(minutes)}m`;
  const hours = minutes / 60;
  if (hours < 24) return `${hours.toFixed(hours < 10 ? 1 : 0)}h`;
  return `${(hours / 24).toFixed(hours / 24 < 10 ? 1 : 0)}d`;
}

/** Kept for the forecast tool's bar scan, which shares this file's vocabulary. */
export type { Bar, RenderContext };
