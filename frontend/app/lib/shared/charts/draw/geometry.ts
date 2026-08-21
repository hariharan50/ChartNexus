/**
 * Point-to-shape distances, in CSS pixels.
 *
 * Every tool's `distance()` reduces to one of these. They are pure and take
 * plain numbers, which is the whole reason hit testing is testable without a
 * canvas: "is the cursor on this trend line" is a segment-distance question,
 * not a rendering question.
 */

export interface Pt {
  x: number;
  y: number;
}

/** Distance from `p` to the finite segment `a`-`b`. */
export function distToSegment(px: number, py: number, a: Pt, b: Pt): number {
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  const lenSq = dx * dx + dy * dy;
  // A zero-length segment is a point; the projection below would divide by zero.
  if (lenSq === 0) return Math.hypot(px - a.x, py - a.y);
  let t = ((px - a.x) * dx + (py - a.y) * dy) / lenSq;
  t = Math.max(0, Math.min(1, t));
  return Math.hypot(px - (a.x + t * dx), py - (a.y + t * dy));
}

/**
 * Distance to the infinite line through `a` and `b`.
 *
 * What `extended-line` and the fan tools need — they are drawn clipped to the
 * plot, but conceptually they have no ends, and hit testing has to agree.
 */
export function distToLine(px: number, py: number, a: Pt, b: Pt): number {
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  const len = Math.hypot(dx, dy);
  if (len === 0) return Math.hypot(px - a.x, py - a.y);
  return Math.abs(dy * (px - a.x) - dx * (py - a.y)) / len;
}

/** Distance to a ray that starts at `a` and passes through `b`, extending past it forever. */
export function distToRay(px: number, py: number, a: Pt, b: Pt): number {
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  const lenSq = dx * dx + dy * dy;
  if (lenSq === 0) return Math.hypot(px - a.x, py - a.y);
  const t = Math.max(0, ((px - a.x) * dx + (py - a.y) * dy) / lenSq);
  return Math.hypot(px - (a.x + t * dx), py - (a.y + t * dy));
}

export function distToPolyline(px: number, py: number, pts: readonly Pt[]): number {
  if (pts.length === 0) return Infinity;
  if (pts.length === 1) return Math.hypot(px - pts[0]!.x, py - pts[0]!.y);
  let best = Infinity;
  for (let i = 1; i < pts.length; i += 1) {
    best = Math.min(best, distToSegment(px, py, pts[i - 1]!, pts[i]!));
  }
  return best;
}

/**
 * Distance to a rectangle: zero anywhere inside a filled one, otherwise the
 * distance to the nearest edge.
 *
 * `filled` matters for how the shape behaves under the cursor. A filled
 * rectangle is a region the reader thinks of as solid, so clicking its middle
 * should select it; an unfilled one is four lines, and clicking the hole in the
 * middle should fall through to whatever is behind.
 */
export function distToRect(
  px: number,
  py: number,
  x1: number,
  y1: number,
  x2: number,
  y2: number,
  filled: boolean
): number {
  const left = Math.min(x1, x2);
  const right = Math.max(x1, x2);
  const top = Math.min(y1, y2);
  const bottom = Math.max(y1, y2);
  const inside = px >= left && px <= right && py >= top && py <= bottom;
  if (inside && filled) return 0;
  if (inside) {
    return Math.min(px - left, right - px, py - top, bottom - py);
  }
  const dx = Math.max(left - px, 0, px - right);
  const dy = Math.max(top - py, 0, py - bottom);
  return Math.hypot(dx, dy);
}

/** Distance to an axis-aligned ellipse's outline, or 0 inside a filled one. */
export function distToEllipse(
  px: number,
  py: number,
  cx: number,
  cy: number,
  rx: number,
  ry: number,
  filled: boolean
): number {
  if (rx <= 0 || ry <= 0) return Math.hypot(px - cx, py - cy);
  const nx = (px - cx) / rx;
  const ny = (py - cy) / ry;
  const norm = Math.hypot(nx, ny);
  if (filled && norm <= 1) return 0;
  // Scale the normalised error back into pixels by the smaller radius, which is
  // the direction the outline is most sensitive in.
  return Math.abs(norm - 1) * Math.min(rx, ry);
}

/** Distance to a closed polygon's outline, or 0 inside a filled one. */
export function distToPolygon(px: number, py: number, pts: readonly Pt[], filled: boolean): number {
  if (pts.length < 2) return Infinity;
  if (filled && pointInPolygon(px, py, pts)) return 0;
  let best = Infinity;
  for (let i = 0; i < pts.length; i += 1) {
    const a = pts[i]!;
    const b = pts[(i + 1) % pts.length]!;
    best = Math.min(best, distToSegment(px, py, a, b));
  }
  return best;
}

/** Even-odd ray cast. */
export function pointInPolygon(px: number, py: number, pts: readonly Pt[]): boolean {
  let inside = false;
  for (let i = 0, j = pts.length - 1; i < pts.length; j = i, i += 1) {
    const a = pts[i]!;
    const b = pts[j]!;
    const straddles = a.y > py !== b.y > py;
    if (straddles && px < ((b.x - a.x) * (py - a.y)) / (b.y - a.y) + a.x) inside = !inside;
  }
  return inside;
}

/** The smallest distance to any of a set of horizontal lines. */
export function distToHorizontals(py: number, ys: readonly number[]): number {
  let best = Infinity;
  for (const y of ys) best = Math.min(best, Math.abs(py - y));
  return best;
}

/** The smallest distance to any of a set of vertical lines. */
export function distToVerticals(px: number, xs: readonly number[]): number {
  let best = Infinity;
  for (const x of xs) best = Math.min(best, Math.abs(px - x));
  return best;
}
