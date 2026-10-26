/**
 * Technical indicators for the price chart — pure functions over the loaded
 * candles.
 *
 * Each returns `LinePoint[]` (epoch-seconds `time` + `value`), the shape
 * `LwChart` draws a line series from, so an indicator is added to the chart by
 * dropping its output into the `overlays` prop. Points before an indicator has
 * enough history are omitted rather than zeroed, so the line simply starts where
 * the data supports it — the same rule the backend indicators follow.
 */

import type { Candle, OverlaySpec, VolumeBar } from '$shared/charts/tv/LwChart';
import type { Interval } from './analyse-data';

export interface LinePoint {
  time: number;
  value: number;
}

export type IndicatorId = 'sma20' | 'sma50' | 'ema20' | 'boll' | 'vwap' | 'rsi' | 'gann';

/** The pane RSI draws into — below price (0) and the volume pane (1). */
export const RSI_PANE = 2;

const COLORS = {
  sma20: '#3b82f6',
  sma50: '#f97316',
  ema20: '#a855f7',
  bollUpper: '#22c55e',
  bollLower: '#22c55e',
  bollMid: '#6b7280',
  vwap: '#eab308',
  rsi: '#a855f7',
  // Gann: three flat colours, one per side, and blue for the anchor between
  // them. Every rung is drawn identically — the ladder is read by *where* a
  // line sits, not by how loud it is, and weighting the triggers heavier than
  // the targets only adds a second thing to decode.
  gannBase: '#2962ff',
  gannBuy: '#22c55e',
  gannSell: '#ef4444'
} as const;

/**
 * What an indicator *is*, which is how the menu groups them.
 *
 * A flat alphabet of six names needs no grouping; a catalogue that grows past
 * that does, and the reader looking for a band is not helped by scanning past
 * every oscillator to find it.
 */
export type IndicatorCategory = 'trend' | 'volatility' | 'volume' | 'momentum' | 'levels';

/** Category order in the menu — broadest and most-reached-for first. */
export const INDICATOR_CATEGORIES: { id: IndicatorCategory; label: string }[] = [
  { id: 'trend', label: 'Trend' },
  { id: 'volatility', label: 'Volatility' },
  { id: 'volume', label: 'Volume' },
  { id: 'momentum', label: 'Momentum' },
  { id: 'levels', label: 'Levels' }
];

export interface IndicatorEntry {
  id: IndicatorId;
  label: string;
  pane: 'price' | 'rsi';
  category: IndicatorCategory;
  /**
   * The colour this indicator draws in, so the menu can show the same swatch
   * the reader is looking at on the chart. Bollinger names its band colour —
   * the mid-line is deliberately grey and would identify nothing.
   */
  color: string;
}

/** Every indicator the menu offers, in display order. */
export const INDICATORS: IndicatorEntry[] = [
  { id: 'sma20', label: 'SMA 20', pane: 'price', category: 'trend', color: COLORS.sma20 },
  { id: 'sma50', label: 'SMA 50', pane: 'price', category: 'trend', color: COLORS.sma50 },
  { id: 'ema20', label: 'EMA 20', pane: 'price', category: 'trend', color: COLORS.ema20 },
  {
    id: 'boll',
    label: 'Bollinger 20',
    pane: 'price',
    category: 'volatility',
    color: COLORS.bollUpper
  },
  { id: 'vwap', label: 'VWAP', pane: 'price', category: 'volume', color: COLORS.vwap },
  { id: 'rsi', label: 'RSI 14', pane: 'rsi', category: 'momentum', color: COLORS.rsi },
  // Names the buy side's colour for the same reason Bollinger names its band:
  // the ladder is green above and red below, and the grey anchor between them
  // would identify nothing.
  { id: 'gann', label: 'Gann SQ9 Levels', pane: 'price', category: 'levels', color: COLORS.gannBuy }
];

/** Simple moving average of the close. */
export function sma(candles: Candle[], period: number): LinePoint[] {
  if (period <= 0) return [];
  const out: LinePoint[] = [];
  let sum = 0;
  for (let i = 0; i < candles.length; i++) {
    sum += candles[i]!.close;
    if (i >= period) sum -= candles[i - period]!.close;
    if (i >= period - 1) out.push({ time: candles[i]!.time, value: sum / period });
  }
  return out;
}

