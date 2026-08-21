/**
 * The chart types that are a different *series*, not a different picture.
 *
 * Heikin Ashi, Renko, Range Bars and Line Break all draw as candlesticks, but
 * the candles they draw are not the ones that came off the feed — they are
 * derived from them. That derivation lives here, as pure functions over
 * `Candle[]`, for the same reason the indicator arithmetic does: it is the part
 * that can be wrong in ways a screenshot will not show, and it is testable
 * without a chart, a canvas or a browser.
 *
 * Applied by the caller (`ChartCell`) rather than inside `LwChart`, so that the
 * indicators drawn over the top are computed from the bars actually on screen.
 * Transform in the renderer and an SMA on a Heikin Ashi chart would be an SMA
 * of prices nobody is looking at.
 */

import type { Candle, ChartType } from './LwChart';

/** Types whose bars are derived rather than the feed's own. */
const TRANSFORMED: ReadonlySet<ChartType> = new Set<ChartType>([
  'heikin',
  'renko',
  'range',
  'linebreak'
]);

/**
 * Whether a type keeps one output bar per input bar, at its original timestamp.
 *
 * Renko, Range Bars and Line Break do not: they emit a bar when *price* has
 * moved far enough, however many feed bars that took, so their bar count and
 * their spacing along the time axis are both untethered from the original.
 * Anything keyed to the original timestamps — the volume histogram above all —
 * cannot be drawn beside them and has to be dropped instead of silently
 * misaligned.
 */
export function preservesBars(type: ChartType): boolean {
  return type !== 'renko' && type !== 'range' && type !== 'linebreak';
}

/** The derived candles for a type, or the input untouched when it draws the feed as-is. */
export function transformCandles(type: ChartType, candles: Candle[]): Candle[] {
  if (!TRANSFORMED.has(type) || candles.length === 0) return candles;

  switch (type) {
    case 'heikin':
      return heikinAshi(candles);
    case 'renko':
      return renko(candles, boxSize(candles));
    case 'range':
      return rangeBars(candles, boxSize(candles));
    case 'linebreak':
      return lineBreak(candles);
    default:
      return candles;
  }
}

/**
 * Heikin Ashi: each bar averaged into the one before it.
 *
 * The point is that consecutive bars share an edge — an HA open is the midpoint
 * of the previous HA bar — so noise cancels and a run of one colour reads as a
 * trend. That also means it is *not* a price you can trade against: the close
 * is an average, not something that ever printed.
 */
export function heikinAshi(candles: Candle[]): Candle[] {
  const out: Candle[] = [];
  let prevOpen = 0;
  let prevClose = 0;

  for (let i = 0; i < candles.length; i += 1) {
    const bar = candles[i]!;
    const close = (bar.open + bar.high + bar.low + bar.close) / 4;
    // The first bar has no previous HA bar to average against, so it seeds from
    // its own body.
    const open = i === 0 ? (bar.open + bar.close) / 2 : (prevOpen + prevClose) / 2;
    out.push({
      time: bar.time,
      open,
      close,
      high: Math.max(bar.high, open, close),
      low: Math.min(bar.low, open, close)
    });
    prevOpen = open;
    prevClose = close;
  }

  return out;
}

/**
 * Renko: a brick every time price moves `box`, and nothing at all when it doesn't.
 *
 * Reversals need *two* boxes, which is the traditional rule and the one
 * TradingView follows — a one-box reversal produces a stream of alternating
 * bricks in a range and defeats the whole purpose of the chart, which is to
 * make a directionless market take up no space.
 */
export function renko(candles: Candle[], box: number): Candle[] {
  if (box <= 0 || candles.length === 0) return [];

  const out: Candle[] = [];
  let anchor = candles[0]!.close;
  let direction = 0;

  for (const candle of candles) {
    const close = candle.close;
    for (;;) {
      const upNeeded = direction === -1 ? box * 2 : box;
      const downNeeded = direction === 1 ? box * 2 : box;

      if (close >= anchor + upNeeded) {
        // On a reversal the new brick starts one box away from the anchor —
        // that gap is what the two-box rule is.
        const open = direction === -1 ? anchor + box : anchor;
        out.push(brick(candle.time, open, open + box));
        anchor = open + box;
        direction = 1;
        continue;
      }

      if (close <= anchor - downNeeded) {
        const open = direction === 1 ? anchor - box : anchor;
        out.push(brick(candle.time, open, open - box));
        anchor = open - box;
        direction = -1;
        continue;
      }

      break;
    }
  }

  return withDistinctTimes(out);
}

