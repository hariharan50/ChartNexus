/**
 * Technical levels, derived from candles and nothing else.
 *
 * Every level this module produces carries the timeframe it was measured on
 * and the rule that produced it. That is not decoration: "previous day high"
 * computed from five-minute bars and from daily bars are the same number only
 * when the intraday series actually reaches back a full session, and a panel
 * that shows both without saying which is which is a panel that will quietly
 * disagree with the chart beside it.
 *
 * Nothing here is called institutional, smart-money, or a liquidity pool. A
 * swing high is a price where sellers won last time. Whether anyone defends it
 * again is not in this data.
 */

import type { Candle, VolumeBar } from '$shared/charts/tv/LwChart';

export type LevelKind =
  | 'previous_close'
  | 'previous_high'
  | 'previous_low'
  | 'day_high'
  | 'day_low'
  | 'open_range_high'
  | 'open_range_low'
  | 'vwap'
  | 'swing_high'
  | 'swing_low'
  | 'pivot'
  | 'atr_band'
  | 'gap';

export interface Level {
  kind: LevelKind;
  label: string;
  price: number;
  /** The bar size this was measured on, e.g. `5m` or `1d`. */
  timeframe: string;
  /** How it was calculated, in one sentence. */
  method: string;
  /** Epoch seconds of the last bar that contributed. */
  asOf?: number | undefined;
}

/** IST is a fixed UTC+5:30 offset; a chart timestamp is epoch seconds. */
const IST_OFFSET_SECONDS = 5.5 * 3600;

/** Minutes past IST midnight when the cash session opens. */
const SESSION_OPEN_MINUTES = 9 * 60 + 15;

/** The opening range the terminal draws, in minutes from the bell. */
export const OPENING_RANGE_MINUTES = 15;

/** The IST calendar day a bar belongs to, as `YYYY-MM-DD`. */
export function istDay(timeSeconds: number): string {
  return new Date((timeSeconds + IST_OFFSET_SECONDS) * 1000).toISOString().slice(0, 10);
}

/** Minutes past IST midnight for a bar. */
export function istMinutes(timeSeconds: number): number {
  const shifted = new Date((timeSeconds + IST_OFFSET_SECONDS) * 1000);
  return shifted.getUTCHours() * 60 + shifted.getUTCMinutes();
}

/** Candles grouped by IST session date, in order. */
export function bySession(candles: Candle[]): { day: string; bars: Candle[] }[] {
  const sessions: { day: string; bars: Candle[] }[] = [];
  for (const candle of candles) {
    const day = istDay(candle.time);
    const last = sessions[sessions.length - 1];
    if (last && last.day === day) last.bars.push(candle);
    else sessions.push({ day, bars: [candle] });
  }
  return sessions;
}

function high(bars: Candle[]): number {
  return bars.reduce((max, bar) => Math.max(max, bar.high), Number.NEGATIVE_INFINITY);
}

function low(bars: Candle[]): number {
  return bars.reduce((min, bar) => Math.min(min, bar.low), Number.POSITIVE_INFINITY);
}

/**
 * Wilder's ATR over `period` bars.
 *
 * True range, not the bar's own range: a gap open leaves a small candle whose
 * range understates how far price actually moved, and sizing a stop off that
 * is how a "1×ATR" stop gets hit on the open.
 *
 * `undefined` below `period + 1` bars rather than an average of what is there.
 */
export function atr(candles: Candle[], period = 14): number | undefined {
  if (candles.length < period + 1) return undefined;

  const trueRanges: number[] = [];
  for (let i = 1; i < candles.length; i += 1) {
    const bar = candles[i];
    const previous = candles[i - 1];
    if (!bar || !previous) continue;
    trueRanges.push(
      Math.max(
        bar.high - bar.low,
        Math.abs(bar.high - previous.close),
        Math.abs(bar.low - previous.close)
      )
    );
  }
  if (trueRanges.length < period) return undefined;

  // Seed with a simple mean, then smooth — Wilder's own definition.
  let value = trueRanges.slice(0, period).reduce((sum, tr) => sum + tr, 0) / period;
  for (let i = period; i < trueRanges.length; i += 1) {
    const tr = trueRanges[i];
    if (tr == null) continue;
    value = (value * (period - 1) + tr) / period;
  }
  return value;
}

