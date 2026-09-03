/**
 * Wire types and pure derivations for the IV/HV/IVP Chart.
 *
 * The only Options Lab page that reads *days* rather than captures, and the only
 * one that draws two payloads on one axis: a year of daily index bars from
 * `/market/history`, and however many sessions of at-the-money implied
 * volatility the archive has accrued.
 *
 * Everything the chart shows beyond those two arrays is computed here — the two
 * volatility estimators, the rank and the percentile — so the arithmetic is
 * testable without a canvas and re-windowing a range costs no round trip.
 *
 * **A note on what is honest.** Implied volatility is quoted only in the moment,
 * and the intraday archive that holds it is pruned after 30 days, so daily IV
 * only exists from the point the rollup started running. The payload says how
 * many sessions it really covers, {@link coverageNote} turns that into words,
 * and {@link ivRank}/{@link ivPercentile} return `null` rather than a confident
 * number when the lookback is too thin to mean anything.
 */

import { apiFetch } from '$shared/api/client';

// Shared clock/instrument helpers, reused rather than duplicated so this page
// reads the same session the rest of the Lab does.
export {
  OI_INSTRUMENTS,
  REFETCH_MS,
  STALE_AFTER_MS,
  clockLabel,
  dateLabel,
  freshnessLabel,
  type Instrument
} from '../open-interest/oi-data';

// The daily-bar fetcher is the Analyse page's; one history endpoint, one client.
export { getHistory, type HistoryView, type WireCandle } from '../../analyse/analyse-data';

import type { WireCandle } from '../../analyse/analyse-data';

// -- the IV payload ---------------------------------------------------------

export interface IvSession {
  /** IST trading date, `YYYY-MM-DD`. */
  d: string;
  /** Volatility points — 13.2 means 13.2%. */
  iv: number;
  future_close: number | null;
  captures: number;
}

export interface IvHistoryView {
  instrument_id: string;
  symbol: string;
  requested_days: number;
  /** Sessions actually stored. Routinely far short of `requested_days`. */
  covered_sessions: number;
  start: string;
  end: string;
  sessions: IvSession[];
}

export function getIvHistory(
  instrument: string,
  days: number,
  fetcher?: typeof fetch
): Promise<IvHistoryView> {
  return apiFetch<IvHistoryView>({
    url: `/options-lab/iv-history/${encodeURIComponent(instrument)}`,
    params: { days },
    fetcher
  });
}

// -- ranges -----------------------------------------------------------------

export type RangeKey = '1m' | '3m' | '6m' | '1y';

/** The IVP/IVR lookback, and how much daily history to fetch for it. */
export const RANGES: readonly { value: RangeKey; label: string; days: number }[] = [
  { value: '1m', label: '1 Month', days: 30 },
  { value: '3m', label: '3 Months', days: 90 },
  { value: '6m', label: '6 Months', days: 180 },
  { value: '1y', label: '1 Year', days: 365 }
];

export const DEFAULT_RANGE: RangeKey = '1y';

export type HvWindowKey = '10d' | '1m' | '3m' | '6m';

/** The HV/RV averaging window, in *sessions* — trading days, not calendar. */
export const HV_WINDOWS: readonly { value: HvWindowKey; label: string; sessions: number }[] = [
  { value: '10d', label: '10 Days', sessions: 10 },
  { value: '1m', label: '1 Month', sessions: 21 },
  { value: '3m', label: '3 Months', sessions: 63 },
  { value: '6m', label: '6 Months', sessions: 126 }
];

export const DEFAULT_HV_WINDOW: HvWindowKey = '1m';

export function rangeDays(key: RangeKey): number {
  return RANGES.find((entry) => entry.value === key)?.days ?? 365;
}

export function hvSessions(key: HvWindowKey): number {
  return HV_WINDOWS.find((entry) => entry.value === key)?.sessions ?? 21;
}

/** Trading days in a year — the annualisation factor for a daily series. */
export const SESSIONS_PER_YEAR = 252;