/** Exponential moving average, seeded with the first SMA of `period`. */
export function ema(candles: Candle[], period: number): LinePoint[] {
  if (period <= 0 || candles.length < period) return [];
  const k = 2 / (period + 1);
  const out: LinePoint[] = [];
  let seed = 0;
  for (let i = 0; i < period; i++) seed += candles[i]!.close;
  let prev = seed / period;
  out.push({ time: candles[period - 1]!.time, value: prev });
  for (let i = period; i < candles.length; i++) {
    prev = candles[i]!.close * k + prev * (1 - k);
    out.push({ time: candles[i]!.time, value: prev });
  }
  return out;
}

export interface Bollinger {
  upper: LinePoint[];
  mid: LinePoint[];
  lower: LinePoint[];
}

/** Bollinger bands: an SMA mid-line ± `mult` standard deviations. */
export function bollinger(candles: Candle[], period = 20, mult = 2): Bollinger {
  const upper: LinePoint[] = [];
  const mid: LinePoint[] = [];
  const lower: LinePoint[] = [];
  for (let i = period - 1; i < candles.length; i++) {
    let sum = 0;
    for (let j = i - period + 1; j <= i; j++) sum += candles[j]!.close;
    const mean = sum / period;
    let variance = 0;
    for (let j = i - period + 1; j <= i; j++) variance += (candles[j]!.close - mean) ** 2;
    const sd = Math.sqrt(variance / period);
    const time = candles[i]!.time;
    mid.push({ time, value: mean });
    upper.push({ time, value: mean + mult * sd });
    lower.push({ time, value: mean - mult * sd });
  }
  return { upper, mid, lower };
}

/**
 * Session VWAP: cumulative typical-price × volume ÷ cumulative volume, reset at
 * each new trading day. `null` when there is no volume — an index has none.
 */
export function vwap(candles: Candle[], volume: VolumeBar[] | undefined): LinePoint[] {
  if (!volume || volume.length === 0) return [];
  const volAt = new Map(volume.map((bar) => [bar.time, bar.value]));
  const out: LinePoint[] = [];
  let cumPV = 0;
  let cumV = 0;
  let day = '';
  for (const candle of candles) {
    const key = dayKey(candle.time);
    if (key !== day) {
      day = key;
      cumPV = 0;
      cumV = 0;
    }
    const v = volAt.get(candle.time) ?? 0;
    const typical = (candle.high + candle.low + candle.close) / 3;
    cumPV += typical * v;
    cumV += v;
    if (cumV > 0) out.push({ time: candle.time, value: cumPV / cumV });
  }
  return out;
}

/** Wilder's RSI of the close, 0–100. */
export function rsi(candles: Candle[], period = 14): LinePoint[] {
  if (candles.length <= period) return [];
  const out: LinePoint[] = [];
  let gain = 0;
  let loss = 0;
  for (let i = 1; i <= period; i++) {
    const diff = candles[i]!.close - candles[i - 1]!.close;
    if (diff >= 0) gain += diff;
    else loss -= diff;
  }
  let avgGain = gain / period;
  let avgLoss = loss / period;
  out.push({ time: candles[period]!.time, value: rsiValue(avgGain, avgLoss) });
  for (let i = period + 1; i < candles.length; i++) {
    const diff = candles[i]!.close - candles[i - 1]!.close;
    const up = diff >= 0 ? diff : 0;
    const down = diff < 0 ? -diff : 0;
    avgGain = (avgGain * (period - 1) + up) / period;
    avgLoss = (avgLoss * (period - 1) + down) / period;
    out.push({ time: candles[i]!.time, value: rsiValue(avgGain, avgLoss) });
  }
  return out;
}

function rsiValue(avgGain: number, avgLoss: number): number {
  if (avgLoss === 0) return 100;
  const rs = avgGain / avgLoss;
  return 100 - 100 / (1 + rs);
}

