/**
 * Pure helpers for the option-chain terminal.
 *
 * The wire contract (`OptionChain`) carries Decimal-as-string fields and
 * nullable CE/PE legs. This module parses that into the merged, per-strike
 * shape the mirror-imaged table renders, and provides the Indian-unit
 * formatting and windowing maths. Everything here is deterministic and
 * side-effect free so it is safe inside a Svelte `$derived` and easy to test.
 */

import type { OptionChain, OptionQuote } from '$contexts/broker-connections/types';
import type { BuildUp } from '$contexts/market-data/view-models';

export type Side = 'ce' | 'pe';

/** A single option leg, numbers parsed and build-up classified. */
export interface Leg {
  oi?: number | undefined;
  oiChange?: number | undefined;
  ltp?: number | undefined;
  /** Implied volatility in percent, e.g. 16.1. */
  iv?: number | undefined;
  volume?: number | undefined;
  buildup?: BuildUp | undefined;
}

/** Both legs of one strike, merged for the two-sided table. */
export interface ChainStrike {
  strike: number;
  ce?: Leg | undefined;
  pe?: Leg | undefined;
}

/** How many strikes to show on each side of the ATM strike. */
export type StrikeCount = 5 | 10 | 15 | 20 | 'All';

export const STRIKE_COUNTS: StrikeCount[] = [5, 10, 15, 20, 'All'];

/** Parse a Decimal-as-string field; `undefined` when absent or unparseable. */
export function num(value: string | null | undefined): number | undefined {
  if (value == null) return undefined;
  const n = Number.parseFloat(value);
  return Number.isNaN(n) ? undefined : n;
}

/**
 * Classify OI build-up from the change in open interest and whether the
 * option's own price is rising. Without a per-strike LTP delta from the broker,
 * price direction is inferred from the underlying: a call gains as the index
 * rises, a put as it falls. Mirrors the dashboard's `derive.ts`.
 */
export function classifyBuildUp(oiChange: number, priceRising: boolean): BuildUp {
  const oiRising = oiChange > 0;
  if (priceRising && oiRising) return 'Long Build-up';
  if (!priceRising && oiRising) return 'Short Build-up';
  if (priceRising && !oiRising) return 'Short Covering';
  return 'Long Unwinding';
}

function toLeg(q: OptionQuote | null, priceRising: boolean): Leg | undefined {
  if (!q) return undefined;
  return {
    oi: q.oi,
    oiChange: q.oi_change,
    ltp: num(q.ltp),
    iv: num(q.iv),
    volume: q.volume,
    buildup: classifyBuildUp(q.oi_change, priceRising)
  };
}

/** Flatten a canonical chain into merged, strike-ascending rows. */
export function toStrikes(chain: OptionChain): ChainStrike[] {
  const rising = (num(chain.change_percent) ?? 0) >= 0;
  return chain.strikes
    .map((s) => ({
      strike: num(s.strike) ?? Number.NaN,
      ce: toLeg(s.ce, rising),
      pe: toLeg(s.pe, !rising)
    }))
    .filter((s) => Number.isFinite(s.strike))
    .sort((a, b) => a.strike - b.strike);
}

/**
 * Index of the strike nearest `spot`. Falls back to `fallbackAtm`, then to the
 * middle of the ladder. Returns -1 for an empty ladder.
 */
export function atmIndex(strikes: ChainStrike[], spot?: number, fallbackAtm?: number): number {
  if (strikes.length === 0) return -1;
  const target = spot != null && Number.isFinite(spot) ? spot : fallbackAtm;
  if (target == null || !Number.isFinite(target)) return Math.floor(strikes.length / 2);
  let best = 0;
  let bestDist = Number.POSITIVE_INFINITY;
  strikes.forEach((s, i) => {
    const d = Math.abs(s.strike - target);
    if (d < bestDist) {
      bestDist = d;
      best = i;
    }
  });
  return best;
}

/** Slice `count` strikes on each side of the ATM index; `'All'` returns all. */
export function windowAround(
  strikes: ChainStrike[],
  atmIdx: number,
  count: StrikeCount
): ChainStrike[] {
  if (count === 'All' || atmIdx < 0) return strikes;
  const lo = Math.max(0, atmIdx - count);
  const hi = Math.min(strikes.length, atmIdx + count + 1);
  return strikes.slice(lo, hi);
}

/** Max OI on one side across the visible strikes — the OI-bar denominator. */
export function maxOi(strikes: ChainStrike[], side: Side): number {
  let max = 0;
  for (const s of strikes) {
    const oi = s[side]?.oi;
    if (oi != null && oi > max) max = oi;
  }
  return max;
}