/**
 * Extra calendar days to fetch *before* the window the reader asked for.
 *
 * A rolling statistic cannot report a value until its window has filled, so a
 * chart that fetches exactly the range it draws spends that whole range warming
 * up and plots almost nothing. At Range = 1 Month with a 1-Month HV window the
 * two are the same length, and the series produces exactly one point — the last
 * one — which is what "the chart is broken" looks like.
 *
 * So the fetch is the visible range *plus* the window, and the extra is trimmed
 * off after the maths but before the drawing. Sessions are converted to
 * calendar days because the endpoint counts calendar days, with a week of slack
 * for public holidays.
 */
export function warmupDays(sessions: number): number {
  return Math.ceil((sessions * 365) / SESSIONS_PER_YEAR) + 7;
}

/** The endpoint's hard ceiling — `days` is validated to 1-365. */
export const MAX_FETCH_DAYS = 365;

/**
 * How much history to ask for so the drawn range is fully warmed up.
 *
 * Clamped to what the endpoint serves: a 1-Year range with a 6-Month window
 * wants more than a year, and there is no more than a year to be had. In that
 * corner the left edge of the chart warms up on screen, which is the honest
 * outcome and still far better than warming up across the whole range.
 */
export function fetchDays(rangeDays: number, hvWindowSessions: number): number {
  return Math.min(MAX_FETCH_DAYS, rangeDays + warmupDays(hvWindowSessions));
}

/**
 * Drop the warm-up, keeping the range the reader asked for.
 *
 * Measured back from the newest session rather than from today, so a stale
 * archive shows its most recent N days instead of an empty window.
 */
export function trimToRange<T extends { d: string }>(rows: T[], rangeDays: number): T[] {
  const last = rows.at(-1);
  if (!last) return rows;
  const cutoff = new Date(`${last.d}T00:00:00Z`);
  cutoff.setUTCDate(cutoff.getUTCDate() - rangeDays);
  const from = cutoff.toISOString().slice(0, 10);
  return rows.filter((row) => row.d > from);
}

// -- volatility -------------------------------------------------------------

/**
 * Log returns between consecutive closes, `null` where either end is unusable.
 *
 * Log rather than simple returns because these get summed and scaled: log
 * returns are additive over time, which is the property annualising by √252
 * quietly assumes.
 */
export function logReturns(closes: (number | null)[]): (number | null)[] {
  return closes.map((close, index) => {
    if (index === 0) return null;
    const prev = closes[index - 1];
    if (prev == null || close == null || prev <= 0 || close <= 0) return null;
    return Math.log(close / prev);
  });
}

/**
 * Rolling annualised close-to-close volatility, in percentage points.
 *
 * The textbook HV every platform quotes: the standard deviation of daily log
 * returns over the window, scaled by √252 and expressed as a percentage so it
 * sits on the same axis as implied volatility.
 *
 * `null` until the window has filled — a 21-day number computed from four days
 * is not a 21-day number, and drawing it as one is how a chart lies about its
 * own left edge.
 */
export function rollingHv(closes: (number | null)[], window: number): (number | null)[] {
  const returns = logReturns(closes);
  return closes.map((_, index) => {
    if (window < 2 || index + 1 < window + 1) return null;
    const slice = returns.slice(index - window + 1, index + 1);
    const usable = slice.filter((value): value is number => value !== null);
    // A window mostly made of gaps is not a window. Two thirds is arbitrary but
    // deliberate: it tolerates a holiday without tolerating a dead month.
    if (usable.length < Math.ceil(window * (2 / 3))) return null;
    const mean = usable.reduce((sum, value) => sum + value, 0) / usable.length;
    const variance =
      usable.reduce((sum, value) => sum + (value - mean) ** 2, 0) / (usable.length - 1 || 1);
    return Math.sqrt(variance) * Math.sqrt(SESSIONS_PER_YEAR) * 100;
  });
}

/**
 * Rolling annualised realised volatility from the bar's own range.
 *
 * Garman–Klass, which reads each day's high, low, open and close rather than
 * only the close. A day that travelled 300 points and came back to where it
 * started is a volatile day; close-to-close scores it at zero, and this does
 * not. That is the whole reason both lines are on the chart: where they part
 * company, the movement happened *inside* the sessions rather than between
 * them.
 */
