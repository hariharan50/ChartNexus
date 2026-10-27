/**
 * When each index settles, and how close that is.
 *
 * Expiry day is the largest regime change an index-options reader faces, and
 * the three indices no longer share one calendar: NIFTY settles Tuesday,
 * SENSEX Thursday, and BANK NIFTY retired its weekly series entirely. A page
 * that shows three boards side by side therefore cannot state one expiry; it
 * has to state three, and say which kind each one is.
 *
 * **Two sources, and the order between them is the whole design.** The broker's
 * listed expiries are authoritative because they are holiday-aware — there is
 * no exchange holiday calendar anywhere in this codebase, so a locally computed
 * date is wrong on exactly the weeks it matters most. `futures_contract.py` on
 * the backend states the same rule for futures contracts.
 *
 * The rules table below is the fallback, and it exists for a specific failure
 * rather than as a general safety net: the mock provider's `upcoming_expiries`
 * returns *Thursdays for every instrument*, so a dev environment that trusted
 * the list blindly would show NIFTY expiring Thursday — the one thing this
 * feature exists to get right. Anything computed from the rules is flagged
 * `estimated` and says so on screen, because a scheduled date presented as a
 * confirmed one is worse than no card.
 */

import type { Provenance } from '$contexts/broker-connections/types';
import { isoDateIST } from '$shared/formatting/ist-clock';
import type { IndexKey } from './view-models';

/**
 * What a date means, not when it falls.
 *
 * `both` is not a degenerate case: the monthly expiry *is* that week's weekly
 * expiry, and a card that printed the same date on two rows would read as a
 * bug. One row carrying both tags is the honest rendering.
 */
export type ExpiryKind = 'weekly' | 'monthly' | 'both';

/** 0 days / 1 day / 2-3 days / further out. */
export type ExpiryUrgency = 'today' | 'tomorrow' | 'near' | 'distant';

export interface ExpiryMarker {
  kind: ExpiryKind;
  /** ISO `YYYY-MM-DD`, an IST calendar date. */
  date: string;
  /** Calendar days from the session date; 0 is today. Never negative — a
      settled contract is dropped rather than reported as overdue. */
  daysAway: number;
  urgency: ExpiryUrgency;
  /** Computed from the rules rather than read off the broker's list. The card
      must say so: the day is a schedule, and holidays move it. */
  estimated: boolean;
}

export interface ExpiryRadar {
  key: IndexKey;
  label: string;
  /** Weekly first, then monthly; one row when the two coincide. */
  rows: ExpiryMarker[];
  /** BANK NIFTY has no weekly series. Stated outright, because an empty slot
      reads as a feed that failed rather than as a contract that does not
      exist. */
  weeklyRetired: boolean;
  /** Any row in `rows` is estimated. */
  estimated: boolean;
}

interface ExpiryRule {
  /** `Date.getUTCDay()`: Sunday 0 … Saturday 6. */
  weekday: number;
  /** False for an index whose weekly series has been retired. */
  weekly: boolean;
}

const TUESDAY = 2;
const THURSDAY = 4;

/**
 * The settlement weekday per index, as the exchanges currently publish it.
 *
 * NSE moved its weekly expiry to Tuesday and withdrew BANK NIFTY's weeklies,
 * leaving it monthly-only on the last Tuesday; BSE settles SENSEX on Thursday.
 * Only the *monthly* rule applies to BANK NIFTY, which is why `weekday` is
 * still meaningful for it.
 */
const RULES: Record<IndexKey, ExpiryRule> = {
  NIFTY50: { weekday: TUESDAY, weekly: true },
  SENSEX: { weekday: THURSDAY, weekly: true },
  BANKNIFTY: { weekday: TUESDAY, weekly: false }
};

const DAY_MS = 86_400_000;

/**
 * An ISO date as a UTC-midnight epoch.
 *
 * Parsed as UTC rather than local on purpose: these are IST calendar dates, and
 * a viewer in New York parsing `2026-10-28` as local midnight lands on the 27th
 * in UTC, which shifts every day count by one for half the world.
 */
