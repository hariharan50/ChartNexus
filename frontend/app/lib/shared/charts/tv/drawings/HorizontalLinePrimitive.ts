import { DrawingPrimitive } from './DrawingPrimitive';

/**
 * A dashed line across the full visible width at one price.
 *
 * Has no time of its own — unlike every other drawing here, so it draws from
 * the pane's own width rather than a second anchor point.
 */
export class HorizontalLinePrimitive extends DrawingPrimitive {
  constructor(
    public price: number,
    public color: string
  ) {
    super();
  }

  protected draw(ctx: CanvasRenderingContext2D): void {
    const y = this.series?.priceToCoordinate(this.price);
    if (y === null || y === undefined) return;
    const width = this.paneWidth();

    ctx.save();
    ctx.strokeStyle = this.color;
    ctx.lineWidth = 1.5;
    ctx.setLineDash([6, 4]);
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(width, y);
    ctx.stroke();
    ctx.restore();
  }
}