/**
 * Swing highs and lows: a bar whose extreme beats `lookback` bars either side.
 *
 * A fractal, not a trend-structure claim. The `lookback` is exposed because
 * three bars either side on a 1-minute chart and on a daily chart describe
 * completely different things.
 */
export function swings(
  candles: Candle[],
  lookback = 3
): { highs: { time: number; price: number }[]; lows: { time: number; price: number }[] } {
  const highs: { time: number; price: number }[] = [];
  const lows: { time: number; price: number }[] = [];

  for (let i = lookback; i < candles.length - lookback; i += 1) {
    const bar = candles[i];
    if (!bar) continue;
    let isHigh = true;
    let isLow = true;
    for (let j = i - lookback; j <= i + lookback; j += 1) {
      if (j === i) continue;
      const other = candles[j];
      if (!other) continue;
      if (other.high >= bar.high) isHigh = false;
      if (other.low <= bar.low) isLow = false;
    }
    if (isHigh) highs.push({ time: bar.time, price: bar.high });
    if (isLow) lows.push({ time: bar.time, price: bar.low });
  }
  return { highs, lows };
}

export type Structure = 'uptrend' | 'downtrend' | 'range' | 'unclear';

export interface StructureRead {
  state: Structure;
  /** The rule that produced it, stated so the reader can disagree with it. */
  rule: string;
}

/**
 * Market structure from the last two confirmed swings on each side.
 *
 * Higher highs *and* higher lows is an uptrend; lower highs and lower lows a
 * downtrend; anything else is a range or not yet readable. Two swings is the
 * minimum that can express the idea and the maximum that stays legible — this
 * is the textbook rule, named as such, not a proprietary read.
 */
export function structureOf(candles: Candle[], lookback = 3): StructureRead {
  const { highs, lows } = swings(candles, lookback);
  if (highs.length < 2 || lows.length < 2) {
    return {
      state: 'unclear',
      rule: 'Fewer than two confirmed swings on one side — not enough structure to read.'
    };
  }

  // Indexed rather than destructured off a `slice`: the guard above proves
  // there are at least two of each, but the compiler reads `slice` as
  // possibly-shorter and a tuple cast would be a lie it cannot check.
  const h1 = highs[highs.length - 2];
  const h2 = highs[highs.length - 1];
  const l1 = lows[lows.length - 2];
  const l2 = lows[lows.length - 1];
  if (!h1 || !h2 || !l1 || !l2) {
    return { state: 'unclear', rule: 'Swings could not be paired.' };
  }
  const higherHighs = h2.price > h1.price;
  const higherLows = l2.price > l1.price;

  if (higherHighs && higherLows) {
    return { state: 'uptrend', rule: 'Last two swing highs and swing lows are both rising.' };
  }
  if (!higherHighs && !higherLows) {
    return { state: 'downtrend', rule: 'Last two swing highs and swing lows are both falling.' };
  }
  return {
    state: 'range',
    rule: 'Swing highs and lows are moving in opposite directions — no directional structure.'
  };
}

/** Classic floor pivots from one session's high, low and close. */
export function pivots(session: { high: number; low: number; close: number }) {
  const pivot = (session.high + session.low + session.close) / 3;
  const range = session.high - session.low;
  return {
    pivot,
    r1: 2 * pivot - session.low,
    r2: pivot + range,
    r3: session.high + 2 * (pivot - session.low),
    s1: 2 * pivot - session.high,
    s2: pivot - range,
    s3: session.low - 2 * (session.high - pivot)
  };
}

export interface GapRead {
  kind: 'gap_up' | 'gap_down' | 'none';
  points: number;
  percent: number;
  /** The unfilled band, when the gap is still open. */
  from?: number | undefined;
  to?: number | undefined;
  filled: boolean;
}