/** IST calendar day of an epoch-seconds instant, for the VWAP session reset. */
function dayKey(seconds: number): string {
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Kolkata',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit'
  }).format(seconds * 1000);
}

/* ---------------------------------------------------------------------------
 * Gann Square-of-9 daily levels
 * ------------------------------------------------------------------------ */

/**
 * India keeps no daylight saving, so IST is a fixed +05:30 and a session's
 * calendar day and open can be found by arithmetic instead of formatting every
 * bar through `Intl` — which matters when a 1m chart carries ~5,600 of them and
 * this runs on each repaint. (`dayKey` above still uses `Intl`; it is called on
 * far fewer bars and changing it is not this indicator's business.)
 */
const IST_OFFSET_SECONDS = 5.5 * 3600;
const SECONDS_PER_DAY = 86400;

/** Midnight IST of the day an instant falls in, as epoch seconds. */
function istMidnight(seconds: number): number {
  return (
    Math.floor((seconds + IST_OFFSET_SECONDS) / SECONDS_PER_DAY) * SECONDS_PER_DAY -
    IST_OFFSET_SECONDS
  );
}

/** Bar size in minutes — what the opening-range guard compares against. */
const INTERVAL_MINUTES: Record<Interval, number> = {
  '1m': 1,
  '5m': 5,
  '15m': 15,
  '1h': 60,
  '1d': 1440
};

/** A point that may have no reading, which `OverlaySpec` draws as a break. */
export interface GappedPoint {
  time: number;
  value: number | null;
}

export interface GannOptions {
  /** Length of the opening range whose close anchors the day. */
  openingRangeMinutes: number;
  /**
   * How much of a 180° rotation one step covers. One whole unit of √P is 180°,
   * so 3.6 is a 50° step — the workbook's default. 1.8 → 100°, 7.2 → 25°.
   */
  divisor: number;
  /** Published levels round to this: 1 for an index, 0.05 NSE cash, 0.01 FX. */
  roundTo: number;
  /**
   * Session open in IST. Omit to anchor on whatever the session's first bar is,
   * which is right for a feed that starts exactly at the open and wrong for one
   * whose first print is late.
   */
  sessionStart?: { hour: number; minute: number } | undefined;
  /**
   * Added to the stop distance. The workbook's 0.0 puts the stop *on* the entry
   * trigger, which defines a trade with no risk — deliberate there, and worth
   * labelling in the UI rather than shipping silently as a default.
   */
  slBuffer: number;
  /**
   * True reproduces the spreadsheet: each target is a step past the *already
   * rounded* level before it, so rounding error compounds up the ladder. False
   * measures every target from the raw anchor, which is cleaner and can differ
   * by a point at target 2.
   */
  legacyTargetSpacing: boolean;
}

export const GANN_DEFAULTS: GannOptions = {
  openingRangeMinutes: 15,
  divisor: 3.6,
  roundTo: 1,
  sessionStart: undefined,
  slBuffer: 0,
  legacyTargetSpacing: true
};

/** The step size a divisor buys, in degrees — how the setting is labelled. */
export function gannDegrees(divisor: number): number {
  return divisor > 0 ? 180 / divisor : Number.NaN;
}

/**
 * Below roughly this price the ±1 unit of √P is a large fraction of the price
 * itself and the ladder spreads absurdly wide. Not an error — a warning.
 */
export const GANN_LOW_PRICE_FLOOR = 500;

/**
 * Round half away from zero, to a multiple of `step` — Excel's `ROUND`.
 *
 * `Math.round` is half-*up* (−0.5 → −0, not −1) and Python's built-in `round`
 * is banker's; both disagree with the workbook on roughly one value in a
 * thousand, which is exactly often enough to be dismissed as a data glitch.
 */
export function excelRound(value: number, step = 1): number {
  if (!Number.isFinite(value)) return Number.NaN;
  if (step <= 0) return value;
  const units = value / step;
  return Math.floor(Math.abs(units) + 0.5) * (units >= 0 ? 1 : -1) * step;
}

