import { DrawingPrimitive } from './DrawingPrimitive';
import type { DrawingPoint } from './types';

/** A short label anchored to one point. */
export class TextPrimitive extends DrawingPrimitive {
  constructor(
    public at: DrawingPoint,
    public text: string,
    public color: string
  ) {
    super();
  }

  protected draw(ctx: CanvasRenderingContext2D): void {
    const p = this.toPixel(this.at);
    if (!p) return;

    ctx.save();
    ctx.font = '600 12px sans-serif';
    ctx.textBaseline = 'bottom';
    ctx.fillStyle = this.color;
    ctx.fillText(this.text, p.x + 4, p.y - 4);
    ctx.restore();
  }
}
