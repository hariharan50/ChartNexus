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

export interface LinePoint {
  time: number;
  value: number;
}

export type IndicatorId = 'sma20' | 'sma50' | 'ema20' | 'boll' | 'vwap' | 'rsi';

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
  rsi: '#a855f7'
} as const;

/**
 * What an indicator *is*, which is how the menu groups them.
 *
 * A flat alphabet of six names needs no grouping; a catalogue that grows past
 * that does, and the reader looking for a band is not helped by scanning past
 * every oscillator to find it.
 */
export type IndicatorCategory = 'trend' | 'volatility' | 'volume' | 'momentum';

/** Category order in the menu — broadest and most-reached-for first. */
export const INDICATOR_CATEGORIES: { id: IndicatorCategory; label: string }[] = [
  { id: 'trend', label: 'Trend' },
  { id: 'volatility', label: 'Volatility' },
  { id: 'volume', label: 'Volume' },
  { id: 'momentum', label: 'Momentum' }
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
  { id: 'rsi', label: 'RSI 14', pane: 'rsi', category: 'momentum', color: COLORS.rsi }
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
  volume: VolumeBar[] | undefined
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
  return overlays;
}
