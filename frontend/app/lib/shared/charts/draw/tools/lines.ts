/**
 * The line family: the eight tools that are, geometrically, one segment.
 *
 * They differ only in which parts of that segment are infinite and whether an
 * arrowhead sits on the end, which is why they share so much here. The
 * horizontal and vertical pair are the odd ones: a horizontal line has no time
 * of its own and a vertical none of its own price, so each ignores half of its
 * single anchor and spans the plot in that direction forever.
 */

import { distToLine, distToRay, distToSegment } from '../geometry';
import { arrowHead, extend, inlineLabel, line, stroke } from '../render';
import { register, type DrawArgs, type DistanceArgs } from '../registry';

export function registerLines(): void {
  register({
    id: 'trend-line',
    name: 'Trend line',
    points: 2,
    shortcut: 'Alt+T',
    draw: (ctx, { pts, style, rc }) => {
      stroke(ctx, style, rc.dpr);
      line(ctx, pts[0]!, pts[1]!);
    },
    distance: (x, y, { pts }) => distToSegment(x, y, pts[0]!, pts[1]!)
  });

  register({
    id: 'ray',
    name: 'Ray',
    points: 2,
    draw: (ctx, { pts, style, rc }) => {
      stroke(ctx, style, rc.dpr);
      const [a, b] = extend(pts[0]!, pts[1]!, rc, false);
      line(ctx, a, b);
    },
    distance: (x, y, { pts }) => distToRay(x, y, pts[0]!, pts[1]!)
  });

  register({
    id: 'extended-line',
    name: 'Extended line',
    points: 2,
    draw: (ctx, { pts, style, rc }) => {
      stroke(ctx, style, rc.dpr);
      const [a, b] = extend(pts[0]!, pts[1]!, rc, true);
      line(ctx, a, b);
    },
    distance: (x, y, { pts }) => distToLine(x, y, pts[0]!, pts[1]!)
  });

  register({
    id: 'arrow',
    name: 'Arrow',
    points: 2,
    draw: (ctx, { pts, style, rc }) => {
      stroke(ctx, style, rc.dpr);
      line(ctx, pts[0]!, pts[1]!);
      arrowHead(ctx, pts[0]!, pts[1]!, 10 * rc.dpr, style.color ?? rc.theme.lineColor);
    },
    distance: (x, y, { pts }) => distToSegment(x, y, pts[0]!, pts[1]!)
  });

  register({
    id: 'horizontal-line',
    name: 'Horizontal line',
    points: 1,
    shortcut: 'Alt+H',
    defaultStyle: { showLabels: true },
    draw: (ctx, args) => horizontal(ctx, args, false),
    // A horizontal line is everywhere along x, so only the price matters.
    distance: (_x, y, { pts }) => Math.abs(y - pts[0]!.y)
  });

  register({
    id: 'horizontal-ray',
    name: 'Horizontal ray',
    points: 1,
    shortcut: 'Alt+J',
    defaultStyle: { showLabels: true },
    draw: (ctx, args) => horizontal(ctx, args, true),
    distance: (x, y, { pts }) =>
      x < pts[0]!.x ? Math.hypot(x - pts[0]!.x, y - pts[0]!.y) : Math.abs(y - pts[0]!.y)
  });

  register({
    id: 'vertical-line',
    name: 'Vertical line',
    points: 1,
    shortcut: 'Alt+V',
    draw: (ctx, { pts, style, rc }) => {
      stroke(ctx, style, rc.dpr);
      const x = pts[0]!.x;
      line(ctx, { x, y: 0 }, { x, y: rc.plotHeight * rc.dpr });
    },
    distance: (x, _y, { pts }) => Math.abs(x - pts[0]!.x)
  });

  register({
    id: 'cross-line',
    name: 'Cross line',
    points: 1,
    shortcut: 'Alt+C',
    draw: (ctx, { pts, style, rc }) => {
      stroke(ctx, style, rc.dpr);
      const { x, y } = pts[0]!;
      line(ctx, { x, y: 0 }, { x, y: rc.plotHeight * rc.dpr });
      line(ctx, { x: 0, y }, { x: rc.plotWidth * rc.dpr, y });
    },
    // Either arm will do — whichever the cursor is nearer to.
    distance: (x, y, { pts }) => Math.min(Math.abs(x - pts[0]!.x), Math.abs(y - pts[0]!.y))
  });
}

/**
 * The shared body of the two horizontal tools.
 *
 * The price tag on the right edge is what makes these worth having over a plain
 * trend line: the reader wants the number, not the line.
 */
function horizontal(
  ctx: CanvasRenderingContext2D,
  { pts, drawing, style, rc }: DrawArgs,
  ray: boolean
): void {
  const dpr = rc.dpr;
  const width = rc.plotWidth * dpr;
  const y = pts[0]!.y;
  stroke(ctx, style, dpr);
  line(ctx, { x: ray ? pts[0]!.x : 0, y }, { x: width, y });
  if (style.showLabels === false) return;
  const price = drawing.points[0]?.price;
  if (price === undefined) return;
  inlineLabel(ctx, rc.priceScale.format(price), width, y, rc, style, { align: 'right' });
}

/** Re-exported so the tests can reach the geometry without a canvas. */
export type { DistanceArgs };
