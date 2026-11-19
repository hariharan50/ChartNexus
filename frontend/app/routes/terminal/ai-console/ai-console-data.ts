/** View-model helpers for the AI Console — formatting and small derivations. */

import type { Decision, Horizon, Levels, Scaffold } from '$contexts/signals/types';

/** The horizons, in switcher order, with their human labels and time frame. */
export const HORIZONS: ReadonlyArray<{ key: Horizon; label: string; frame: string }> = [
  { key: 'intraday', label: 'Intraday', frame: 'next 15–30 min' },
  { key: 'end_of_day', label: 'End of day', frame: 'into the close' },
  { key: 'swing', label: 'Swing', frame: '1–3 days' }
] as const;

/** A short, readable label for a market regime. */
export function regimeLabel(regime: string): string {
  if (regime === 'trending_up') return 'Trending up';
  if (regime === 'trending_down') return 'Trending down';
  if (regime === 'rangebound') return 'Rangebound';
  return regime;
}

/** Friendly names for the feature drivers surfaced in a call's breakdown. */
const DRIVER_LABELS: Readonly<Record<string, string>> = {
  ret_5: 'Short-term momentum',
  ret_20: 'Trend momentum',
  rsi_norm: 'RSI',
  ema_gap: 'EMA gap',
  vwap_gap: 'VWAP gap',
  adx: 'Trend strength',
  bb_width: 'Bollinger width',
  realized_vol: 'Realized vol',
  range_pos: 'Range position',
  daily_ret_3: '3-day return',
  daily_rsi_norm: 'Daily RSI',
  pcr_level: 'Put/call ratio',
  pcr_velocity: 'PCR velocity',
  buildup_bias: 'OI build-up',
  gex_sign: 'Gamma exposure',
  dist_max_pain: 'Max pain pull',
  dist_call_wall: 'Call wall',
  dist_put_wall: 'Put wall',
  dist_gamma_flip: 'Gamma flip',
  iv_pct: 'IV rank',
  atm_skew: 'ATM skew'
};

export function driverLabel(name: string): string {
  return DRIVER_LABELS[name] ?? name.replace(/_/g, ' ');
}

export const INSTRUMENTS = [
  { short: 'NIFTY', label: 'NIFTY 50', symbol: 'NIFTY' },
  { short: 'SENSEX', label: 'SENSEX', symbol: 'SENSEX' },
  { short: 'BANKNIFTY', label: 'BANK NIFTY', symbol: 'BANKNIFTY' }
] as const;

export const SUGGESTIONS = [
  'Why this call?',
  "Where's my stop?",
  "What's the target?",
  'Which levels matter?'
] as const;

/** Maps a decision to its CSS-module class name (buy/sell/hold). */
export function decisionClass(decision: Decision): 'buy' | 'sell' | 'hold' {
  if (decision === 'BUY') return 'buy';
  if (decision === 'SELL') return 'sell';
  return 'hold';
}

export function fmtPrice(value: number | null): string {
  return value == null ? '—' : Math.round(value).toLocaleString('en-IN');
}

export function fmtRatio(value: number | null): string {
  return value == null ? '—' : value.toFixed(2);
}

/** Fraction of the meter to fill, 0..1, for a score in [-1, 1]. */
export function meterWidth(score: number | null): string {
  if (score == null) return '100%';
  return `${Math.min(100, Math.abs(score) * 50)}%`;
}

/** Signed, two-decimal score for a pill, or a dash when absent. */
export function fmtScore(score: number | null): string {
  if (score == null) return '·';
  const sign = score > 0 ? '+' : '';
  return `${sign}${score.toFixed(2)}`;
}

/** A short lean word for a directional score. */
export function scoreLean(score: number | null): 'pos' | 'neg' | 'none' {
  if (score == null) return 'none';
  if (score > 0.05) return 'pos';
  if (score < -0.05) return 'neg';
  return 'none';
}

/**
 * Where spot sits between support and resistance, 0..100 — or `null` when the
 * bracket can't be drawn. Powers the position bar in the Levels panel.
 */
export function spotPositionPct(
  support: number | null,
  resistance: number | null,
  spot: number
): number | null {
  if (support == null || resistance == null || resistance <= support) return null;
  return Math.min(100, Math.max(0, ((spot - support) / (resistance - support)) * 100));
}

let seq = 0;
export function nextId(): string {
  seq += 1;
  return `m${seq}`;
}

/* -- Context-card derivations --------------------------------------------- */

/** A qualitative word for a 0-100 model confidence. */
export function confidenceBand(value: number): string {
  if (value >= 70) return 'Strong';
  if (value >= 40) return 'Moderate';
  if (value > 0) return 'Weak';
  return 'No edge';
}

/** A directional bias phrase for the regime card, from the headline decision. */
export function biasPhrase(decision: Decision): string {
  if (decision === 'BUY') return 'Bullish bias';
  if (decision === 'SELL') return 'Bearish bias';
  return 'Neutral bias';
}

