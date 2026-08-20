import { DrawingPrimitive } from './DrawingPrimitive';
import type { DrawingPoint } from './types';

/** A straight line between two anchors — the simplest drawing, and the template the others follow. */
export class TrendLinePrimitive extends DrawingPrimitive {
  constructor(
    public a: DrawingPoint,
    public b: DrawingPoint,
    public color: string
  ) {
    super();
  }

  protected draw(ctx: CanvasRenderingContext2D): void {
    const p1 = this.toPixel(this.a);
    const p2 = this.toPixel(this.b);
    if (!p1 || !p2) return;

    ctx.save();
    ctx.strokeStyle = this.color;
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(p1.x, p1.y);
    ctx.lineTo(p2.x, p2.y);
    ctx.stroke();
    ctx.restore();
  }
}
