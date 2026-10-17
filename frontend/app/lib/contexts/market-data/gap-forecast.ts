/**
 * The pre-open gap *forecast* — what the dashboard card shows before the bell.
 *
 * **Why this exists.** Until the opening auction runs there is no opening
 * print, so `/market/spot` returns no gap at all: a broker's `open_price`
 * before 09:15 is the *previous* session's figure, and the card used to
 * subtract it from the previous close and publish the result as today's
 * verdict. At 08:00 that reads as a confident FLAT about a session that has
 * not happened. The backend now refuses to measure in that window, and this
 * module fills it with the thing a reader actually wants there: an estimate,
 * labelled as an estimate.
 *
 * **Where the estimate comes from.** GIFT NIFTY — the same reading GIA's
 * implied-open card renders, off the same polled `/global/view` response, so
 * the two screens can never quote different numbers for the same morning. The
 * contract settles to NIFTY and trades through the night, which makes it the
 * market's own quote of where the index opens rather than an inference from
 * one. The weighted global composite is carried alongside as a cross-check,
 * never averaged in: the mornings the two disagree are the informative ones,
 * and a single blended arrow would erase exactly those.
 *
 * Nothing here is measured and nothing here is latched. A forecast is allowed
 * to move — that is the difference between it and the opening print, and the
 * card says which of the two it is showing.
 */

import type { DataSourceName } from '$contexts/broker-connections/types';
import type { GapSignal, GlobalView, PressureBand, Verdict } from '$contexts/global-markets/types';
import { SESSION_OPEN_MIN, istClock } from '$shared/formatting/ist-clock';

/** Minutes past IST midnight at which the pre-open card starts watching. */
export const PRE_OPEN_WATCH_MIN = 8 * 60;

/**
 * How much weight to put on the forecast, as a label the card can show.
 *
 * Three levels rather than a percentage, on purpose. A number like "68%
 * confident" implies a calibration nobody here has measured; what *is* known
 * is whether the contract quote is real, whether enough of the world could be
 * priced, and whether the two independent reads agree. Those are stated.
 */
export type Confidence = 'high' | 'medium' | 'low';

export interface GapForecast {
  /** The index this forecasts — only NIFTY has a contract that quotes it. */
  label: string;
  signal: GapSignal;
  /** GIFT against the close the next session opens from. */
  points: number;
  percent: number;
  /** GIFT NIFTY's own level: the market's quote of the opening level. */
  impliedLevel: number;
  /** The NIFTY close that open would gap from. */
  referenceClose: number;
  /** `mock` means NSE IX could not be reached and this is simulated. */
  source: DataSourceName;
  /** When the server read it. The forecast moves; this says how recently. */
  asOf: Date;
  /** The bell this forecast is for, as the server placed it. */
  opensAt: Date;
  /** Whether the composite and GIFT tell the same story. */
  verdict: Verdict;
  pressureScore: number;
  pressureBand: PressureBand;
  /** Weighted markets the composite could not price — named, not hidden. */
  missing: number;
  confidence: Confidence;
  /** One sentence saying why the confidence is what it is. */
  confidenceReason: string;
}

/**
 * The forecast, or `undefined` when there is nothing honest to show.
 *
 * Absent whenever GIFT has no quote: the composite alone is an inference about
 * an inference, and dressing it up as a gap figure would put a points value on
 * screen that no instrument anywhere is actually quoting.
 */
export function gapForecast(view: GlobalView | undefined, label: string): GapForecast | undefined {
  const implied = view?.implied;
  if (!view || !implied) return undefined;

  const points = toNumber(implied.gap_points);
  const percent = toNumber(implied.gap_percent);
  const impliedLevel = toNumber(implied.gift_level);
  const referenceClose = toNumber(implied.reference_close);
  if (![points, percent, impliedLevel, referenceClose].every(Number.isFinite)) return undefined;
  if (impliedLevel <= 0 || referenceClose <= 0) return undefined;

  const missing = view.pressure.missing.length;
  const confidence = rate(view.gift_source, view.verdict, missing);

  return {
    label,
    signal: implied.signal,
    points,
    percent,
    impliedLevel,
    referenceClose,
    source: view.gift_source,
    asOf: new Date(view.as_of),
    opensAt: new Date(view.window.closes_at),
    verdict: view.verdict,
    pressureScore: toNumber(view.pressure.score),
    pressureBand: view.pressure.band,
    missing,
    confidence,
    confidenceReason: reasonFor(confidence, view.gift_source, view.verdict, missing)
  };
}

/**
 * Whether the clock is inside the morning window this card is built for.
 *
 * 08:00 to the bell, weekdays. Read off the exchange clock rather than the
 * viewer's, the same way the session-phase strip is, so someone watching from
 * another timezone sees India's morning and not their own.
 *
 * Before 08:00 the forecast still renders — GIFT has been trading all night
 * and the number is real — but the countdown and the faster poll belong to the
 * window a trader is actually sitting in front of the screen for.
 */
export function inPreOpenWatch(at: number = Date.now()): boolean {
  const { minutes, weekend } = istClock(at);
  return !weekend && minutes >= PRE_OPEN_WATCH_MIN && minutes < SESSION_OPEN_MIN;
}

/** Whole minutes until the bell, floored at zero. */
export function minutesToOpen(at: number = Date.now()): number {
  const { minutes } = istClock(at);
  return Math.max(0, SESSION_OPEN_MIN - minutes);
}

/** `1h 14m`, or `14m` under the hour. Zero reads as `now`. */
export function countdownLabel(minutes: number): string {
  if (minutes <= 0) return 'now';
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  return hours > 0 ? `${hours}h ${rest}m` : `${rest}m`;
}

/**
 * Three inputs decide how much the forecast is worth, and all three are
 * things the response states rather than things guessed at here.
 */
function rate(source: DataSourceName, verdict: Verdict, missing: number): Confidence {
  // A simulated contract is not a forecast at all, whatever the rest says.
  if (source === 'mock') return 'low';
  if (missing >= 3) return 'low';
  if (verdict === 'disagree') return 'medium';
  if (verdict === 'agree' && missing === 0) return 'high';
  return 'medium';
}

function reasonFor(
  confidence: Confidence,
  source: DataSourceName,
  verdict: Verdict,
  missing: number
): string {
  if (source === 'mock') {
    return 'Simulated — NSE IX could not be reached, so this is a synthetic contract and not tradeable.';
  }
  if (missing >= 3) {
    return `${missing} weighted markets had no quote, so the cross-check behind this is thin.`;
  }
  if (verdict === 'disagree') {
    return 'GIFT and the global composite disagree — the contract is pricing something the world indices are not.';
  }
  if (confidence === 'high') {
    return 'GIFT and the global composite point the same way, with every weighted market priced.';
  }
  return 'Neither read is strong enough to confirm the other.';
}

/** A `Decimal` on the wire. `NaN` when the field is absent or unparseable. */
function toNumber(value: string | number | null | undefined): number {
  if (value === null || value === undefined || value === '') return Number.NaN;
  return typeof value === 'number' ? value : Number(value);
}