/** One session's complete ladder. */
export interface GannLevels {
  base: number;
  root: number;
  upperBoundary: number;
  lowerBoundary: number;
  upStep: number;
  downStep: number;
  buyAbove: number;
  buyTarget1: number;
  buyTarget2: number;
  buySl: number;
  sellBelow: number;
  sellTarget1: number;
  sellTarget2: number;
  sellSl: number;
}

/**
 * Build the ladder from an anchor price. `null` when the anchor cannot support
 * one — the caller blanks the indicator rather than drawing a guess.
 */
export function gannLadder(base: number, options: Partial<GannOptions> = {}): GannLevels | null {
  const { divisor, roundTo, slBuffer, legacyTargetSpacing } = { ...GANN_DEFAULTS, ...options };
  if (!Number.isFinite(base) || base <= 0) return null;
  // A setting rather than data — but it arrives from the UI and must not reach
  // the render loop as a throw, so it blanks the indicator like a bad price.
  if (!Number.isFinite(divisor) || divisor <= 0) return null;

  const root = Math.sqrt(base);
  const upperBoundary = (root + 1) ** 2;
  const lowerBoundary = (root - 1) ** 2;

  // These reduce exactly to 2·root + 1 and 2·root − 1, which is why the upside
  // distance always exceeds the downside by precisely 2 — and so why the two
  // steps always differ by 2/divisor, whatever the price.
  const upStep = (upperBoundary - base) / divisor;
  const downStep = (base - lowerBoundary) / divisor;

  const r = (value: number): number => excelRound(value, roundTo);

  const buyAbove = r(base + upStep);
  const sellBelow = r(base - downStep);

  const buyTarget1 = legacyTargetSpacing ? r(buyAbove + upStep) : r(base + 2 * upStep);
  const buyTarget2 = legacyTargetSpacing ? r(buyTarget1 + upStep) : r(base + 3 * upStep);
  const sellTarget1 = legacyTargetSpacing ? r(sellBelow - downStep) : r(base - 2 * downStep);
  const sellTarget2 = legacyTargetSpacing ? r(sellTarget1 - downStep) : r(base - 3 * downStep);

  return {
    base,
    root,
    upperBoundary,
    lowerBoundary,
    upStep,
    downStep,
    buyAbove,
    buyTarget1,
    buyTarget2,
    buySl: r(buyAbove - slBuffer),
    sellBelow,
    sellTarget1,
    sellTarget2,
    sellSl: r(sellBelow + slBuffer)
  };
}

/**
 * The seven lines drawn. `buySl`/`sellSl` are computed but not drawn: at the
 * default zero buffer they sit exactly on the triggers, and a second line on
 * top of the first is noise rather than information.
 */
export type GannLineKey =
  'base' | 'buyAbove' | 'buyTarget1' | 'buyTarget2' | 'sellBelow' | 'sellTarget1' | 'sellTarget2';

export const GANN_LINE_KEYS: GannLineKey[] = [
  'base',
  'buyAbove',
  'buyTarget1',
  'buyTarget2',
  'sellBelow',
  'sellTarget1',
  'sellTarget2'
];

/** What one session resolved to — for the tests and the legend. */
export interface GannSession {
  /** Midnight IST of the session, epoch seconds. */
  day: number;
  /** The bar whose close became the anchor. */
  anchorTime: number;
  /** First bar the levels are published on — the opening range has closed. */
  publishTime: number;
  levels: GannLevels;
}

export interface GannResult {
  lines: Record<GannLineKey, GappedPoint[]>;
  sessions: GannSession[];
  /** Set when the indicator must not draw at all, with the reason to show. */
  error: string | null;
  /** Set when it draws but the reader should know something. */
  warning: string | null;
}

function emptyGannLines(): Record<GannLineKey, GappedPoint[]> {
  return {
    base: [],
    buyAbove: [],
    buyTarget1: [],
    buyTarget2: [],
    sellBelow: [],
    sellTarget1: [],
    sellTarget2: []
  };
}

