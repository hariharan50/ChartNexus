import type {
  GapBucket,
  LevelOrigin,
  RegimeBand,
  Stance,
  WireNumber
} from '$contexts/pre-market/types';

/**
 * Formatters and label tables for PMS.
 *
 * Page-local, following the `*-data.ts` convention every other terminal page
 * uses. Numbers are formatted identically to GIA and the dashboard on purpose:
 * a reader comparing the screener's NIFTY figure against the dashboard's must
 * not have to wonder whether a rounding difference is a data difference.
 */

/** Parse a wire Decimal. `null` for anything unparseable — never 0. */
export function toNumber(value: WireNumber | null | undefined): number | null {
  if (value === null || value === undefined) return null;
  const parsed = typeof value === 'number' ? value : Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

/** A true minus sign, not a hyphen — it lines up in a tabular column. */
function sign(n: number): string {
  return n > 0 ? '+' : n < 0 ? '−' : '';
}

/** An index level, grouped Indian-style, to two decimals throughout. */
export function fmtLevel(value: WireNumber | number | null | undefined): string {
  const n = toNumber(value ?? null);
  if (n === null) return '—';
  return n.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

/** A signed change, to two decimals. The sign is the reading. */
export function fmtChange(value: WireNumber | number | null | undefined): string {
  const n = toNumber(value ?? null);
  if (n === null) return '—';
  return `${sign(n)}${Math.abs(n).toLocaleString('en-IN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  })}`;
}

/** A signed percentage, to two decimals. */
export function fmtPercent(value: WireNumber | number | null | undefined): string {
  const n = toNumber(value ?? null);
  if (n === null) return '—';
  return `${sign(n)}${Math.abs(n).toFixed(2)}%`;
}

/** An unsigned figure to one decimal — scores, RSI, ADX. */
export function fmtOne(value: number | null | undefined): string {
  return value === null || value === undefined ? '—' : value.toFixed(1);
}

/** A count-of-total, so a percentage never travels without its denominator. */
export function fmtOutOf(count: number | null, total: number | null): string {
  if (count === null) return '—';
  if (total === null || total <= 0) return String(count);
  return `${count} of ${total}`;
}

/** An ATR multiple, which is the distance figure that transfers across indices. */
export function fmtAtr(value: number | null | undefined): string {
  return value === null || value === undefined
    ? '—'
    : `${sign(value)}${Math.abs(value).toFixed(2)}×`;
}

/** 'up' | 'down' | null. Null when there is nothing to colour. */
export function tone(value: WireNumber | number | null | undefined): 'up' | 'down' | null {
  const n = toNumber(value ?? null);
  if (n === null || n === 0) return null;
  return n > 0 ? 'up' : 'down';
}

export const GAP_LABELS: Record<GapBucket, string> = {
  gap_down_large: 'LARGE GAP DOWN',
  gap_down: 'GAP DOWN',
  flat: 'FLAT',
  gap_up: 'GAP UP',
  gap_up_large: 'LARGE GAP UP'
};

export function gapTone(bucket: GapBucket): 'up' | 'down' | null {
  if (bucket === 'flat') return null;
  return bucket.startsWith('gap_up') ? 'up' : 'down';
}

export const REGIME_LABELS: Record<RegimeBand, string> = {
  strongly_bearish: 'STRONGLY BEARISH',
  bearish: 'BEARISH',
  neutral: 'NEUTRAL',
  bullish: 'BULLISH',
  strongly_bullish: 'STRONGLY BULLISH'
};

export function regimeTone(band: RegimeBand): 'up' | 'down' | null {
  if (band === 'neutral') return null;
  return band.endsWith('bullish') ? 'up' : 'down';
}

export function stanceTone(stance: Stance): 'up' | 'down' | null {
  if (stance === 'neutral') return null;
  return stance === 'bullish' ? 'up' : 'down';
}

export const ORIGIN_LABELS: Record<LevelOrigin, string> = {
  pivot: 'Pivot',
  central_pivot: 'CPR',
  prior_day: 'Prev day',
  weekly: '5-session',
  monthly: '21-session',
  yearly: '52-week',
  option_wall: 'Option OI',
  max_pain: 'Max pain',
  gamma_flip: 'Gamma'
};

export const MOVE_LABELS: Record<'straddle' | 'vix' | 'atr', string> = {
  straddle: 'Straddle (priced)',
  vix: 'India VIX (implied)',
  atr: 'ATR (realised)'
};

/**
 * How the confidence reads to someone who has not read the code.
 *
 * Coverage, never conviction: a lopsided score off three inputs is thin, and
 * this wording has to stop it looking like a strong call.
 */
export const CONFIDENCE_NOTES: Record<'thin' | 'moderate' | 'high', string> = {
  thin: 'Most inputs are missing — read this as indicative only.',
  moderate: 'Some inputs are missing.',
  high: 'Built on the full input set.'
};

/** An ISO instant as IST clock time. */
export function fmtIst(iso: string): string {
  const at = new Date(iso);
  if (Number.isNaN(at.getTime())) return '—';
  return at.toLocaleTimeString('en-IN', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
    timeZone: 'Asia/Kolkata'
  });
}

/**
 * Minutes until the open, or `null` once it has passed.
 *
 * Both clock strings are IST `HH:MM` from the server, so this is string
 * arithmetic on the exchange's own clock rather than on the browser's — a
 * reader in another timezone gets the same countdown as one in Mumbai.
 */
export function minutesToOpen(nowIst: string, opensIst: string): number | null {
  const now = parseClock(nowIst);
  const opens = parseClock(opensIst);
  if (now === null || opens === null || now >= opens) return null;
  return opens - now;
}

function parseClock(value: string): number | null {
  const parts = value.split(':');
  const hours = Number(parts[0]);
  const minutes = Number(parts[1]);
  if (!Number.isFinite(hours) || !Number.isFinite(minutes)) return null;
  return hours * 60 + minutes;
}

/** "1h 12m" / "18m". Short enough to sit in a header without wrapping. */
export function fmtCountdown(minutes: number): string {
  if (minutes < 60) return `${minutes}m`;
  return `${Math.floor(minutes / 60)}h ${minutes % 60}m`;
}
