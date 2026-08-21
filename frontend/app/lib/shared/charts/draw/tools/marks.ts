/**
 * Notes, markers and the two freehand inks.
 *
 * The text family is the only one whose content is not geometry, which is why
 * these are the tools the adapter special-cases: placing one opens the editor
 * immediately, and cancelling out of an empty one removes the drawing rather
 * than leaving an invisible box on the chart for the reader to find later.
 */

import { distToEllipse, distToPolygon, distToPolyline, distToRect } from '../geometry';
import { boxLabel, inlineLabel, line, polyline, stroke, withAlpha, withFill } from '../render';
import { register, type DrawArgs } from '../registry';

/** Half-width and height of the arrow markers, CSS px before dpr. */
const ARROW_W = 7;
const ARROW_H = 16;

export function registerMarks(): void {
  register({
    id: 'text',
    name: 'Text',
    points: 1,
    defaultStyle: {
      text: 'Text',
      fontSize: 14,
      fontWeight: 'normal',
      fontStyle: 'normal',
      background: false,
      backgroundOpacity: 1,
      border: false,
      wrap: false,
      wrapWidth: 220,
      textAlign: 'left'
    },
    draw: (ctx, { pts, style, rc }) => {
      boxLabel(ctx, style.text ?? '', pts[0]!.x, pts[0]!.y, rc, style, {
        align: style.textAlign ?? 'left',
        place: 'below'
      });
    },
    // Measured against a nominal box rather than the real one: `distance` has no
    // canvas to ask for text metrics, and a note is grabbed by roughly where it
    // sits, not by the exact pixel its descenders reach.
    distance: (x, y, { pts, drawing }) => textBoxDistance(x, y, pts[0]!, drawing.style)
  });

  register({
    id: 'price-label',
    name: 'Price label',
    points: 1,
    defaultStyle: { fontSize: 12 },
    draw: (ctx, { pts, drawing, style, rc }) => {
      const price = drawing.points[0]?.price;
      if (price === undefined) return;
      const text = style.text?.trim() ? style.text : rc.priceScale.format(price);
      inlineLabel(ctx, text, pts[0]!.x, pts[0]!.y, rc, style, { align: 'center' });
    },
    distance: (x, y, { pts }) => Math.hypot(x - pts[0]!.x, y - pts[0]!.y) - 16
  });

  register({
    id: 'callout',
    name: 'Callout',
    points: 2,
    defaultStyle: { fontSize: 12, text: 'Note' },
    draw: (ctx, { pts, style, rc }) => {
      // The leader line first, so the box paints over its end and the join is
      // hidden rather than poking into the text.
      stroke(ctx, style, rc.dpr);
      line(ctx, pts[0]!, pts[1]!);
      boxLabel(
        ctx,
        style.text ?? '',
        pts[1]!.x,
        pts[1]!.y,
        rc,
        {
          ...style,
          background: style.background ?? true,
          backgroundColor: style.backgroundColor ?? rc.theme.background,
          border: style.border ?? true
        },
        { align: 'left', place: 'above' }
      );
    },
    distance: (x, y, { pts, drawing }) =>
      Math.min(distToPolyline(x, y, pts), textBoxDistance(x, y, pts[1]!, drawing.style))
  });

  register({
    id: 'flag-mark',
    name: 'Flag mark',
    points: 1,
    defaultStyle: { fill: true, fillOpacity: 0.95 },
    draw: (ctx, { pts, style, rc }) => {
      const dpr = rc.dpr;
      const { x, y } = pts[0]!;
      const h = 18 * dpr;
      const w = 12 * dpr;
      stroke(ctx, style, dpr);
      line(ctx, { x, y }, { x, y: y - h });
      withFill(ctx, style, () => {
        ctx.beginPath();
        ctx.moveTo(x, y - h);
        ctx.lineTo(x + w, y - h + w / 2);
        ctx.lineTo(x, y - h + w);
        ctx.closePath();
        ctx.fill();
      });
    },
    distance: (x, y, { pts }) =>
      distToRect(x, y, pts[0]!.x, pts[0]!.y - 18, pts[0]!.x + 12, pts[0]!.y, true)
  });

  register({
    id: 'arrow-up',
    name: 'Arrow up',
    points: 1,
    defaultStyle: { fill: true, fillOpacity: 0.9 },
    draw: (ctx, args) => marker(ctx, args, 1),
    distance: (x, y, { pts, drawing }) =>
      distToPolygon(x, y, markerPoints(pts[0]!.x, pts[0]!.y, 1, 1), drawing.style.fill !== false)
  });

  register({
    id: 'arrow-down',
    name: 'Arrow down',
    points: 1,
    defaultStyle: { fill: true, fillOpacity: 0.9 },
    draw: (ctx, args) => marker(ctx, args, -1),
    distance: (x, y, { pts, drawing }) =>
      distToPolygon(x, y, markerPoints(pts[0]!.x, pts[0]!.y, -1, 1), drawing.style.fill !== false)
  });

  register({
    id: 'brush',
    name: 'Brush',
    points: 0,
    freehand: true,
    defaultStyle: { lineWidth: 2 },
    draw: (ctx, { pts, style, rc }) => {
      stroke(ctx, style, rc.dpr);
      smooth(ctx, pts);
    },
    distance: (x, y, { pts }) => distToPolyline(x, y, pts)
  });

  register({
    id: 'highlighter',
    name: 'Highlighter',
    points: 0,
    freehand: true,
    defaultStyle: { lineWidth: 12, fillOpacity: 0.28 },
    draw: (ctx, { pts, style, rc }) => {
      // A wide, flat, translucent stroke — square caps so overlapping passes
      // build up the way a real marker does instead of beading at the joins.
      ctx.save();
      ctx.strokeStyle = withAlpha(style.color ?? rc.theme.lineColor, style.fillOpacity ?? 0.28);
      ctx.lineWidth = Math.max(1, Math.round((style.lineWidth ?? 12) * rc.dpr));
      ctx.lineCap = 'butt';
      ctx.lineJoin = 'round';
      ctx.setLineDash([]);
      polyline(ctx, pts);
      ctx.restore();
    },
    distance: (x, y, { pts }) => distToPolyline(x, y, pts)
  });
}

