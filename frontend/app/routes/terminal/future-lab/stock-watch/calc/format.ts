/**
 * Formatting and feed-freshness, shared by every panel on the page.
 *
 * One module so that a price on the chain, a price in the planner and a price
 * in the journal round the same way. Two screens quoting the same contract to
 * different precisions is a bug report nobody can reproduce.
 *
 * The staleness half is here rather than in a component because it is a
 * judgement with a rule behind it, and the rule belongs somewhere testable:
 * silently rendering a six-minute-old quote as current is the failure this
 * whole terminal is meant not to have.
 */

import type { DataSourceName } from '$contexts/broker-connections/types';

const INR = new Intl.NumberFormat('en-IN', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2
});

const INR_0 = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 });

/** A dash, not a zero. Every formatter returns this for absent input. */
export const EMPTY = '—';

export function fmtPrice(value: number | undefined | null): string {
  if (value == null || !Number.isFinite(value)) return EMPTY;
  return INR.format(value);
}

export function fmtInt(value: number | undefined | null): string {
  if (value == null || !Number.isFinite(value)) return EMPTY;
  return INR_0.format(value);
}

/** A true minus sign, which aligns in a tabular column where a hyphen does not. */
export function sign(value: number): string {
  return value > 0 ? '+' : value < 0 ? '−' : '';
}

export function fmtSigned(value: number | undefined | null, digits = 2): string {
  if (value == null || !Number.isFinite(value)) return EMPTY;
  return `${sign(value)}${Math.abs(value).toLocaleString('en-IN', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits
  })}`;
}

export function fmtPercent(value: number | undefined | null, digits = 2): string {
  if (value == null || !Number.isFinite(value)) return EMPTY;
  return `${sign(value)}${Math.abs(value).toFixed(digits)}%`;
}

/**
 * Indian units — lakh and crore — for open interest and turnover.
 *
 * Not K/M/B. The reader's other screens say 12.4L, and a terminal that says
 * 1.24M forces a conversion on every glance.
 *
 * A *magnitude*: a negative reads with a minus, a positive reads bare. Open
 * interest and volume are counts, and "+12.50L contracts open" asserts a
 * direction the number does not have — use {@link fmtIndianSigned} for a
 * change, where the sign is the whole point.
 */
export function fmtIndian(value: number | undefined | null): string {
  if (value == null || !Number.isFinite(value)) return EMPTY;
  return `${value < 0 ? '−' : ''}${magnitude(Math.abs(value))}`;
}

/** The same scale, always signed — for a change in open interest or volume. */
export function fmtIndianSigned(value: number | undefined | null): string {
  if (value == null || !Number.isFinite(value)) return EMPTY;
  return `${sign(value)}${magnitude(Math.abs(value))}`;
}

function magnitude(abs: number): string {
  if (abs >= 1e7) return `${(abs / 1e7).toFixed(2)}Cr`;
  if (abs >= 1e5) return `${(abs / 1e5).toFixed(2)}L`;
  if (abs >= 1e3) return `${(abs / 1e3).toFixed(1)}K`;
  return abs.toFixed(0);
}

/** `₹1,24,500` — grouped Indian-style, no paise. */
export function fmtRupees(value: number | undefined | null): string {
  if (value == null || !Number.isFinite(value)) return EMPTY;
  return `${value < 0 ? '−' : ''}₹${INR_0.format(Math.abs(value))}`;
}

export function fmtRupeesPrecise(value: number | undefined | null): string {
  if (value == null || !Number.isFinite(value)) return EMPTY;
  return `${value < 0 ? '−' : ''}₹${INR.format(Math.abs(value))}`;
}

/** An ISO instant or epoch-seconds as IST clock time. */
export function fmtIst(at: string | number | Date | undefined): string {
  if (at == null) return EMPTY;
  const date = typeof at === 'number' ? new Date(at * 1000) : new Date(at);
  if (Number.isNaN(date.getTime())) return EMPTY;
  return date.toLocaleTimeString('en-IN', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
    timeZone: 'Asia/Kolkata'
  });
}

/** An ISO date as `30 Oct 2026`. */
export function fmtDate(iso: string | undefined): string {
  if (!iso) return EMPTY;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleDateString('en-IN', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    timeZone: 'Asia/Kolkata'
  });
}

/** `up` | `down` | null — null when there is nothing to colour. */
export function tone(value: number | undefined | null): 'up' | 'down' | null {
  if (value == null || !Number.isFinite(value) || value === 0) return null;
  return value > 0 ? 'up' : 'down';
}

// -- freshness ----------------------------------------------------------------

/** Seconds past which a quote is called stale while the market is open. */
export const STALE_AFTER_SECONDS = 90;
/** And past which it is called badly stale, warranting a louder warning. */
export const VERY_STALE_AFTER_SECONDS = 300;

export type Freshness = 'fresh' | 'stale' | 'very_stale' | 'simulated' | 'unavailable';

export interface FeedState {
  freshness: Freshness;
  ageSeconds: number;
  source: DataSourceName;
  /** One line a user can act on. Empty when fresh. */
  message: string;
}

/**
 * How much to trust what is on screen.
 *
 * Simulated outranks stale: a mock quote that arrived a second ago is fresh
 * and still must not be traded on, so it gets its own state rather than a
 * green dot. Staleness is only judged while the market is open — at 20:00 a
 * four-hour-old last print is the close, not a broken feed, and warning about
 * it every evening trains the reader to ignore the warning.
 */
export function feedState(
  source: DataSourceName,
  ageSeconds: number | undefined,
  marketOpen: boolean
): FeedState {
  const age = ageSeconds ?? 0;
  if (source === 'unavailable') {
    return {
      freshness: 'unavailable',
      ageSeconds: age,
      source,
      message: 'No data — the provider returned nothing for this instrument.'
    };
  }
  if (source === 'mock') {
    return {
      freshness: 'simulated',
      ageSeconds: age,
      source,
      message: 'Simulated data — no live broker feed is connected. Not tradeable.'
    };
  }
  if (!marketOpen) {
    return { freshness: 'fresh', ageSeconds: age, source, message: '' };
  }
  if (age >= VERY_STALE_AFTER_SECONDS) {
    return {
      freshness: 'very_stale',
      ageSeconds: age,
      source,
      message: `Last update was ${Math.round(age)}s ago — the feed has stopped. Do not size a trade off this.`
    };
  }
  if (age >= STALE_AFTER_SECONDS) {
    return {
      freshness: 'stale',
      ageSeconds: age,
      source,
      message: `Last update was ${Math.round(age)}s ago while the market is open.`
    };
  }
  return { freshness: 'fresh', ageSeconds: age, source, message: '' };
}

/** `2m 14s ago`, or `just now` under five seconds. */
export function fmtAge(seconds: number | undefined): string {
  if (seconds == null || !Number.isFinite(seconds)) return EMPTY;
  if (seconds < 5) return 'just now';
  if (seconds < 60) return `${Math.round(seconds)}s ago`;
  const minutes = Math.floor(seconds / 60);
  const rest = Math.round(seconds % 60);
  return `${minutes}m ${rest}s ago`;
}

/** Parse a `Decimal`-as-string wire field. `undefined` when absent. */
export function wire(value: string | number | null | undefined): number | undefined {
  if (value == null || value === '') return undefined;
  const parsed = typeof value === 'number' ? value : Number.parseFloat(value);
  return Number.isFinite(parsed) ? parsed : undefined;
}
