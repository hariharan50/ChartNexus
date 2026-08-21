/**
 * Position and forecast tools — the three that do arithmetic rather than geometry.
 *
 * A long or short position is placed with a single click and expands into three
 * anchors: entry, target, stop. That `expand` is what makes the tool usable —
 * asking a reader to click three times to get a default risk box, before they
 * have seen it, is three chances to get it wrong.
 *
 * The numbers on them are the point. Position size follows from account size
 * and the percentage risked, so the target and stop labels answer "what does
 * this trade actually pay" rather than just "where are the lines".
 */

import { DOWN, UP } from '../constants';
import { distToRect } from '../geometry';
import { boxLabel, fillWith, inlineLabel, line, stroke } from '../render';
import { register, type DrawArgs } from '../registry';
import type { Bar, Point } from '../types';

export function registerPositions(): void {
  register({
    id: 'long-position',
    name: 'Long position',
    points: 1,
    defaultStyle: { accountSize: 1e5, risk: 1 },
    expand: (pts, ctx) => expandPosition(pts, ctx, 1),
    draw: (ctx, args) => position(ctx, args, 1),
    distance: (x, y, { pts }) => positionDistance(x, y, pts)
  });

  register({
    id: 'short-position',
    name: 'Short position',
    points: 1,
    defaultStyle: { accountSize: 1e5, risk: 1 },
    expand: (pts, ctx) => expandPosition(pts, ctx, -1),
    draw: (ctx, args) => position(ctx, args, -1),
    distance: (x, y, { pts }) => positionDistance(x, y, pts)
  });

  register({
    id: 'forecast',
    name: 'Forecast',
    points: 2,
    defaultStyle: { fill: true, fillOpacity: 0.12, lineStyle: 'dashed' },
    draw: (ctx, { pts, drawing, style, rc }) => {
      const a = pts[0]!;
      const b = pts[1]!;
      const rising = b.y <= a.y;
      const color = rising ? UP : DOWN;
      fillWith(ctx, style.fillColor ?? color, style.fillOpacity ?? 0.12, () =>
        ctx.fillRect(
          Math.min(a.x, b.x),
          Math.min(a.y, b.y),
          Math.abs(b.x - a.x),
          Math.abs(b.y - a.y)
        )
      );
      stroke(ctx, { ...style, color: style.color ?? color }, rc.dpr);
      line(ctx, a, b);
      inlineLabel(ctx, verdict(drawing.points, rc.bars?.()), b.x, b.y, rc, style, {
        align: 'left',
        place: 'above',
        background: color
      });
    },
    distance: (x, y, { pts }) => distToRect(x, y, pts[0]!.x, pts[0]!.y, pts[1]!.x, pts[1]!.y, true)
  });
}

/**
 * SUCCESS when any bar between the two anchors reached the projected price.
 *
 * Deliberately a range test rather than a close test: a forecast that was hit
 * intraday and gave the level back was still hit, and a reader looking at the
 * wick can see that it was.
 */
export function verdict(points: readonly Point[], bars: readonly Bar[] | undefined): string {
  const from = points[0];
  const to = points[1];
  if (!from || !to || !bars) return 'FORECAST';
  const lo = Math.min(from.time, to.time);
  const hi = Math.max(from.time, to.time);
  const rising = to.price >= from.price;
  for (const bar of bars) {
    if (bar.time < lo || bar.time > hi) continue;
    if (rising ? bar.high >= to.price : bar.low <= to.price) return 'SUCCESS';
  }
  return 'MISSED';
}

/**
 * One click becomes entry, target and stop.
 *
 * A percent of price for the distance and a fraction of the visible window for
 * the duration, so the default box is the same *shape* on a ₹200 stock and a
 * 24,000 index — an absolute default would be invisible on one and fill the
 * screen on the other.
 */