/** Rank strikes by volume on one side (1 = highest). */
export function volumeRanks(strikes: ChainStrike[], side: Side): Map<number, number> {
  const ranked = strikes
    .filter((s) => (s[side]?.volume ?? 0) > 0)
    .sort((a, b) => (b[side]!.volume ?? 0) - (a[side]!.volume ?? 0));
  const ranks = new Map<number, number>();
  ranked.forEach((s, i) => ranks.set(s.strike, i + 1));
  return ranks;
}

/** The #1 volume on one side — the tooltip's "% of highest" denominator. */
export function topVolume(strikes: ChainStrike[], side: Side): number {
  let max = 0;
  for (const s of strikes) {
    const v = s[side]?.volume;
    if (v != null && v > max) max = v;
  }
  return max;
}

/**
 * OI change as a percent of the prior OI. `undefined` (render "—") when any
 * input is missing, the change is zero, or the prior value was zero.
 */
export function oiChangePct(leg?: Leg): number | undefined {
  if (!leg || leg.oi == null || leg.oiChange == null || leg.oiChange === 0) return undefined;
  const prev = leg.oi - leg.oiChange;
  if (prev === 0) return undefined;
  return (leg.oiChange / Math.abs(prev)) * 100;
}

/** Volume/OI in Indian units: `Cr` ≥1e7, `L` ≥1e5, `K` ≥1e3, else raw. */
export function compactIndian(value?: number): string {
  if (value == null || Number.isNaN(value)) return '—';
  const abs = Math.abs(value);
  if (abs >= 1e7) return `${(value / 1e7).toFixed(2)} Cr`;
  if (abs >= 1e5) return `${(value / 1e5).toFixed(2)} L`;
  if (abs >= 1e3) return `${(value / 1e3).toFixed(1)} K`;
  return `${Math.round(value)}`;
}

/** A signed percentage with a `+` on gains; `undefined` → "—". */
export function signedPct(value: number | undefined, digits = 0): string {
  if (value == null || Number.isNaN(value)) return '—';
  const sign = value > 0 ? '+' : value < 0 ? '−' : '';
  return `${sign}${Math.abs(value).toFixed(digits)}%`;
}

/** An Nth-place ordinal: 1 → "1ˢᵗ", 2 → "2ⁿᵈ", 3 → "3ʳᵈ", 4 → "4ᵗʰ". */
export function ordinal(n: number): string {
  const s = ['ᵗʰ', 'ˢᵗ', 'ⁿᵈ', 'ʳᵈ'];
  const v = n % 100;
  return `${n}${s[(v - 20) % 10] ?? s[v] ?? s[0]}`;
}

const IST = 'Asia/Kolkata';

/**
 * Days from now until an expiry date string. `null` when unparseable. Uses the
 * IST calendar day so "Today" is correct for an Indian trading session.
 */
export function daysAway(expiry: string): number | null {
  const target = parseExpiry(expiry);
  if (!target) return null;
  const today = istMidnight(new Date());
  const diff = Math.round((target.getTime() - today.getTime()) / 86_400_000);
  return diff;
}

/** A short expiry label like `06 Aug`; falls back to the raw string. */
export function expiryLabel(expiry: string): string {
  const d = parseExpiry(expiry);
  if (!d) return expiry;
  return new Intl.DateTimeFormat('en-GB', {
    day: '2-digit',
    month: 'short',
    timeZone: IST
  }).format(d);
}

/** Human days-away tag: `Today`, `1d`, `3d`, … or "" when unknown/past. */
export function daysAwayLabel(expiry: string): string {
  const d = daysAway(expiry);
  if (d == null) return '';
  if (d <= 0) return 'Today';
  return `${d}d`;
}

/** Parse the common expiry encodings (ISO, `06AUG25`, `06-Aug-2025`). */
function parseExpiry(expiry: string): Date | null {
  const iso = new Date(expiry);
  if (!Number.isNaN(iso.getTime())) return istMidnight(iso);

  const m = expiry.match(/^(\d{1,2})[-\s]?([A-Za-z]{3})[-\s]?(\d{2,4})$/);
  if (m) {
    const dd = m[1];
    const mon = m[2];
    const yy = m[3];
    if (dd && mon && yy) {
      const months = [
        'jan',
        'feb',
        'mar',
        'apr',
        'may',
        'jun',
        'jul',
        'aug',
        'sep',
        'oct',
        'nov',
        'dec'
      ];
      const mi = months.indexOf(mon.toLowerCase());
      if (mi >= 0) {
        const year = yy.length === 2 ? 2000 + Number(yy) : Number(yy);
        return istMidnight(new Date(year, mi, Number(dd)));
      }
    }
  }
  return null;
}

function istMidnight(d: Date): Date {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: IST,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit'
  }).format(d);
  return new Date(`${parts}T00:00:00`);
}
