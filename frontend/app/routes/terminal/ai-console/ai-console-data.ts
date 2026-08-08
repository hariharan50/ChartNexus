/** View-model helpers for the AI Console — formatting and small derivations. */

import type { Decision } from '$contexts/signals/types';

export const INSTRUMENTS = [
  { short: 'NIFTY', symbol: 'NIFTY' },
  { short: 'SENSEX', symbol: 'SENSEX' },
  { short: 'BANKNIFTY', symbol: 'BANKNIFTY' }
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