/**
 * Gann Square-of-9 levels, one ladder per session, held flat across the day.
 *
 * The anchor is found **by time**, never by counting bars: the window is
 * `session start + openingRangeMinutes`, and the anchor is the close of the
 * last bar that *opens* strictly before that edge. Counting "bar N = 15 ÷
 * timeframe" picks the wrong candle the moment a print is missing, the feed
 * gaps, or the exchange runs a half-day.
 *
 * Nothing is published until that window has closed. Every bar inside it — and
 * every bar of a session whose anchor never arrived — carries an explicit
 * `null` rather than being omitted, because an omitted bar in a stepped series
 * holds the previous session's level straight across the hole, which is exactly
 * the forward-fill a backtest must never see.
 */
export function gannDailyLevels(
  candles: Candle[],
  interval: Interval | undefined,
  options: Partial<GannOptions> = {}
): GannResult {
  const opts: GannOptions = { ...GANN_DEFAULTS, ...options };
  const lines = emptyGannLines();
  const sessions: GannSession[] = [];

  if (candles.length === 0) return { lines, sessions, error: null, warning: null };

  // Fail loudly rather than anchor to the wrong candle: on a bar coarser than
  // the opening range no bar closes at the window's edge, and quietly taking
  // the day's first bar instead would be a different indicator.
  if (interval === undefined) {
    return { lines, sessions, error: 'Gann SQ9: chart interval unknown.', warning: null };
  }
  const barMinutes = INTERVAL_MINUTES[interval];
  if (barMinutes > opts.openingRangeMinutes) {
    return {
      lines,
      sessions,
      error:
        `Gann SQ9 needs a bar of ${opts.openingRangeMinutes}m or finer to anchor on the ` +
        `${opts.openingRangeMinutes}-minute opening range — this chart is on ${interval}.`,
      warning: null
    };
  }

  let warning: string | null = null;

  for (let i = 0; i < candles.length;) {
    const day = istMidnight(candles[i]!.time);
    let end = i;
    while (end < candles.length && istMidnight(candles[end]!.time) === day) end += 1;

    const start =
      opts.sessionStart === undefined
        ? candles[i]!.time
        : day + opts.sessionStart.hour * 3600 + opts.sessionStart.minute * 60;
    const orEnd = start + opts.openingRangeMinutes * 60;

    // The last bar opening inside [start, orEnd) carries the anchor close.
    let anchorTime: number | null = null;
    let anchorClose = Number.NaN;
    for (let j = i; j < end; j += 1) {
      const candle = candles[j]!;
      if (candle.time >= start && candle.time < orEnd) {
        anchorTime = candle.time;
        anchorClose = candle.close;
      }
    }

    const levels = anchorTime === null ? null : gannLadder(anchorClose, opts);

    // The first bar at or past the edge is where the anchor becomes known, and
    // so the first bar that may carry a level. The anchor bar itself does not:
    // its own close is not known until it closes, which is this instant.
    let publishTime: number | null = null;
    if (levels !== null) {
      for (let j = i; j < end; j += 1) {
        if (candles[j]!.time >= orEnd) {
          publishTime = candles[j]!.time;
          break;
        }
      }
    }

    if (levels !== null && publishTime !== null) {
      sessions.push({ day, anchorTime: anchorTime!, publishTime, levels });
      if (levels.base < GANN_LOW_PRICE_FLOOR) {
        warning =
          `Gann SQ9: anchor ${levels.base.toFixed(2)} is below ${GANN_LOW_PRICE_FLOOR}. ` +
          'The ±1 square-root unit is scale-dependent, so the levels are very wide here.';
      }
    }

    for (let j = i; j < end; j += 1) {
      const time = candles[j]!.time;
      const live = levels !== null && publishTime !== null && time >= publishTime;
      for (const key of GANN_LINE_KEYS) {
        lines[key].push({ time, value: live ? levels[key] : null });
      }
    }

    i = end;
  }

  return { lines, sessions, error: null, warning };
}

/**
 * Just the diagnostics, for the chart to show beside the price.
 *
 * Delegates rather than re-deriving the rules, so the message the reader sees
 * can never disagree with what was (or was not) drawn. The pass is plain
 * arithmetic over the loaded bars, and the caller memoises it.
 */
