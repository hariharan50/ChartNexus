import { DrawingPrimitive } from './DrawingPrimitive';
import type { DrawingPoint } from './types';
import { withAlpha } from '../../theme/tokens';

/** A filled, outlined box between two opposite corners. */
export class RectanglePrimitive extends DrawingPrimitive {
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

    const x = Math.min(p1.x, p2.x);
    const y = Math.min(p1.y, p2.y);
    const width = Math.abs(p2.x - p1.x);
    const height = Math.abs(p2.y - p1.y);

    ctx.save();
    ctx.fillStyle = withAlpha(this.color, 0.12);
    ctx.strokeStyle = this.color;
    ctx.lineWidth = 1.5;
    ctx.fillRect(x, y, width, height);
    ctx.strokeRect(x, y, width, height);
    ctx.restore();
  }
}
