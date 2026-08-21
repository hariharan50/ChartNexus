/**
 * Fibonacci, channels and Gann.
 *
 * All eight are the same idea applied to different axes: take a move the reader
 * marks out with two or three anchors, divide it by a fixed set of ratios, and
 * draw a line at each. Retracement divides price, the time zone divides time,
 * the fan divides slope, and the channel divides the gap between two parallels.
 * The ratios themselves live in `constants.ts` so the whole family stays in step.
 */

import { FAN_LEVELS, FIB_LEVELS, FIB_TIME_ZONES, GANN_RATIOS } from '../constants';
import {
  distToHorizontals,
  distToLine,
  distToSegment,
  distToVerticals,
  type Pt
} from '../geometry';
import { extend, inlineLabel, line, stroke, withFill } from '../render';
import { register, type DrawArgs, type DistanceArgs } from '../registry';

export function registerFib(): void {
  register({
    id: 'parallel-channel',
    name: 'Parallel channel',
    points: 3,
    defaultStyle: { fill: true },
    draw: (ctx, { pts, style, rc }) => {
      const [a, b, offset] = channelOf(pts);
      withFill(ctx, style, () => {
        ctx.beginPath();
        ctx.moveTo(a.x, a.y);
        ctx.lineTo(b.x, b.y);
        ctx.lineTo(b.x, b.y + offset);
        ctx.lineTo(a.x, a.y + offset);
        ctx.closePath();
        ctx.fill();
      });
      stroke(ctx, style, rc.dpr);
      line(ctx, a, b);
      line(ctx, { x: a.x, y: a.y + offset }, { x: b.x, y: b.y + offset });
    },
    distance: (x, y, { pts }) => {
      const [a, b, offset] = channelOf(pts);
      return Math.min(
        distToSegment(x, y, a, b),
        distToSegment(x, y, { x: a.x, y: a.y + offset }, { x: b.x, y: b.y + offset })
      );
    }
  });

  register({
    id: 'fib-channel',
    name: 'Fib channel',
    points: 3,
    defaultStyle: { levels: [...FIB_LEVELS] },
    draw: (ctx, { pts, style, rc }) => {
      const [a, b, offset] = channelOf(pts);
      stroke(ctx, style, rc.dpr);
      for (const level of style.levels ?? FIB_LEVELS) {
        const dy = offset * level;
        line(ctx, { x: a.x, y: a.y + dy }, { x: b.x, y: b.y + dy });
        if (style.showLabels !== false) {
          inlineLabel(ctx, level.toFixed(3), b.x, b.y + dy, rc, style, { align: 'right' });
        }
      }
    },
    distance: (x, y, { pts, drawing }) => {
      const [a, b, offset] = channelOf(pts);
      let best = Infinity;
      for (const level of drawing.style.levels ?? FIB_LEVELS) {
        const dy = offset * level;
        best = Math.min(
          best,
          distToSegment(x, y, { x: a.x, y: a.y + dy }, { x: b.x, y: b.y + dy })
        );
      }
      return best;
    }
  });

  register({
    id: 'fib-retracement',
    name: 'Fib retracement',
    points: 2,
    defaultStyle: {
      levels: [...FIB_LEVELS],
      showLabels: true,
      fill: true,
      fillOpacity: 0.06
    },
    draw: (ctx, args) => fibLevels(ctx, args, (a, b, level) => a.y + (b.y - a.y) * level),
    distance: (x, y, args) => fibDistance(x, y, args, (a, b, level) => a.y + (b.y - a.y) * level)
  });

  register({
    id: 'fib-extension',
    name: 'Fib extension',
    points: 3,
    defaultStyle: {
      levels: [...FIB_LEVELS],
      showLabels: true,
      fill: true,
      fillOpacity: 0.06
    },
    // The extension projects the first leg's height from the third anchor, which
    // is what makes it a target tool rather than a pullback one.
    draw: (ctx, args) => fibLevels(ctx, args, (a, b, level, c) => (c ?? b).y + (b.y - a.y) * level),
    distance: (x, y, args) =>
      fibDistance(x, y, args, (a, b, level, c) => (c ?? b).y + (b.y - a.y) * level)
  });

  register({
    id: 'fib-time-zone',
    name: 'Fib time zone',
    points: 2,
    defaultStyle: { levels: [...FIB_TIME_ZONES] },
    draw: (ctx, { pts, style, rc }) => {
      stroke(ctx, style, rc.dpr);
      const span = pts[1]!.x - pts[0]!.x;
      const height = rc.plotHeight * rc.dpr;
      for (const step of style.levels ?? FIB_TIME_ZONES) {
        const x = pts[0]!.x + span * step;
        line(ctx, { x, y: 0 }, { x, y: height });
        if (style.showLabels !== false) {
          inlineLabel(ctx, String(step), x, height, rc, style, { align: 'center', place: 'above' });
        }
      }
    },
    distance: (x, _y, { pts, drawing }) => {
      const span = pts[1]!.x - pts[0]!.x;
      return distToVerticals(
        x,
        (drawing.style.levels ?? FIB_TIME_ZONES).map((step) => pts[0]!.x + span * step)
      );
    }
  });

  register({
    id: 'fib-fan',
    name: 'Fib fan',
    points: 2,
    defaultStyle: { levels: [...FAN_LEVELS] },
    draw: (ctx, { pts, style, rc }) => {
      stroke(ctx, style, rc.dpr);
      for (const level of style.levels ?? FAN_LEVELS) {
        const through = { x: pts[1]!.x, y: pts[0]!.y + (pts[1]!.y - pts[0]!.y) * level };
        const [, far] = extend(pts[0]!, through, rc, false);
        line(ctx, pts[0]!, far);
      }
    },
    distance: (x, y, { pts, drawing }) => {
      let best = Infinity;
      for (const level of drawing.style.levels ?? FAN_LEVELS) {
        const through = { x: pts[1]!.x, y: pts[0]!.y + (pts[1]!.y - pts[0]!.y) * level };
        best = Math.min(best, distToLine(x, y, pts[0]!, through));
      }
      return best;
    }
  });

  register({
    id: 'gann-fan',
    name: 'Gann fan',
    points: 2,
    defaultStyle: { showLabels: true },
    draw: (ctx, { pts, style, rc }) => {
      stroke(ctx, style, rc.dpr);
      const dx = pts[1]!.x - pts[0]!.x;
      const dy = pts[1]!.y - pts[0]!.y;
      for (const [t, p] of GANN_RATIOS) {
        const through = { x: pts[0]!.x + dx * t, y: pts[0]!.y + dy * p };
        const [, far] = extend(pts[0]!, through, rc, false);
        line(ctx, pts[0]!, far);
        if (style.showLabels !== false) {
          // 1x2 reads "one unit of price to two of time" — Gann's own notation,
          // and the reason the ratios are stored as pairs rather than slopes.
          inlineLabel(ctx, `${1 / p}x${1 / t}`, through.x, through.y, rc, style, {
            align: 'center'
          });
        }
      }
    },
    distance: (x, y, { pts }) => {
      const dx = pts[1]!.x - pts[0]!.x;
      const dy = pts[1]!.y - pts[0]!.y;
      let best = Infinity;
      for (const [t, p] of GANN_RATIOS) {
        best = Math.min(
          best,
          distToLine(x, y, pts[0]!, { x: pts[0]!.x + dx * t, y: pts[0]!.y + dy * p })
        );
      }
      return best;
    }
  });

  register({
    id: 'gann-box',
    name: 'Gann box',
    points: 2,
    defaultStyle: { fill: true, fillOpacity: 0.05, levels: [0, 0.25, 0.5, 0.75, 1] },
    draw: (ctx, { pts, style, rc }) => {
      const a = pts[0]!;
      const b = pts[1]!;
      withFill(ctx, style, () =>
        ctx.fillRect(
          Math.min(a.x, b.x),
          Math.min(a.y, b.y),
          Math.abs(b.x - a.x),
          Math.abs(b.y - a.y)
        )
      );
      stroke(ctx, style, rc.dpr);
      const levels = style.levels ?? [0, 0.25, 0.5, 0.75, 1];
      for (const level of levels) {
        const y = a.y + (b.y - a.y) * level;
        line(ctx, { x: a.x, y }, { x: b.x, y });
        const x = a.x + (b.x - a.x) * level;
        line(ctx, { x, y: a.y }, { x, y: b.y });
      }
    },
    distance: (x, y, { pts, drawing }) => {
      const a = pts[0]!;
      const b = pts[1]!;
      const levels = drawing.style.levels ?? [0, 0.25, 0.5, 0.75, 1];
      return Math.min(
        distToHorizontals(
          y,
          levels.map((l) => a.y + (b.y - a.y) * l)
        ),
        distToVerticals(
          x,
          levels.map((l) => a.x + (b.x - a.x) * l)
        )
      );
    }
  });
}