/** India VIX read: a short environment label + tone. `null` → unknown. */
export function vixEnvironment(vix: number | null): { label: string; note: string } {
  if (vix == null) return { label: 'Unknown', note: 'No volatility read' };
  if (vix < 13) return { label: 'Low Volatility', note: 'Lower volatility environment' };
  if (vix < 20) return { label: 'Moderate Volatility', note: 'Normal volatility environment' };
  return { label: 'High Volatility', note: 'Elevated volatility environment' };
}

/** Put/call ratio sentiment. Puts-heavy (high PCR) reads supportive/bullish. */
export function pcrSentiment(pcr: number | null): { label: string; note: string } {
  if (pcr == null) return { label: 'Unknown', note: 'No option-flow read' };
  if (pcr >= 1.2) return { label: 'Bullish', note: 'Put-heavy positioning' };
  if (pcr >= 1.0) return { label: 'Neutral', note: 'Slightly bullish' };
  if (pcr >= 0.85) return { label: 'Neutral', note: 'Balanced positioning' };
  if (pcr >= 0.7) return { label: 'Cautious', note: 'Slightly bearish' };
  return { label: 'Bearish', note: 'Call-heavy positioning' };
}

/** Absolute VIX day-change implied by its percent move (for the "-1.32" figure). */
export function vixAbsoluteChange(vix: number | null, changePct: number | null): number | null {
  if (vix == null || changePct == null) return null;
  const prev = vix / (1 + changePct / 100);
  return vix - prev;
}

/**
 * NSE cash session is 09:15–15:30 IST, Mon–Fri. Derived client-side from the
 * viewer's clock converted to IST — display only, never a trading gate.
 */
export function marketStatusIST(now: Date = new Date()): { open: boolean; label: string } {
  const ist = new Date(now.getTime() + IST_OFFSET_MS);
  const day = ist.getUTCDay(); // 0 Sun .. 6 Sat, on the IST-shifted clock
  const minutes = ist.getUTCHours() * 60 + ist.getUTCMinutes();
  const weekday = day >= 1 && day <= 5;
  const open = weekday && minutes >= 9 * 60 + 15 && minutes <= 15 * 60 + 30;
  return { open, label: open ? 'OPEN' : 'CLOSED' };
}

/** Current time as "10:35 AM IST". */
export function nowLabelIST(now: Date = new Date()): string {
  const ist = new Date(now.getTime() + IST_OFFSET_MS);
  let h = ist.getUTCHours();
  const m = ist.getUTCMinutes();
  const ampm = h >= 12 ? 'PM' : 'AM';
  h = h % 12 || 12;
  return `${h}:${String(m).padStart(2, '0')} ${ampm} IST`;
}

/** IST is a fixed UTC+5:30; a Date's epoch is UTC, so shift then read getUTC*. */
const IST_OFFSET_MS = 5.5 * 60 * 60 * 1000;

/* -- Market Analysis view-models ------------------------------------------- */

/** One plain-English line on what each driver measures, for the driver bars. */
const DRIVER_HINTS: Readonly<Record<string, string>> = {
  ret_5: 'Price change over the last few bars',
  ret_20: 'Price change over the last twenty bars',
  rsi_norm: 'Momentum: overbought above 70, oversold below 30',
  ema_gap: 'How far price sits from its moving average',
  vwap_gap: 'Price versus the volume-weighted average',
  adx: 'How strongly the market is trending',
  bb_width: 'How wide the Bollinger bands are',
  realized_vol: 'How much price has actually been moving',
  range_pos: 'Where price sits in its recent range',
  daily_ret_3: 'Change over the last three sessions',
  daily_rsi_norm: 'Daily momentum',
  pcr_level: 'Put/call open interest balance',
  pcr_velocity: 'How fast the put/call ratio is changing',
  buildup_bias: 'Whether puts or calls are being written',
  gex_sign: 'Dealer gamma: dampens or amplifies moves',
  dist_max_pain: 'Pull towards the max-pain strike',
  dist_call_wall: 'Distance to the heaviest call strike',
  dist_put_wall: 'Distance to the heaviest put strike',
  dist_gamma_flip: 'Distance to the gamma flip level',
  iv_pct: 'Implied volatility versus its own history',
  atm_skew: 'Put versus call implied volatility at the money'
};

export function driverHint(name: string): string {
  return DRIVER_HINTS[name] ?? '';
}

export interface Consensus {
  /** Every horizon makes the same call. */
  agree: boolean;
  /** The call most horizons make, or `null` on a split. */
  majority: Decision | null;
  votes: Record<Decision, number>;
  averageConfidence: number;
  label: string;
}

