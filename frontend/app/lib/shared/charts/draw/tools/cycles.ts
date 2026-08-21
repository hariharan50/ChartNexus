/**
 * Cycle tools: three ways of saying "this interval, repeated".
 *
 * All three take one span between two anchors and tile it across the plot.
 * Cyclic lines mark each repeat with a vertical, time cycles with a semicircle,
 * and the sine line draws the wave itself. Only the fourth of these — the
 * period — carries any meaning; the price of the second anchor is used solely
 * to give the sine an amplitude.
 */

import { distToPolyline, distToVerticals, type Pt } from '../geometry';
import { line, polyline, stroke } from '../render';
import { register } from '../registry';

/** How far past the anchors to keep tiling, as a multiple of the span. */
const REPEATS = 12;

export function registerCycles(): void {
  register({
    id: 'cyclic-lines',
    name: 'Cyclic lines',
    points: 2,
    defaultStyle: { lineStyle: 'dashed' },
    draw: (ctx, { pts, style, rc }) => {
      stroke(ctx, style, rc.dpr);
      const height = rc.plotHeight * rc.dpr;
      for (const x of tiles(pts[0]!.x, pts[1]!.x, rc.plotWidth * rc.dpr)) {
        line(ctx, { x, y: 0 }, { x, y: height });
      }
    },
    distance: (x, _y, { pts, rc }) => distToVerticals(x, tiles(pts[0]!.x, pts[1]!.x, rc.plotWidth))
  });

  register({
    id: 'time-cycles',
    name: 'Time cycles',
    points: 2,
    draw: (ctx, { pts, style, rc }) => {
      stroke(ctx, style, rc.dpr);
      const span = Math.abs(pts[1]!.x - pts[0]!.x);
      if (span <= 0) return;
      const baseline = Math.max(pts[0]!.y, pts[1]!.y);
      // Half-circles sitting on the later anchor's price — the classic cycle
      // arcs, where each crossing of the baseline is a projected turning point.
      for (const x of tiles(pts[0]!.x, pts[1]!.x, rc.plotWidth * rc.dpr)) {
        ctx.beginPath();
        ctx.arc(x - span / 2, baseline, span / 2, Math.PI, 0);
        ctx.stroke();
      }
    },
    distance: (x, y, { pts, rc }) => {
      const span = Math.abs(pts[1]!.x - pts[0]!.x);
      if (span <= 0) return Infinity;
      const baseline = Math.max(pts[0]!.y, pts[1]!.y);
      const r = span / 2;
      let best = Infinity;
      for (const cx of tiles(pts[0]!.x, pts[1]!.x, rc.plotWidth)) {
        // Only the upper half exists, so a cursor below the baseline measures to
        // the nearest end of the arc rather than through it.
        const d =
          y <= baseline
            ? Math.abs(Math.hypot(x - (cx - r), y - baseline) - r)
            : Math.hypot(x - (cx - r), y - baseline) - r;
        best = Math.min(best, Math.abs(d));
      }
      return best;
    }
  });

  register({
    id: 'sine-line',
    name: 'Sine line',
    points: 2,
    draw: (ctx, { pts, style, rc }) => {
      stroke(ctx, style, rc.dpr);
      polyline(ctx, sine(pts[0]!, pts[1]!, rc.plotWidth * rc.dpr));
    },
    distance: (x, y, { pts, rc }) => distToPolyline(x, y, sine(pts[0]!, pts[1]!, rc.plotWidth))
  });
}

/** Every repeat of the span that lands inside the plot, starting at the first anchor. */
function tiles(from: number, to: number, width: number): number[] {
  const span = to - from;
  if (span === 0 || !Number.isFinite(span)) return [from];
  const step = Math.abs(span);
  const out: number[] = [];
  for (let i = -REPEATS; i <= REPEATS; i += 1) {
    const x = from + step * i;
    if (x >= -step && x <= width + step) out.push(x);
  }
  return out;
}

/** One period per span, amplitude from the anchors' price gap. */
function sine(a: Pt, b: Pt, width: number): Pt[] {
  const period = Math.abs(b.x - a.x);
  if (period <= 0) return [a, b];
  const amplitude = (b.y - a.y) / 2;
  const mid = (a.y + b.y) / 2;
  const out: Pt[] = [];
  const step = Math.max(2, period / 48);
  for (
    let x = a.x - period * REPEATS;
    x <= Math.min(width + period, a.x + period * REPEATS);
    x += step
  ) {
    out.push({ x, y: mid - amplitude * Math.sin(((x - a.x) / period) * Math.PI * 2) });
  }
  return out;
}