function epochOf(iso: string): number {
  return Date.parse(`${iso}T00:00:00Z`);
}

function isoOf(epoch: number): string {
  return new Date(epoch).toISOString().slice(0, 10);
}

/** Whole calendar days from `from` to `to`; negative when `to` has passed. */
export function daysBetween(from: string, to: string): number {
  return Math.round((epochOf(to) - epochOf(from)) / DAY_MS);
}

export function urgencyFor(daysAway: number): ExpiryUrgency {
  if (daysAway <= 0) return 'today';
  if (daysAway === 1) return 'tomorrow';
  if (daysAway <= 3) return 'near';
  return 'distant';
}

/** The next `weekday` on or after `from`. */
function nextWeekday(from: string, weekday: number): string {
  const start = epochOf(from);
  const ahead = (weekday - new Date(start).getUTCDay() + 7) % 7;
  return isoOf(start + ahead * DAY_MS);
}

/** The last `weekday` of the calendar month `iso` falls in. */
function lastWeekdayOfMonth(iso: string, weekday: number): string {
  const probe = new Date(epochOf(iso));
  // Day 0 of the following month is the last day of this one.
  const last = Date.UTC(probe.getUTCFullYear(), probe.getUTCMonth() + 1, 0);
  const back = (new Date(last).getUTCDay() - weekday + 7) % 7;
  return isoOf(last - back * DAY_MS);
}

/** The first day of the month after the one `iso` falls in. */
function startOfNextMonth(iso: string): string {
  const probe = new Date(epochOf(iso));
  return isoOf(Date.UTC(probe.getUTCFullYear(), probe.getUTCMonth() + 1, 1));
}

/** The next weekly settlement on or after `today`, by rule. */
export function nextWeeklyFromRules(key: IndexKey, today: string): string | undefined {
  const rule = RULES[key];
  if (!rule.weekly) return undefined;
  return nextWeekday(today, rule.weekday);
}

/**
 * The next monthly settlement on or after `today`, by rule.
 *
 * Rolls to the following month once this month's has passed — on the 29th of a
 * month whose last Tuesday was the 27th, the answer is November's, not a date
 * two days behind.
 */
export function monthlyFromRules(key: IndexKey, today: string): string {
  const { weekday } = RULES[key];
  const thisMonth = lastWeekdayOfMonth(today, weekday);
  if (daysBetween(today, thisMonth) >= 0) return thisMonth;
  return lastWeekdayOfMonth(startOfNextMonth(today), weekday);
}

interface Classified {
  weekly?: string | undefined;
  monthly?: string | undefined;
}

/**
 * Weekly and monthly, read off the broker's own list.
 *
 * The monthly expiry is the last listed date inside its calendar month. Two
 * guards keep that inference honest:
 *
 * * **The list is capped at 42 days** by the backend, so a month's tail can be
 *   truncated — and the last date of a truncated month is merely the last one
 *   that fitted, not the monthly. A date is only called monthly when the list
 *   reaches past that month's end and so demonstrably contains its tail.
 * * **Settled dates are dropped first.** A cached list served after an expiry
 *   would otherwise present a contract that no longer trades as the next one.
 */
export function classifyListed(expiries: readonly string[], today: string): Classified {
  const upcoming = expiries
    .filter((iso) => /^\d{4}-\d{2}-\d{2}$/.test(iso) && daysBetween(today, iso) >= 0)
    .sort();
  if (upcoming.length === 0) return {};

  const nearest = upcoming[0]!;
  const furthest = upcoming[upcoming.length - 1]!;
  const nextMonth = startOfNextMonth(nearest);

  // The last date still inside the nearest expiry's month.
  const sameMonth = upcoming.filter((iso) => iso < nextMonth);
  const tailVisible = furthest >= nextMonth;
  const monthly = tailVisible ? sameMonth[sameMonth.length - 1] : undefined;

  // The nearest date that is not the monthly. When the monthly *is* the
  // nearest, there is no separate weekly left in the month and the caller
  // collapses the two into one row.
  const weekly = upcoming.find((iso) => iso !== monthly);

  return { weekly, monthly };
}