export function expandPosition(
  pts: Point[],
  ctx: { barSeconds: number; visibleBars: number },
  sign: 1 | -1
): Point[] {
  const entry = pts[0];
  if (!entry) return pts;
  const dp = Math.max(1, 0.01 * Math.abs(entry.price));
  const dt = Math.max(5, Math.round(0.08 * ctx.visibleBars)) * ctx.barSeconds;
  return [
    entry,
    { time: entry.time + dt, price: entry.price + dp * sign },
    { time: entry.time + dt, price: entry.price - dp * sign }
  ];
}

function position(
  ctx: CanvasRenderingContext2D,
  { pts, drawing, style, rc }: DrawArgs,
  sign: 1 | -1
): void {
  const entry = pts[0]!;
  const target = pts[1]!;
  const stop = pts[2]!;
  const left = entry.x;
  const right = Math.max(target.x, stop.x);
  const width = right - left;

  fillWith(ctx, UP, 0.18, () =>
    ctx.fillRect(left, Math.min(entry.y, target.y), width, Math.abs(target.y - entry.y))
  );
  fillWith(ctx, DOWN, 0.18, () =>
    ctx.fillRect(left, Math.min(entry.y, stop.y), width, Math.abs(stop.y - entry.y))
  );

  stroke(ctx, { ...style, color: style.color ?? rc.theme.lineColor }, rc.dpr);
  line(ctx, { x: left, y: entry.y }, { x: right, y: entry.y });
  ctx.strokeStyle = UP;
  line(ctx, { x: left, y: target.y }, { x: right, y: target.y });
  ctx.strokeStyle = DOWN;
  line(ctx, { x: left, y: stop.y }, { x: right, y: stop.y });

  const anchors = drawing.points;
  const entryPrice = anchors[0]?.price;
  const targetPrice = anchors[1]?.price;
  const stopPrice = anchors[2]?.price;
  if (entryPrice === undefined || targetPrice === undefined || stopPrice === undefined) return;

  const risk = Math.abs(entryPrice - stopPrice);
  const reward = Math.abs(targetPrice - entryPrice);
  const accountSize = style.accountSize ?? 1e5;
  const riskPercent = style.risk ?? 1;
  // Position size from the money at risk, which is the only way the amounts
  // below mean anything: risking one percent of the account across a wider stop
  // has to buy fewer units, not lose more money.
  const qty = risk > 0 ? (accountSize * riskPercent) / 100 / risk : 0;

  const text = [
    `Target: ${rc.priceScale.format(targetPrice)} (${pct(targetPrice, entryPrice)}%) Amount: ${money(qty * reward)}`,
    `Stop: ${rc.priceScale.format(stopPrice)} (${pct(stopPrice, entryPrice)}%) Amount: ${money(qty * risk)}`,
    `Risk/reward ratio: ${risk > 0 ? (reward / risk).toFixed(2) : '—'}`
  ].join('\n');

  boxLabel(
    ctx,
    text,
    left,
    sign === 1 ? Math.min(target.y, stop.y) : Math.max(target.y, stop.y),
    rc,
    {
      ...style,
      fontSize: style.fontSize ?? 11,
      background: true,
      backgroundColor: style.backgroundColor ?? rc.theme.background,
      border: true,
      borderColor: style.borderColor ?? style.color ?? rc.theme.lineColor,
      wrap: false
    },
    { align: 'left', place: sign === 1 ? 'above' : 'below' }
  );
}

function positionDistance(x: number, y: number, pts: readonly { x: number; y: number }[]): number {
  const entry = pts[0]!;
  const target = pts[1] ?? entry;
  const stop = pts[2] ?? entry;
  const right = Math.max(target.x, stop.x);
  return distToRect(
    x,
    y,
    entry.x,
    Math.min(target.y, stop.y),
    right,
    Math.max(target.y, stop.y),
    true
  );
}

function pct(price: number, entry: number): string {
  if (entry === 0) return '0.00';
  return (((price - entry) / entry) * 100).toFixed(2);
}

function money(value: number): string {
  return value.toLocaleString('en-IN', { maximumFractionDigits: 0 });
}