/** The two rails of a channel plus the vertical gap between them, in the drawn space. */
function channelOf(pts: readonly Pt[]): [Pt, Pt, number] {
  const a = pts[0]!;
  const b = pts[1]!;
  const c = pts[2] ?? b;
  // The third anchor only contributes its distance from the base line, measured
  // vertically — a channel's rails are parallel by definition, so its x is free.
  const t = b.x === a.x ? 0 : (c.x - a.x) / (b.x - a.x);
  const baseY = a.y + (b.y - a.y) * t;
  return [a, b, c.y - baseY];
}

type LevelY = (a: Pt, b: Pt, level: number, c?: Pt) => number;

function fibLevels(
  ctx: CanvasRenderingContext2D,
  { pts, style, rc }: DrawArgs,
  levelY: LevelY
): void {
  const a = pts[0]!;
  const b = pts[1]!;
  const c = pts[2];
  const levels = style.levels ?? FIB_LEVELS;
  const left = Math.min(a.x, b.x, c?.x ?? a.x);
  const right = rc.plotWidth * rc.dpr;

  // The band between the outermost levels, so the zone reads as one region
  // rather than as a stack of unrelated lines.
  if (style.fill === true && levels.length > 1) {
    const first = levelY(a, b, levels[0]!, c);
    const last = levelY(a, b, levels[levels.length - 1]!, c);
    withFill(ctx, style, () =>
      ctx.fillRect(left, Math.min(first, last), right - left, Math.abs(last - first))
    );
  }

  stroke(ctx, style, rc.dpr);
  for (const level of levels) {
    const y = levelY(a, b, level, c);
    line(ctx, { x: left, y }, { x: right, y });
    if (style.showLabels !== false) {
      const price = rc.priceScale.format(priceAt(rc, y));
      inlineLabel(ctx, `${level.toFixed(3)}  ${price}`, left, y, rc, style, { place: 'above' });
    }
  }
}

function fibDistance(x: number, y: number, { pts, drawing }: DistanceArgs, levelY: LevelY): number {
  const a = pts[0]!;
  const b = pts[1]!;
  const c = pts[2];
  const levels = drawing.style.levels ?? FIB_LEVELS;
  void x;
  return distToHorizontals(
    y,
    levels.map((level) => levelY(a, b, level, c))
  );
}

/**
 * Reads a price back off a y in device px.
 *
 * The render context only projects forwards, so this inverts by sampling: the
 * price scale is linear over any single frame's worth of pixels, which is all
 * this needs to label a level the reader can see.
 */
function priceAt(rc: RenderContextLike, deviceY: number): number {
  const y = deviceY / rc.dpr;
  const y0 = rc.priceScale.priceToY(0);
  const y1 = rc.priceScale.priceToY(100);
  if (y0 === y1) return 0;
  return ((y - y0) / (y1 - y0)) * 100;
}

interface RenderContextLike {
  dpr: number;
  priceScale: { priceToY(p: number): number };
}
