/**
 * Closed shapes and free paths.
 *
 * Two anchors define a rectangle, an ellipse or a circle; three define a
 * triangle, a rotated rectangle and the curves. `path` and `polyline` take as
 * many as the reader gives them and end on a double-click — `points: 0` is the
 * registry's way of saying open-ended.
 */

import { distToEllipse, distToPolygon, distToPolyline, distToRect, type Pt } from '../geometry';
import { boxLabel, polyline as strokePolyline, stroke, withFill } from '../render';
import { register } from '../registry';

export function registerShapes(): void {
  register({
    id: 'rectangle',
    name: 'Rectangle',
    points: 2,
    defaultStyle: {
      fill: true,
      fontSize: 14,
      textAlign: 'left',
      textVAlign: 'top',
      textPosition: 'inside'
    },
    draw: (ctx, { pts, style, rc }) => {
      const a = pts[0]!;
      const b = pts[1]!;
      const x = Math.min(a.x, b.x);
      const y = Math.min(a.y, b.y);
      const w = Math.abs(b.x - a.x);
      const h = Math.abs(b.y - a.y);
      withFill(ctx, style, () => ctx.fillRect(x, y, w, h));
      stroke(ctx, style, rc.dpr);
      ctx.strokeRect(x, y, w, h);
      const text = style.text;
      if (text) {
        const align = style.textAlign ?? 'left';
        const tx = align === 'center' ? x + w / 2 : align === 'right' ? x + w : x;
        const vAlign = style.textVAlign ?? 'top';
        const ty = vAlign === 'middle' ? y + h / 2 : vAlign === 'bottom' ? y + h : y;
        boxLabel(ctx, text, tx, ty, rc, style, {
          align,
          place: vAlign === 'middle' ? 'middle' : vAlign === 'bottom' ? 'above' : 'below'
        });
      }
    },
    distance: (x, y, { pts, drawing }) =>
      distToRect(x, y, pts[0]!.x, pts[0]!.y, pts[1]!.x, pts[1]!.y, drawing.style.fill === true)
  });

  register({
    id: 'rotated-rectangle',
    name: 'Rotated rectangle',
    points: 3,
    defaultStyle: { fill: true, fillOpacity: 0.12 },
    draw: (ctx, { pts, style, rc }) => {
      const quad = rotatedQuad(pts[0]!, pts[1]!, pts[2]!);
      withFill(ctx, style, () => {
        path(ctx, quad, true);
        ctx.fill();
      });
      stroke(ctx, style, rc.dpr);
      path(ctx, quad, true);
      ctx.stroke();
    },
    distance: (x, y, { pts, drawing }) =>
      distToPolygon(x, y, rotatedQuad(pts[0]!, pts[1]!, pts[2]!), drawing.style.fill === true)
  });

  register({
    id: 'ellipse',
    name: 'Ellipse',
    points: 2,
    defaultStyle: { fill: true, textAlign: 'center', textVAlign: 'middle' },
    draw: (ctx, { pts, style, rc }) => {
      const { cx, cy, rx, ry } = ellipseOf(pts[0]!, pts[1]!);
      withFill(ctx, style, () => {
        ctx.beginPath();
        ctx.ellipse(cx, cy, rx, ry, 0, 0, Math.PI * 2);
        ctx.fill();
      });
      stroke(ctx, style, rc.dpr);
      ctx.beginPath();
      ctx.ellipse(cx, cy, rx, ry, 0, 0, Math.PI * 2);
      ctx.stroke();
    },
    distance: (x, y, { pts, drawing }) => {
      const { cx, cy, rx, ry } = ellipseOf(pts[0]!, pts[1]!);
      return distToEllipse(x, y, cx, cy, rx, ry, drawing.style.fill === true);
    }
  });

  register({
    id: 'circle',
    name: 'Circle',
    points: 2,
    defaultStyle: { fill: true },
    draw: (ctx, { pts, style, rc }) => {
      const r = Math.hypot(pts[1]!.x - pts[0]!.x, pts[1]!.y - pts[0]!.y);
      withFill(ctx, style, () => {
        ctx.beginPath();
        ctx.arc(pts[0]!.x, pts[0]!.y, r, 0, Math.PI * 2);
        ctx.fill();
      });
      stroke(ctx, style, rc.dpr);
      ctx.beginPath();
      ctx.arc(pts[0]!.x, pts[0]!.y, r, 0, Math.PI * 2);
      ctx.stroke();
    },
    distance: (x, y, { pts, drawing }) => {
      const r = Math.hypot(pts[1]!.x - pts[0]!.x, pts[1]!.y - pts[0]!.y);
      return distToEllipse(x, y, pts[0]!.x, pts[0]!.y, r, r, drawing.style.fill === true);
    }
  });

  register({
    id: 'triangle',
    name: 'Triangle',
    points: 3,
    defaultStyle: { fill: true },
    draw: (ctx, { pts, style, rc }) => {
      withFill(ctx, style, () => {
        path(ctx, pts, true);
        ctx.fill();
      });
      stroke(ctx, style, rc.dpr);
      path(ctx, pts, true);
      ctx.stroke();
    },
    distance: (x, y, { pts, drawing }) => distToPolygon(x, y, pts, drawing.style.fill === true)
  });

  register({
    id: 'path',
    name: 'Path',
    points: 0,
    draw: (ctx, { pts, style, rc }) => {
      stroke(ctx, style, rc.dpr);
      strokePolyline(ctx, pts);
    },
    distance: (x, y, { pts }) => distToPolyline(x, y, pts)
  });

  register({
    id: 'polyline',
    name: 'Polyline',
    points: 0,
    defaultStyle: { fill: false },
    draw: (ctx, { pts, style, rc }) => {
      // A polyline closes back to its first point; a path does not. That is the
      // whole difference between the two tools, and it is why this one can fill.
      withFill(ctx, style, () => {
        path(ctx, pts, true);
        ctx.fill();
      });
      stroke(ctx, style, rc.dpr);
      path(ctx, pts, true);
      ctx.stroke();
    },
    distance: (x, y, { pts, drawing }) => distToPolygon(x, y, pts, drawing.style.fill === true)
  });

  register({
    id: 'arc',
    name: 'Arc',
    points: 3,
    draw: (ctx, { pts, style, rc }) => {
      stroke(ctx, style, rc.dpr);
      ctx.beginPath();
      ctx.moveTo(pts[0]!.x, pts[0]!.y);
      // The third anchor pulls the curve: a quadratic through it rather than at
      // it, which is what makes dragging the handle feel like bending a wire.
      ctx.quadraticCurveTo(pts[2]!.x, pts[2]!.y, pts[1]!.x, pts[1]!.y);
      ctx.stroke();
    },
    distance: (x, y, { pts }) => distToPolyline(x, y, quadPoints(pts[0]!, pts[2]!, pts[1]!))
  });

  register({
    id: 'curve',
    name: 'Curve',
    points: 3,
    draw: (ctx, { pts, style, rc }) => {
      stroke(ctx, style, rc.dpr);
      ctx.beginPath();
      ctx.moveTo(pts[0]!.x, pts[0]!.y);
      ctx.quadraticCurveTo(
        control(pts[0]!, pts[1]!, pts[2]!).x,
        control(pts[0]!, pts[1]!, pts[2]!).y,
        pts[1]!.x,
        pts[1]!.y
      );
      ctx.stroke();
    },
    distance: (x, y, { pts }) =>
      distToPolyline(x, y, quadPoints(pts[0]!, control(pts[0]!, pts[1]!, pts[2]!), pts[1]!))
  });

  register({
    id: 'double-curve',
    name: 'Double curve',
    points: 3,
    draw: (ctx, { pts, style, rc }) => {
      stroke(ctx, style, rc.dpr);
      const [first, second] = doubleCurve(pts[0]!, pts[1]!, pts[2]!);
      ctx.beginPath();
      ctx.moveTo(pts[0]!.x, pts[0]!.y);
      ctx.quadraticCurveTo(first.x, first.y, pts[2]!.x, pts[2]!.y);
      ctx.quadraticCurveTo(second.x, second.y, pts[1]!.x, pts[1]!.y);
      ctx.stroke();
    },
    distance: (x, y, { pts }) => {
      const [first, second] = doubleCurve(pts[0]!, pts[1]!, pts[2]!);
      return Math.min(
        distToPolyline(x, y, quadPoints(pts[0]!, first, pts[2]!)),
        distToPolyline(x, y, quadPoints(pts[2]!, second, pts[1]!))
      );
    }
  });
}

