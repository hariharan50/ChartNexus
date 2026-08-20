import type { UTCTimestamp } from 'lightweight-charts';
import { DrawingPrimitive } from './DrawingPrimitive';
import { fibLevelPrices } from './fib-levels';
import type { DrawingPoint } from './types';
import { withAlpha } from '../../theme/tokens';

/** The standard retracement levels between two anchors, each labelled with its ratio and price. */
export class FibRetracementPrimitive extends DrawingPrimitive {
  constructor(
    public a: DrawingPoint,
    public b: DrawingPoint,
    public color: string
  ) {
    super();
  }

  protected draw(ctx: CanvasRenderingContext2D): void {
    const x1 = this.chart?.timeScale().timeToCoordinate(this.a.time as UTCTimestamp) ?? null;
    const x2 = this.chart?.timeScale().timeToCoordinate(this.b.time as UTCTimestamp) ?? null;
    if (x1 === null || x2 === null || !this.series) return;

    const left = Math.min(x1, x2);
    const right = Math.max(x1, x2);
    const levels = fibLevelPrices(this.a.price, this.b.price);

    ctx.save();
    ctx.font = '11px sans-serif';
    ctx.textBaseline = 'bottom';
    for (const { level, price } of levels) {
      const y = this.series.priceToCoordinate(price);
      if (y === null) continue;

      ctx.strokeStyle = withAlpha(this.color, level === 0 || level === 1 ? 0.9 : 0.5);
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(left, y);
      ctx.lineTo(right, y);
      ctx.stroke();

      ctx.fillStyle = this.color;
      ctx.fillText(`${(level * 100).toFixed(1)}% (${price.toFixed(2)})`, left + 4, y - 2);
    }
    ctx.restore();
  }
}