/**
 * This session's gap against the previous close, and whether it has filled.
 *
 * "Filled" means price has traded back through the previous close at some
 * point today — not that the gap is closed on the candle, which a reader could
 * check themselves.
 */
export function gapOf(
  previousClose: number,
  today: { open: number; high: number; low: number }
): GapRead {
  if (!(previousClose > 0)) return { kind: 'none', points: 0, percent: 0, filled: false };
  const points = today.open - previousClose;
  const percent = (points / previousClose) * 100;

  if (points > 0) {
    return {
      kind: 'gap_up',
      points,
      percent,
      from: previousClose,
      to: today.open,
      filled: today.low <= previousClose
    };
  }
  if (points < 0) {
    return {
      kind: 'gap_down',
      points,
      percent,
      from: today.open,
      to: previousClose,
      filled: today.high >= previousClose
    };
  }
  return { kind: 'none', points: 0, percent: 0, filled: true };
}

/**
 * Relative volume: today's traded volume so far against the mean of the same
 * number of bars on prior sessions.
 *
 * Compared bar-for-bar rather than session-to-session, because at 10:00 a
 * session is 12% complete and dividing by a full day's mean would report 0.12
 * on a perfectly normal morning.
 */
export function relativeVolume(
  sessions: { day: string; bars: Candle[] }[],
  volumes: Map<number, number>
): number | undefined {
  if (sessions.length < 2) return undefined;
  const today = sessions[sessions.length - 1];
  if (!today) return undefined;

  const barsSoFar = today.bars.length;
  const sum = (bars: Candle[]) =>
    bars.slice(0, barsSoFar).reduce((total, bar) => total + (volumes.get(bar.time) ?? 0), 0);

  const todayVolume = sum(today.bars);
  const priorSessions = sessions.slice(0, -1);
  if (priorSessions.length === 0) return undefined;

  const priorMean =
    priorSessions.reduce((total, session) => total + sum(session.bars), 0) / priorSessions.length;
  if (!(priorMean > 0)) return undefined;
  return todayVolume / priorMean;
}

export interface LevelSet {
  levels: Level[];
  atr?: number | undefined;
  structure: StructureRead;
  gap?: GapRead | undefined;
  relativeVolume?: number | undefined;
  /** The session the intraday levels were measured on. */
  sessionDay?: string | undefined;
  /** True when the series does not reach back far enough for a prior session. */
  previousSessionMissing: boolean;
}

/**
 * Every level the panel and the chart draw, from one candle series.
 *
 * Takes the series the chart is *actually showing* so the two cannot disagree.
 * The cost is that a 1-minute window of five days has no 60-day swing in it —
 * which is correct, and the panel says the timeframe beside every row.
 */