function path(ctx: CanvasRenderingContext2D, pts: readonly Pt[], close: boolean): void {
  if (pts.length === 0) return;
  ctx.beginPath();
  ctx.moveTo(pts[0]!.x, pts[0]!.y);
  for (const p of pts.slice(1)) ctx.lineTo(p.x, p.y);
  if (close) ctx.closePath();
}

function ellipseOf(a: Pt, b: Pt): { cx: number; cy: number; rx: number; ry: number } {
  return {
    cx: (a.x + b.x) / 2,
    cy: (a.y + b.y) / 2,
    rx: Math.abs(b.x - a.x) / 2,
    ry: Math.abs(b.y - a.y) / 2
  };
}

/**
 * The four corners of a rotated rectangle.
 *
 * The first two anchors are one edge; the third sets the depth, measured
 * perpendicular to that edge. Projecting the third anchor onto the normal
 * rather than using it as a corner is what keeps the shape a true rectangle
 * however the reader drags it.
 */
export function rotatedQuad(a: Pt, b: Pt, c: Pt): Pt[] {
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  const len = Math.hypot(dx, dy);
  if (len === 0) return [a, b, c, c];
  const nx = -dy / len;
  const ny = dx / len;
  const depth = (c.x - b.x) * nx + (c.y - b.y) * ny;
  return [
    a,
    b,
    { x: b.x + nx * depth, y: b.y + ny * depth },
    { x: a.x + nx * depth, y: a.y + ny * depth }
  ];
}

/** The control point that makes a quadratic bow through the third anchor. */
function control(a: Pt, b: Pt, c: Pt): Pt {
  // A quadratic passes through its control point at t=0.5 only if the control
  // is pulled twice as far as the point you want it to reach.
  return { x: 2 * c.x - (a.x + b.x) / 2, y: 2 * c.y - (a.y + b.y) / 2 };
}

function doubleCurve(a: Pt, b: Pt, c: Pt): [Pt, Pt] {
  return [
    { x: (a.x + c.x) / 2, y: c.y },
    { x: (c.x + b.x) / 2, y: 2 * c.y - b.y }
  ];
}

/** A quadratic flattened to a polyline, for hit testing. */
function quadPoints(a: Pt, ctrl: Pt, b: Pt, steps = 16): Pt[] {
  const out: Pt[] = [];
  for (let i = 0; i <= steps; i += 1) {
    const t = i / steps;
    const u = 1 - t;
    out.push({
      x: u * u * a.x + 2 * u * t * ctrl.x + t * t * b.x,
      y: u * u * a.y + 2 * u * t * ctrl.y + t * t * b.y
    });
  }
  return out;
}