/**
 * One index's radar, from the broker's list where it can be trusted.
 *
 * The mock arm is the reason this function is not simply `classifyListed`: a
 * synthetic list is a plausible-looking lie about the one fact this card
 * exists to state, so it is refused in favour of the published schedule, and
 * the result is flagged so the card can say which it is showing.
 */
export function radarFor(
  key: IndexKey,
  label: string,
  listed: readonly string[] | undefined,
  provenance: Provenance | undefined,
  today: string = isoDateIST()
): ExpiryRadar {
  const rule = RULES[key];
  const trusted = provenance != null && provenance.source !== 'mock';
  const classified = trusted && listed ? classifyListed(listed, today) : {};

  // Each side falls back independently: a list can carry a believable weekly
  // while its month's tail sits past the horizon, and halving the card because
  // of that would discard a date the broker did publish.
  const weeklyDate = rule.weekly
    ? (classified.weekly ?? nextWeeklyFromRules(key, today))
    : undefined;
  const monthlyDate = classified.monthly ?? monthlyFromRules(key, today);

  const weeklyEstimated = classified.weekly == null;
  const monthlyEstimated = classified.monthly == null;

  const marker = (kind: ExpiryKind, date: string, estimated: boolean): ExpiryMarker => {
    const daysAway = Math.max(0, daysBetween(today, date));
    return { kind, date, daysAway, urgency: urgencyFor(daysAway), estimated };
  };

  const rows: ExpiryMarker[] = [];
  if (weeklyDate != null && weeklyDate === monthlyDate) {
    rows.push(marker('both', weeklyDate, weeklyEstimated && monthlyEstimated));
  } else {
    if (weeklyDate != null) rows.push(marker('weekly', weeklyDate, weeklyEstimated));
    rows.push(marker('monthly', monthlyDate, monthlyEstimated));
  }

  return {
    key,
    label,
    rows,
    weeklyRetired: !rule.weekly,
    estimated: rows.some((row) => row.estimated)
  };
}

const DATE_LABEL = new Intl.DateTimeFormat('en-GB', {
  timeZone: 'UTC',
  weekday: 'short',
  day: 'numeric',
  month: 'short'
});

/** `Tue 28 Oct` — formatted in UTC because the ISO date is already IST. */
export function expiryDateLabel(iso: string): string {
  return DATE_LABEL.format(epochOf(iso));
}

/** `TODAY` / `TOMORROW` / `3 days`. */
export function countdownLabel(daysAway: number): string {
  if (daysAway <= 0) return 'TODAY';
  if (daysAway === 1) return 'TOMORROW';
  return `${daysAway} days`;
}

/** `Weekly` / `Monthly` / `Weekly + Monthly`, for display and for prose. */
export function kindLabel(kind: ExpiryKind): string {
  if (kind === 'both') return 'Weekly + Monthly';
  return kind === 'weekly' ? 'Weekly' : 'Monthly';
}

/**
 * The row a reader needs to see first, or none.
 *
 * Used by the spot card's corner marker and by the alert, both of which have
 * room for exactly one. Soonest wins; a tie goes to the weekly, which is the
 * contract most positions are actually in.
 */
export function leadMarker(radar: ExpiryRadar): ExpiryMarker | undefined {
  return radar.rows.reduce<ExpiryMarker | undefined>((best, row) => {
    if (!best || row.daysAway < best.daysAway) return row;
    return best;
  }, undefined);
}

/**
 * The radars worth interrupting a reader over, soonest first.
 *
 * Only `today` and `tomorrow` qualify. A banner that fired three days out
 * would be on screen most of the week and would stop being read.
 */
export function alertable(
  radars: readonly ExpiryRadar[]
): { radar: ExpiryRadar; marker: ExpiryMarker }[] {
  return radars
    .flatMap((radar) =>
      radar.rows
        .filter((marker) => marker.urgency === 'today' || marker.urgency === 'tomorrow')
        .map((marker) => ({ radar, marker }))
    )
    .sort((a, b) => a.marker.daysAway - b.marker.daysAway);
}