export function levelsFrom(
  candles: Candle[],
  volumeBars: VolumeBar[] | undefined,
  timeframe: string,
  options: { vwap?: number; openingRangeMinutes?: number; swingLookback?: number } = {}
): LevelSet {
  const structure = structureOf(candles, options.swingLookback ?? 3);
  if (candles.length === 0) {
    return { levels: [], structure, previousSessionMissing: true };
  }

  const sessions = bySession(candles);
  const today = sessions[sessions.length - 1];
  const previous = sessions.length >= 2 ? sessions[sessions.length - 2] : undefined;
  const last = candles[candles.length - 1];
  const levels: Level[] = [];

  if (previous) {
    const previousClose = previous.bars[previous.bars.length - 1]?.close;
    levels.push(
      {
        kind: 'previous_high',
        label: 'Previous day high',
        price: high(previous.bars),
        timeframe,
        method: `Highest high of the ${previous.day} session, from ${timeframe} bars.`
      },
      {
        kind: 'previous_low',
        label: 'Previous day low',
        price: low(previous.bars),
        timeframe,
        method: `Lowest low of the ${previous.day} session, from ${timeframe} bars.`
      }
    );
    if (previousClose != null) {
      levels.push({
        kind: 'previous_close',
        label: 'Previous close',
        price: previousClose,
        timeframe,
        method: `Close of the last ${timeframe} bar of ${previous.day}.`
      });
    }
  }

  if (today) {
    levels.push(
      {
        kind: 'day_high',
        label: "Day's high",
        price: high(today.bars),
        timeframe,
        method: `Highest high so far on ${today.day}.`,
        asOf: last?.time
      },
      {
        kind: 'day_low',
        label: "Day's low",
        price: low(today.bars),
        timeframe,
        method: `Lowest low so far on ${today.day}.`,
        asOf: last?.time
      }
    );

    const window = options.openingRangeMinutes ?? OPENING_RANGE_MINUTES;
    const openingBars = today.bars.filter(
      (bar) => istMinutes(bar.time) < SESSION_OPEN_MINUTES + window
    );
    // Only meaningful on intraday bars: on a daily series the "opening range"
    // would be the whole session, which is the day's range under another name.
    if (openingBars.length > 0 && openingBars.length < today.bars.length) {
      levels.push(
        {
          kind: 'open_range_high',
          label: `Opening range high (${window}m)`,
          price: high(openingBars),
          timeframe,
          method: `Highest high in the first ${window} minutes after 09:15 IST.`
        },
        {
          kind: 'open_range_low',
          label: `Opening range low (${window}m)`,
          price: low(openingBars),
          timeframe,
          method: `Lowest low in the first ${window} minutes after 09:15 IST.`
        }
      );
    }
  }

  if (options.vwap != null && Number.isFinite(options.vwap)) {
    levels.push({
      kind: 'vwap',
      label: 'VWAP',
      price: options.vwap,
      timeframe,
      method: 'Volume-weighted average price over the bars on screen.',
      asOf: last?.time
    });
  }

  const { highs, lows } = swings(candles, options.swingLookback ?? 3);
  const lastSwingHigh = highs[highs.length - 1];
  const lastSwingLow = lows[lows.length - 1];
  if (lastSwingHigh) {
    levels.push({
      kind: 'swing_high',
      label: 'Last swing high',
      price: lastSwingHigh.price,
      timeframe,
      method: `A ${timeframe} bar whose high beat the ${options.swingLookback ?? 3} bars either side.`,
      asOf: lastSwingHigh.time
    });
  }
  if (lastSwingLow) {
    levels.push({
      kind: 'swing_low',
      label: 'Last swing low',
      price: lastSwingLow.price,
      timeframe,
      method: `A ${timeframe} bar whose low beat the ${options.swingLookback ?? 3} bars either side.`,
      asOf: lastSwingLow.time
    });
  }

  const range = atr(candles);
  if (range != null && last) {
    levels.push(
      {
        kind: 'atr_band',
        label: 'Close + 1 ATR',
        price: last.close + range,
        timeframe,
        method: `Last close plus a 14-period Wilder ATR of ${range.toFixed(2)}.`
      },
      {
        kind: 'atr_band',
        label: 'Close − 1 ATR',
        price: last.close - range,
        timeframe,
        method: `Last close minus a 14-period Wilder ATR of ${range.toFixed(2)}.`
      }
    );
  }

  const previousClose = previous?.bars[previous.bars.length - 1]?.close;
  const firstToday = today?.bars[0];
  const gap =
    previousClose != null && firstToday != null && today
      ? gapOf(previousClose, {
          open: firstToday.open,
          high: high(today.bars),
          low: low(today.bars)
        })
      : undefined;

  const volumeIndex = new Map((volumeBars ?? []).map((bar) => [bar.time, bar.value]));

  const result: LevelSet = {
    levels,
    structure,
    previousSessionMissing: previous == null
  };
  if (range != null) result.atr = range;
  if (gap) result.gap = gap;
  if (today) result.sessionDay = today.day;
  const relVol = volumeBars ? relativeVolume(sessions, volumeIndex) : undefined;
  if (relVol != null) result.relativeVolume = relVol;
  return result;
}
