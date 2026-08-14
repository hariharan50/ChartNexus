/** View-model helpers for the AI Console — formatting and small derivations. */

import type { Decision, Horizon } from '$contexts/signals/types';

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
