/**
 * Wire types and pure derivations for the IV − HV Chart.
 *
 * The volatility risk premium: what the option market charged for movement,
 * against how much movement there actually was. Positive means options were
 * priced rich against what the index went on to do; negative means they were
 * cheap.
 *
 * Both inputs are already served and already derived — the daily IV archive and
 * the rolling historical volatility both belong to the IV/HV/IVP page, and this
 * module re-exports rather than restates them. What is new here is the
 * subtraction and the one rule that governs it: see {@link buildSpreadRows}.
 */

// Everything below the subtraction is the sibling page's, reused rather than
// duplicated so the two pages cannot drift into disagreeing about what HV is.
export {
  clockLabel,
  coverageNote,
  dailyBars,
  dateLabel,
  dayLabel,
  DEFAULT_HV_WINDOW,
  fetchDays,
  DEFAULT_RANGE,
  fmtIv,
  fmtPrice,
  freshnessLabel,
  getHistory,
  getIvHistory,
  HV_WINDOWS,
  hvSessions,
  istDate,
  logReturns,
  MAX_FETCH_DAYS,
  OI_INSTRUMENTS,
  rangeDays,
  RANGES,
  REFETCH_MS,
  rollingHv,
  SESSIONS_PER_YEAR,
  STALE_AFTER_MS,
  trimToRange,
  warmupDays,
  type DailyBar,
  type HistoryView,
  type HvWindowKey,
  type Instrument,
  type IvHistoryView,
  type IvSession,
  type RangeKey,
  type WireCandle
} from '../iv-hv-ivp/iv-hv-ivp-data';

export { CALL_COLOR, PUT_COLOR } from '../open-interest/oi-data';

import { rollingHv, type DailyBar, type IvSession } from '../iv-hv-ivp/iv-hv-ivp-data';

/**
 * The range this page opens on.
 *
 * A month, not the sibling's year. Bars only exist where the IV archive
 * reaches — currently a few weeks — and every longer range opens on a mostly
 * empty pane with the data crammed against the right edge. The Range select is
 * there for when the archive has grown into it.
 */
export const DEFAULT_SPREAD_RANGE = '1m' as const;

// -- the spread -------------------------------------------------------------

/** One session: the premium, and everything it was computed from. */
export interface SpreadRow {
  /** IST trading date, `YYYY-MM-DD`. */
  d: string;
  /** IV − HV in volatility points; `null` unless both sides were real. */
  spread: number | null;
  iv: number | null;
  hv: number | null;
  /** The index close — always present, it is the axis's spine. */
  close: number | null;
  /** The tradable future at that session's last capture, where recorded. */
  future: number | null;
}

/**
 * One row per trading session, with the premium where it can be computed.
 *
 * The price series is the spine — it has every session — and IV is joined onto
 * it, exactly as on the IV/HV/IVP page. HV comes from the same closes.
 *
 * **A bar is drawn only where both sides are real.** An implied volatility with
 * no historical volatility behind it is not a premium, and neither is a
 * historical volatility on a session nobody quoted an option on. Either alone
 * would still produce a number — `iv - 0`, or `0 - hv` — and that number would
 * be a large, confident, meaningless bar. `null` keeps it off the chart, which
 * is the honest state of a session that is missing half its inputs.
 */
export function buildSpreadRows(
  bars: DailyBar[],
  sessions: IvSession[],
  hvWindow: number
): SpreadRow[] {
  const ivByDate = new Map(sessions.map((session) => [session.d, session.iv]));
  const futureByDate = new Map(sessions.map((session) => [session.d, session.future_close]));
  const hv = rollingHv(
    bars.map((bar) => bar.close),
    hvWindow
  );

  return bars.map((bar, index) => {
    const iv = ivByDate.get(bar.d) ?? null;
    const historical = hv[index] ?? null;
    return {
      d: bar.d,
      spread: iv === null || historical === null ? null : iv - historical,
      iv,
      hv: historical,
      close: bar.close,
      future: futureByDate.get(bar.d) ?? null
    };
  });
}

/** What the bars add up to, for the caption. */
export interface SpreadStats {
  /** Sessions with a computable premium. */
  covered: number;
  /** Of those, how many had IV above HV. */
  rich: number;
  cheap: number;
  /** Mean premium over the covered sessions; `null` when there are none. */
  mean: number | null;
}

/**
 * The count either side of zero and the average premium.
 *
 * A page of bars invites the reader to eyeball which colour dominates, and
 * eyeballing a signed series is exactly where people go wrong — a few tall red
 * bars read as "mostly cheap" against thirty short green ones. Counting is
 * cheap and settles it.
 */
export function spreadStats(rows: SpreadRow[]): SpreadStats {
  const values = rows.map((row) => row.spread).filter((value): value is number => value !== null);

  if (values.length === 0) return { covered: 0, rich: 0, cheap: 0, mean: null };

  const rich = values.filter((value) => value > 0).length;
  return {
    covered: values.length,
    rich,
    // Deliberately not `length - rich`: a spread of exactly zero is neither,
    // and folding it into "cheap" would overstate one side.
    cheap: values.filter((value) => value < 0).length,
    mean: values.reduce((sum, value) => sum + value, 0) / values.length
  };
}

/** `+4.66` / `−1.20` — the sign is the whole reading, so it is always shown. */
export function fmtSpread(value: number): string {
  const sign = value > 0 ? '+' : value < 0 ? '−' : '';
  return `${sign}${Math.abs(value).toFixed(2)}`;
}

// -- CSV export -------------------------------------------------------------

export function ivHvCsv(rows: SpreadRow[]): string {
  const header = 'date,spread,iv,hv,close,future';
  const body = rows.map((row) =>
    [row.d, row.spread ?? '', row.iv ?? '', row.hv ?? '', row.close ?? '', row.future ?? ''].join(
      ','
    )
  );
  return [header, ...body].join('\n');
}

/** `iv-hv-NIFTY-2026-09-03.csv` — sortable, and says which day it ends on. */
export function csvFilename(symbol: string, rows: SpreadRow[]): string {
  const last = rows.at(-1);
  return last ? `iv-hv-${symbol}-${last.d}.csv` : `iv-hv-${symbol}.csv`;
}