function marker(ctx: CanvasRenderingContext2D, { pts, style, rc }: DrawArgs, sign: 1 | -1): void {
  const shape = markerPoints(pts[0]!.x, pts[0]!.y, sign, rc.dpr);
  ctx.save();
  ctx.globalAlpha = style.fillOpacity ?? 0.9;
  ctx.fillStyle = style.fillColor ?? style.color ?? rc.theme.lineColor;
  ctx.beginPath();
  ctx.moveTo(shape[0]!.x, shape[0]!.y);
  for (const p of shape.slice(1)) ctx.lineTo(p.x, p.y);
  ctx.closePath();
  ctx.fill();
  ctx.restore();
}

/** A stubby arrow: a triangular head on a short shaft, pointing up (`1`) or down (`-1`). */
function markerPoints(x: number, y: number, sign: 1 | -1, dpr: number): { x: number; y: number }[] {
  const w = ARROW_W * dpr;
  const h = ARROW_H * dpr;
  const tip = y - h * sign;
  const neck = y - h * 0.45 * sign;
  return [
    { x, y: tip },
    { x: x + w, y: neck },
    { x: x + w * 0.4, y: neck },
    { x: x + w * 0.4, y },
    { x: x - w * 0.4, y },
    { x: x - w * 0.4, y: neck },
    { x: x - w, y: neck }
  ];
}

/**
 * A brush stroke drawn as quadratics through the midpoints of its samples.
 *
 * Straight segments between raw pointer samples look faceted at any speed the
 * hand actually moves; running the curve through midpoints costs nothing and
 * makes the ink look inked.
 */
function smooth(ctx: CanvasRenderingContext2D, pts: readonly { x: number; y: number }[]): void {
  if (pts.length < 3) {
    polyline(ctx, pts);
    return;
  }
  ctx.beginPath();
  ctx.moveTo(pts[0]!.x, pts[0]!.y);
  for (let i = 1; i < pts.length - 1; i += 1) {
    const current = pts[i]!;
    const next = pts[i + 1]!;
    ctx.quadraticCurveTo(current.x, current.y, (current.x + next.x) / 2, (current.y + next.y) / 2);
  }
  const last = pts[pts.length - 1]!;
  ctx.lineTo(last.x, last.y);
  ctx.stroke();
}

/** A rough box around a text anchor, in CSS px. */
function textBoxDistance(
  x: number,
  y: number,
  at: { x: number; y: number },
  style: { fontSize?: number; text?: string; textAlign?: string }
): number {
  const size = style.fontSize ?? 14;
  const lines = (style.text ?? '').split('\n');
  const longest = lines.reduce((n, l) => Math.max(n, l.length), 1);
  // 0.55em per character is the usual rule of thumb for a proportional stack,
  // and close enough for a grab box.
  const width = Math.max(24, longest * size * 0.55);
  const height = Math.max(size, lines.length * size * 1.35) + 8;
  const align = style.textAlign ?? 'left';
  const left = align === 'center' ? at.x - width / 2 : align === 'right' ? at.x - width : at.x;
  return distToRect(x, y, left, at.y, left + width, at.y + height, true);
}

/** Unused by the tools here, but kept so the marker geometry can be checked in isolation. */
export { markerPoints, distToEllipse };