/**
 * Range bars: a bar every time the high-to-low span reaches `range`.
 *
 * Unlike Renko this keeps the highs and lows it actually saw, so a violent bar
 * is one bar rather than six bricks — the trade-off being that it says nothing
 * about how long that move took.
 */
export function rangeBars(candles: Candle[], range: number): Candle[] {
  if (range <= 0 || candles.length === 0) return [];

  const out: Candle[] = [];
  let open = candles[0]!.open;
  let high = candles[0]!.high;
  let low = candles[0]!.low;

  for (const candle of candles) {
    high = Math.max(high, candle.high);
    low = Math.min(low, candle.low);
    const close = candle.close;

    // A single feed bar can span several ranges at once — a gap, or one violent
    // minute — so this closes as many as it has to rather than one per bar.
    while (high - low >= range) {
      const rising = close >= open;
      const boundary = rising ? low + range : high - range;
      out.push({
        time: candle.time,
        open,
        close: boundary,
        high: rising ? boundary : high,
        low: rising ? low : boundary
      });
      // Whatever is left of the move opens the next bar.
      open = boundary;
      high = Math.max(boundary, close);
      low = Math.min(boundary, close);
    }
  }

  return withDistinctTimes(out);
}

/**
 * Line Break: a new line only when the close clears the last `lines` of them.
 *
 * Three is the standard and the reason the chart is usually called "Three Line
 * Break" — a reversal has to beat three lines' worth of extremes, so shallow
 * pullbacks draw nothing.
 */
export function lineBreak(candles: Candle[], lines = 3): Candle[] {
  if (candles.length === 0) return [];

  const out: Candle[] = [];
  const first = candles[0]!;
  out.push(brick(first.time, first.open, first.close));

  for (const candle of candles.slice(1)) {
    const close = candle.close;
    const recent = out.slice(-lines);
    const ceiling = Math.max(...recent.map((line) => Math.max(line.open, line.close)));
    const floor = Math.min(...recent.map((line) => Math.min(line.open, line.close)));
    const last = out[out.length - 1]!;

    if (close > ceiling) {
      out.push(brick(candle.time, Math.max(last.open, last.close), close));
    } else if (close < floor) {
      out.push(brick(candle.time, Math.min(last.open, last.close), close));
    }
  }

  return withDistinctTimes(out);
}

/**
 * The brick/range size, from average true range.
 *
 * A fixed number of points cannot work across a ₹200 stock and a 24,000 index,
 * and asking the reader for one before showing them anything is worse. ATR
 * scales itself, which is what TradingView's own "ATR" box-size mode does.
 */
export function boxSize(candles: Candle[], period = 14): number {
  if (candles.length === 0) return 0;

  const window = candles.slice(-Math.max(period, 2));
  let sum = 0;
  for (let i = 0; i < window.length; i += 1) {
    const bar = window[i]!;
    const prev = window[i - 1];
    const trueRange = prev
      ? Math.max(
          bar.high - bar.low,
          Math.abs(bar.high - prev.close),
          Math.abs(bar.low - prev.close)
        )
      : bar.high - bar.low;
    sum += trueRange;
  }

  const atr = sum / window.length;
  // A flat window — a halted instrument, or mock data with no movement — would
  // otherwise hand back a zero box and produce either nothing or an endless
  // loop. Fall back to a fraction of price, and only give up if that is zero too.
  if (atr > 0) return atr;
  const last = candles[candles.length - 1]!.close;
  return last > 0 ? last * 0.001 : 0;
}

/** A body with no wick — what Renko and Line Break draw. */
function brick(time: number, open: number, close: number): Candle {
  return {
    time,
    open,
    close,
    high: Math.max(open, close),
    low: Math.min(open, close)
  };
}

/**
 * Nudges repeated timestamps forward a second each.
 *
 * These transforms can emit several bars off one feed bar, all carrying that
 * bar's time, and the library requires strictly ascending times — `LwChart`'s
 * own guard would otherwise keep only the last of them and quietly drop the
 * rest. A second is invisible against an intraday axis and keeps every brick.
 */
function withDistinctTimes(bars: Candle[]): Candle[] {
  let previous = -Infinity;
  for (const bar of bars) {
    if (bar.time <= previous) bar.time = previous + 1;
    previous = bar.time;
  }
  return bars;
}