export function rollingRv(bars: DailyBar[], window: number): (number | null)[] {
  const terms = bars.map((bar) => {
    if (bar.high <= 0 || bar.low <= 0 || bar.open <= 0 || bar.close <= 0) return null;
    const hl = Math.log(bar.high / bar.low);
    const co = Math.log(bar.close / bar.open);
    return 0.5 * hl * hl - (2 * Math.LN2 - 1) * co * co;
  });

  return bars.map((_, index) => {
    if (window < 2 || index + 1 < window) return null;
    const slice = terms.slice(index - window + 1, index + 1);
    const usable = slice.filter((value): value is number => value !== null);
    if (usable.length < Math.ceil(window * (2 / 3))) return null;
    const mean = usable.reduce((sum, value) => sum + value, 0) / usable.length;
    // Garman-Klass can go slightly negative on a bar whose body exceeds its
    // range through rounding; a negative variance has no square root, and
    // clamping to zero is truer than dropping the day.
    return Math.sqrt(Math.max(0, mean)) * Math.sqrt(SESSIONS_PER_YEAR) * 100;
  });
}

/**
 * The fewest observations an IV Rank or Percentile is allowed to be built from.
 *
 * Below this the statistic is arithmetic rather than information: a percentile
 * over four readings can only ever be 0, 25, 50, 75 or 100, and it will look
 * exactly as authoritative as one over two hundred.
 */
export const MIN_IV_OBSERVATIONS = 10;

/**
 * IV Rank — where today's IV sits between the lookback's low and high, 0-100.
 *
 * `null` where the lookback is too thin, and where the window is perfectly flat
 * (a zero range has no position within it to report).
 */
export function ivRank(ivs: (number | null)[], window: number): (number | null)[] {
  return ivs.map((today, index) => {
    if (today == null) return null;
    const past = usableWindow(ivs, index, window);
    if (past.length < MIN_IV_OBSERVATIONS) return null;
    const low = Math.min(...past);
    const high = Math.max(...past);
    if (high <= low) return null;
    return ((today - low) / (high - low)) * 100;
  });
}

/**
 * IV Percentile — the share of the lookback's sessions that sat below today.
 *
 * Different from rank, and the difference is the point: rank cares only about
 * the two extremes, so one panic day drags it down all year, while percentile
 * counts every session and is unmoved by a single outlier.
 */
export function ivPercentile(ivs: (number | null)[], window: number): (number | null)[] {
  return ivs.map((today, index) => {
    if (today == null) return null;
    const past = usableWindow(ivs, index, window);
    if (past.length < MIN_IV_OBSERVATIONS) return null;
    const below = past.filter((value) => value < today).length;
    return (below / past.length) * 100;
  });
}

/** The quoted readings in the trailing window ending at `index`, inclusive. */
function usableWindow(ivs: (number | null)[], index: number, window: number): number[] {
  const from = Math.max(0, index - window + 1);
  return ivs.slice(from, index + 1).filter((value): value is number => value !== null);
}

// -- alignment --------------------------------------------------------------

export interface DailyBar {
  /** IST trading date, `YYYY-MM-DD`. */
  d: string;
  open: number;
  high: number;
  low: number;
  close: number;
}

export interface SkewRow {
  d: string;
  close: number | null;
  iv: number | null;
  hv: number | null;
  rv: number | null;
  ivr: number | null;
  ivp: number | null;
}

/**
 * Candles reduced to one bar per IST trading date.
 *
 * The endpoint returns UTC instants; two of them can land on the same IST date
 * around the boundary, and the last one is the session's close.
 */
export function dailyBars(candles: WireCandle[]): DailyBar[] {
  const byDate = new Map<string, DailyBar>();
  for (const candle of candles) {
    const d = istDate(candle.time);
    const existing = byDate.get(d);
    if (existing === undefined) {
      byDate.set(d, {
        d,
        open: candle.open,
        high: candle.high,
        low: candle.low,
        close: candle.close
      });
      continue;
    }
    byDate.set(d, {
      d,
      open: existing.open,
      high: Math.max(existing.high, candle.high),
      low: Math.min(existing.low, candle.low),
      close: candle.close
    });
  }
  return [...byDate.values()].sort((a, b) => a.d.localeCompare(b.d));
}

