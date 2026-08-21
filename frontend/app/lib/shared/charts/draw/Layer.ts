/**
 * One pane's worth of drawings, as a paintable and hit-testable unit.
 *
 * The layer is where the chart-space rule is actually enforced: it holds
 * `Drawing`s, whose anchors are `{time, price}`, and re-projects every one of
 * them on every frame. Nothing here caches a pixel. That is what makes pan,
 * zoom, resize, a timeframe change and a full chart rebuild all no-ops as far
 * as the drawings are concerned — there is no stale coordinate to invalidate.
 *
 * Unit discipline, restated because it is the one trap: `draw()` hands tools
 * **device px**, `hitTest()` works in **CSS px**. See `render.ts`.
 */

import { BODY_HIT, HANDLE_HIT, PREVIEW_ALPHA } from './constants';
import type { Pt } from './geometry';
import { drawHandles, handleIndices, project } from './render';
import { get, has } from './registry';
import type { Drawing, HitResult, Primitive, RenderContext } from './types';

/** The id the in-progress shape carries. Never in `_drawings`, never in JSON. */
export const PREVIEW_ID = '__preview';

export class Layer implements Primitive {
  private drawings: Drawing[] = [];
  private preview: Drawing | null = null;
  private selectedId: string | null = null;

  setDrawings(drawings: Drawing[]): void {
    this.drawings = drawings;
  }

  setPreview(preview: Drawing | null): void {
    this.preview = preview;
  }

  setSelected(id: string | null): void {
    this.selectedId = id;
  }

  zOrder(): 'top' {
    return 'top';
  }

  /** Always null — a drawing must never move the price scale. */
  autoscaleInfo(): null {
    return null;
  }

  draw(ctx: CanvasRenderingContext2D, rc: RenderContext): void {
    const all = this.preview ? [...this.drawings, this.preview] : this.drawings;
    for (const drawing of all) {
      if (drawing.visible === false) continue;
      // Forward compatibility: a shape saved by a newer build must be skipped,
      // not thrown on. Losing one drawing beats losing the whole layer.
      if (!has(drawing.tool)) continue;
      const def = get(drawing.tool);
      if (drawing.points.length < Math.max(1, def.points)) continue;

      const css = drawing.points.map((p) => project(rc, p.time, p.price));
      // Off-screen entirely: every anchor unprojectable. A shape with one anchor
      // off screen still has to draw, or a trend line would vanish the moment
      // one end scrolled out of view.
      if (css.every((p) => !Number.isFinite(p.x) || !Number.isFinite(p.y))) continue;

      const style = { color: rc.theme.lineColor, lineWidth: 1.5, ...drawing.style };
      ctx.save();
      if (drawing.id === PREVIEW_ID) ctx.globalAlpha = PREVIEW_ALPHA;
      const device: Pt[] = css.map((p) => ({ x: p.x * rc.dpr, y: p.y * rc.dpr }));
      try {
        def.draw(ctx, { pts: device, drawing, style, rc });
      } catch {
        // A tool that throws mid-frame would otherwise leave the canvas in
        // whatever state it got to and take the rest of the layer with it.
      }
      ctx.restore();

      if (drawing.id === this.selectedId && drawing.locked !== true) {
        drawHandles(ctx, css, handleIndices(drawing, def.freehand === true), rc);
      }
    }
  }

  /**
   * Handles first, then bodies top-most first.
   *
   * The ordering is the whole usability of dragging: a handle sits *on* its
   * drawing, so testing bodies first would mean the reader could never grab an
   * endpoint — every attempt would pick up the shape and move the lot.
   */
  hitTest(x: number, y: number, rc: RenderContext): HitResult | null {
    const selected = this.drawings.find((d) => d.id === this.selectedId);
    if (selected && selected.locked !== true && has(selected.tool)) {
      const def = get(selected.tool);
      const pts = selected.points.map((p) => project(rc, p.time, p.price));
      for (const i of handleIndices(selected, def.freehand === true)) {
        const p = pts[i];
        if (!p) continue;
        if (Math.hypot(x - p.x, y - p.y) <= HANDLE_HIT) {
          return {
            externalId: `draw:${selected.id}#${i}`,
            cursor: 'grabbing',
            draggable: true,
            distance: 0
          };
        }
      }
    }

    let best: HitResult | null = null;
    for (let i = this.drawings.length - 1; i >= 0; i -= 1) {
      const drawing = this.drawings[i]!;
      if (drawing.visible === false || drawing.locked === true) continue;
      if (!has(drawing.tool)) continue;
      const def = get(drawing.tool);
      const pts = drawing.points.map((p) => project(rc, p.time, p.price));
      if (pts.length < Math.max(1, def.points)) continue;
      let distance: number;
      try {
        distance = def.distance(x, y, { pts, drawing, rc });
      } catch {
        continue;
      }
      if (!Number.isFinite(distance) || distance > BODY_HIT) continue;
      if (!best || distance < best.distance) {
        best = { externalId: `draw:${drawing.id}`, cursor: 'move', draggable: true, distance };
      }
    }
    return best;
  }
}