export function gannGuard(
  candles: Candle[],
  interval: Interval | undefined,
  options: Partial<GannOptions> = {}
): { error: string | null; warning: string | null } {
  const { error, warning } = gannDailyLevels(candles, interval, options);
  return { error, warning };
}

/**
 * Turn the active indicator ids into the `overlays` the chart draws.
 *
 * Built here rather than in the component so the (pure) arithmetic stays
 * testable without a chart, and so toggling an indicator is a cheap array
 * rebuild rather than a chart teardown.
 */
export function buildOverlays(
  active: ReadonlySet<IndicatorId>,
  candles: Candle[],
  volume: VolumeBar[] | undefined,
  /**
   * Bar size, which only Gann needs — it refuses to anchor on a bar coarser
   * than its opening range. Optional so every existing caller still compiles;
   * omitted, Gann declines to draw rather than guessing the timeframe.
   */
  interval?: Interval,
  gannOptions?: Partial<GannOptions>
): OverlaySpec[] {
  const overlays: OverlaySpec[] = [];
  if (active.has('sma20')) {
    overlays.push({ id: 'sma20', paneIndex: 0, color: COLORS.sma20, data: sma(candles, 20) });
  }
  if (active.has('sma50')) {
    overlays.push({ id: 'sma50', paneIndex: 0, color: COLORS.sma50, data: sma(candles, 50) });
  }
  if (active.has('ema20')) {
    overlays.push({ id: 'ema20', paneIndex: 0, color: COLORS.ema20, data: ema(candles, 20) });
  }
  if (active.has('boll')) {
    const b = bollinger(candles, 20, 2);
    overlays.push({
      id: 'boll-u',
      paneIndex: 0,
      color: COLORS.bollUpper,
      lineWidth: 1,
      data: b.upper
    });
    overlays.push({ id: 'boll-m', paneIndex: 0, color: COLORS.bollMid, lineWidth: 1, data: b.mid });
    overlays.push({
      id: 'boll-l',
      paneIndex: 0,
      color: COLORS.bollLower,
      lineWidth: 1,
      data: b.lower
    });
  }
  if (active.has('vwap')) {
    const v = vwap(candles, volume);
    if (v.length > 0) overlays.push({ id: 'vwap', paneIndex: 0, color: COLORS.vwap, data: v });
  }
  if (active.has('rsi')) {
    // Sits below price, and below the volume pane when there is one. An index
    // has no volume, so its RSI drops to pane 1 rather than leaving a blank gap.
    const pane = volume && volume.length > 0 ? RSI_PANE : 1;
    overlays.push({ id: 'rsi', paneIndex: pane, color: COLORS.rsi, data: rsi(candles, 14) });
  }
  if (active.has('gann')) {
    const gann = gannDailyLevels(candles, interval, gannOptions);
    // A guard that tripped draws nothing at all; the reason is shown beside the
    // price by `gannGuard`, so a silent empty chart never happens.
    if (gann.error === null) {
      // All seven are drawn the same way: a solid hairline at full opacity,
      // stepped, carrying a right-edge price label. Stepping is not styling —
      // a level is fixed for its session and jumps at the next anchor, so
      // interpolating would slope it across the overnight gap and imply a
      // drift that never happened.
      const level = (id: string, key: GannLineKey, color: string): OverlaySpec => ({
        id,
        paneIndex: 0,
        color,
        lineWidth: 1,
        lineStyle: 'solid',
        stepped: true,
        priceLabel: true,
        data: gann.lines[key]
      });

      overlays.push(
        // Blue, between the two sides: the anchor is neither a buy nor a sell,
        // and a third colour says so without needing a second line weight.
        level('gann-base', 'base', COLORS.gannBase),
        level('gann-buy', 'buyAbove', COLORS.gannBuy),
        level('gann-bt1', 'buyTarget1', COLORS.gannBuy),
        level('gann-bt2', 'buyTarget2', COLORS.gannBuy),
        level('gann-sell', 'sellBelow', COLORS.gannSell),
        level('gann-st1', 'sellTarget1', COLORS.gannSell),
        level('gann-st2', 'sellTarget2', COLORS.gannSell)
      );
    }
  }
  return overlays;
}