/** How the horizons line up: "All 3 horizons: BUY", "2 of 3: BUY" or a split. */
export function horizonConsensus(
  calls: ReadonlyArray<{ decision: Decision; confidence: number }>
): Consensus {
  const votes: Record<Decision, number> = { BUY: 0, SELL: 0, HOLD: 0 };
  for (const call of calls) votes[call.decision] += 1;
  const ranked = (Object.entries(votes) as [Decision, number][]).sort((a, b) => b[1] - a[1]);
  const top = ranked[0];
  const second = ranked[1];
  const majority = top && top[1] > 0 && (!second || top[1] > second[1]) ? top[0] : null;
  const agree = calls.length > 0 && top !== undefined && top[1] === calls.length;
  const averageConfidence = calls.length
    ? Math.round(calls.reduce((sum, call) => sum + call.confidence, 0) / calls.length)
    : 0;
  let label = 'Horizons split';
  if (!calls.length) label = 'No calls';
  else if (agree && majority) label = `All ${calls.length} horizons: ${majority}`;
  else if (majority) label = `${votes[majority]} of ${calls.length}: ${majority}`;
  return { agree, majority, votes, averageConfidence, label };
}

/**
 * The HOLD band in probability terms (0-1). BUY needs p(up) above `high`,
 * SELL below `low`. `null` when the model did not report its band.
 */
export function holdBand(band: number | null | undefined): { low: number; high: number } | null {
  if (band == null || !Number.isFinite(band) || band <= 0 || band >= 0.5) return null;
  return { low: 0.5 - band, high: 0.5 + band };
}

/** What the probability would have to do for the call to change, in words. */
export function bandExplainer(
  probability: number,
  band: { low: number; high: number } | null
): string {
  if (!band) return '';
  const pct = (value: number) => `${Math.round(value * 100)}%`;
  if (probability > band.high) return `Above ${pct(band.high)}, so the model calls BUY.`;
  if (probability < band.low) return `Below ${pct(band.low)}, so the model calls SELL.`;
  return (
    `Inside the HOLD band (${pct(band.low)}–${pct(band.high)}): needs above ` +
    `${pct(band.high)} for BUY or below ${pct(band.low)} for SELL.`
  );
}

export interface LadderRow {
  key: string;
  label: string;
  price: number;
  /** Signed distance from spot in points (positive = above spot). */
  points: number;
  percent: number;
  side: 'above' | 'below' | 'spot';
  nearest: boolean;
}

const LEVEL_LABELS: ReadonlyArray<[Exclude<keyof Levels, 'spot'>, string]> = [
  ['resistance', 'Resistance'],
  ['call_wall', 'Call wall'],
  ['gamma_flip', 'Gamma flip'],
  ['max_pain', 'Max pain'],
  ['put_wall', 'Put wall'],
  ['support', 'Support']
];

/**
 * Every known level plus spot, highest first, with its distance from spot.
 * The level closest to spot is flagged: it is the one price meets next.
 */
export function levelLadder(levels: Levels): LadderRow[] {
  const spot = levels.spot;
  const rows: LadderRow[] = [];
  for (const [key, label] of LEVEL_LABELS) {
    const price = levels[key];
    if (price == null || !Number.isFinite(price)) continue;
    const points = price - spot;
    rows.push({
      key,
      label,
      price,
      points,
      percent: spot ? (points / spot) * 100 : 0,
      side: points >= 0 ? 'above' : 'below',
      nearest: false
    });
  }
  let nearest: LadderRow | null = null;
  for (const row of rows) {
    if (nearest === null || Math.abs(row.points) < Math.abs(nearest.points)) nearest = row;
  }
  if (nearest) nearest.nearest = true;
  rows.push({
    key: 'spot',
    label: 'Spot',
    price: spot,
    points: 0,
    percent: 0,
    side: 'spot',
    nearest: false
  });
  // Highest first. At an equal price levels keep their listed order (the sort
  // is stable) and the spot marker goes below them.
  const isSpot = (row: LadderRow) => (row.side === 'spot' ? 1 : 0);
  return rows.sort((a, b) => b.price - a.price || isSpot(a) - isSpot(b));
}

/** Risk and reward of a scaffold in index points, when all three legs exist. */
export function scaffoldPoints(scaffold: Scaffold): { risk: number; reward: number } | null {
  const { entry, stop, target } = scaffold;
  if (entry == null || stop == null || target == null) return null;
  return { risk: Math.abs(entry - stop), reward: Math.abs(target - entry) };
}

/** "8s ago", "3m ago" — for the freshness line. */
export function fmtAgo(atMs: number, now: number): string {
  if (!atMs) return '—';
  const seconds = Math.max(0, Math.round((now - atMs) / 1000));
  if (seconds < 60) return `${seconds}s ago`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  return `${Math.floor(seconds / 3600)}h ago`;
}

/** "10:42" in IST, for the call-history timeline. */
export function timeIST(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '—';
  const ist = new Date(date.getTime() + IST_OFFSET_MS);
  const hours = String(ist.getUTCHours()).padStart(2, '0');
  const minutes = String(ist.getUTCMinutes()).padStart(2, '0');
  return `${hours}:${minutes}`;
}

/** Whether an ISO timestamp falls on today's IST date. */
export function isTodayIST(iso: string, now: Date = new Date()): boolean {
  const day = (value: Date) => new Date(value.getTime() + IST_OFFSET_MS).toISOString().slice(0, 10);
  const date = new Date(iso);
  return !Number.isNaN(date.getTime()) && day(date) === day(now);
}