/** The IST calendar date an ISO instant belongs to. */
export function istDate(iso: string): string {
  const ms = Date.parse(iso);
  if (Number.isNaN(ms)) return iso.slice(0, 10);
  return new Date(ms + 5.5 * 3600_000).toISOString().slice(0, 10);
}

/**
 * One row per trading date, price and volatility side by side.
 *
 * The price axis is the spine: it has a year of dates and IV has whatever the
 * archive holds, so IV is joined onto it and left `null` everywhere it has
 * nothing to say. That asymmetry is the page — thirty sessions of a real IV
 * curve sitting inside a year of price, rather than a year of price truncated
 * to thirty days to match.
 */
export function buildRows(
  bars: DailyBar[],
  sessions: IvSession[],
  { hvWindow, ivWindow }: { hvWindow: number; ivWindow: number }
): SkewRow[] {
  const ivByDate = new Map(sessions.map((session) => [session.d, session.iv]));
  const closes = bars.map((bar) => bar.close);
  const hv = rollingHv(closes, hvWindow);
  const rv = rollingRv(bars, hvWindow);
  const ivs = bars.map((bar) => ivByDate.get(bar.d) ?? null);
  const ivr = ivRank(ivs, ivWindow);
  const ivp = ivPercentile(ivs, ivWindow);

  return bars.map((bar, index) => ({
    d: bar.d,
    close: bar.close,
    iv: ivs[index] ?? null,
    hv: hv[index] ?? null,
    rv: rv[index] ?? null,
    ivr: ivr[index] ?? null,
    ivp: ivp[index] ?? null
  }));
}

// -- formatting -------------------------------------------------------------

/** A volatility or percentile, two decimals — what the reference's tooltip shows. */
export function fmtIv(value: number): string {
  return value.toFixed(2);
}

/** The index level, grouped Indian-style, one decimal. */
export function fmtPrice(value: number): string {
  return value.toLocaleString('en-IN', { minimumFractionDigits: 1, maximumFractionDigits: 1 });
}

/** `30 Jul 26` — the tooltip header and the axis ticks. */
export function dayLabel(d: string): string {
  const date = new Date(`${d}T00:00:00Z`);
  if (Number.isNaN(date.getTime())) return d;
  return new Intl.DateTimeFormat('en-GB', {
    day: 'numeric',
    month: 'short',
    year: '2-digit',
    timeZone: 'UTC'
  }).format(date);
}

/**
 * What to say about a curve that is shorter than the range asked for.
 *
 * `null` when the history covers the lookback, so a healthy page says nothing.
 */
export function coverageNote(view: IvHistoryView | undefined, window: number): string | null {
  if (!view) return null;
  const covered = view.covered_sessions;
  if (covered === 0) {
    return 'No implied-volatility history recorded yet — IV, IVR and IVP fill in one session per trading day.';
  }
  if (covered < MIN_IV_OBSERVATIONS) {
    return `Only ${covered} session${covered === 1 ? '' : 's'} of implied volatility recorded — too few to rank, so IVR and IVP stay blank until there are ${MIN_IV_OBSERVATIONS}.`;
  }
  if (covered < window) {
    return `IV ranked over the ${covered} sessions recorded so far, not the full window — the archive accrues one session per trading day.`;
  }
  return null;
}

// -- CSV export -------------------------------------------------------------

export function ivHvIvpCsv(rows: SkewRow[]): string {
  const header = 'date,close,iv,hv,rv,ivr,ivp';
  const body = rows.map((row) =>
    [
      row.d,
      row.close ?? '',
      row.iv ?? '',
      row.hv ?? '',
      row.rv ?? '',
      row.ivr ?? '',
      row.ivp ?? ''
    ].join(',')
  );
  return [header, ...body].join('\n');
}

/** `iv-hv-ivp-NIFTY-2026-09-03.csv` — sortable, and says which day it ends on. */
export function csvFilename(symbol: string, rows: SkewRow[]): string {
  const last = rows.at(-1);
  return last ? `iv-hv-ivp-${symbol}-${last.d}.csv` : `iv-hv-ivp-${symbol}.csv`;
}
