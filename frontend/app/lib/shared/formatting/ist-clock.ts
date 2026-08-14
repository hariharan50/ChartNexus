/**
 * The exchange clock, read in `Asia/Kolkata`.
 *
 * Session boundaries are IST wall-clock facts, so every reading of "what time
 * is it for the market" goes through here rather than through the viewer's
 * locale or a server timestamp. Two consequences worth keeping:
 *
 * * A viewer outside India sees the exchange's clock, not their own.
 * * It does not depend on the API being reachable or up to date. The market
 *   status endpoint carries a `time_ist`, but a badge that freezes when a
 *   request fails is worse than one the browser can always answer.
 */

const HMS = new Intl.DateTimeFormat('en-GB', {
  timeZone: 'Asia/Kolkata',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
  hourCycle: 'h23'
});

const PARTS = new Intl.DateTimeFormat('en-GB', {
  timeZone: 'Asia/Kolkata',
  weekday: 'short',
  hour: '2-digit',
  minute: '2-digit',
  hourCycle: 'h23'
});

/** `23:06:28` — IST, 24-hour, seconds included so it visibly ticks. */
export function istTimeLabel(at: number): string {
  return HMS.format(at);
}

export interface IstClock {
  /** Minutes past IST midnight. */
  minutes: number;
  weekend: boolean;
}

export function istClock(at: number): IstClock {
  const parts = PARTS.formatToParts(at);
  const part = (type: Intl.DateTimeFormatPartTypes) =>
    parts.find((candidate) => candidate.type === type)?.value ?? '';
  const weekday = part('weekday');
  return {
    minutes: Number(part('hour')) * 60 + Number(part('minute')),
    weekend: weekday === 'Sat' || weekday === 'Sun'
  };
}

/**
 * 09:15 to 15:40 IST — the window derivatives actually trade in.
 *
 * Exported, and the only copy: these were duplicated privately in the chart
 * modules, and when the close moved from 15:30 to 15:40 (the F&O extension
 * effective 3 August 2026) those copies were left behind. Every capture after
 * 15:30 then clamped onto the same axis position, which stacked ten minutes of
 * readings into a single hover — see `axisX` in charts/options/multi-series.
 */
export const SESSION_OPEN_MIN = 9 * 60 + 15;
export const SESSION_CLOSE_MIN = 15 * 60 + 40;
/** Length of the session in minutes — 385. */
export const SESSION_MINUTES = SESSION_CLOSE_MIN - SESSION_OPEN_MIN;

/**
 * Whether the exchange is trading right now.
 *
 * Used to decide when a series that has stopped growing is a *fault* rather
 * than simply the end of the day. Outside these hours the newest snapshot is
 * meant to age, and warning about it would be noise every evening.
 */
export function isTradingWindow(at: number): boolean {
  const { minutes, weekend } = istClock(at);
  return !weekend && minutes >= SESSION_OPEN_MIN && minutes < SESSION_CLOSE_MIN;
}

/** IST is a fixed UTC+5:30; a Date's epoch is UTC, so shift then read getUTC*. */
const IST_OFFSET_MS = 5.5 * 60 * 60 * 1000;

/**
 * An IST calendar date as `YYYY-MM-DD`, `offsetDays` from today.
 *
 * The value a `<input type="date">` reads and writes. Computed off the IST clock
 * so a viewer past midnight UTC but before it in India still gets India's date.
 */
export function isoDateIST(offsetDays = 0, now: number = Date.now()): string {
  return new Date(now + IST_OFFSET_MS + offsetDays * 86_400_000).toISOString().slice(0, 10);
}

/**
 * The most recent weekday on or before today, IST, as `YYYY-MM-DD`.
 *
 * A sensible default for the Historical date picker: on a Monday it lands on the
 * previous Friday rather than an empty weekend session.
 */
export function lastTradingDayIST(now: number = Date.now()): string {
  let offset = -1;
  for (let i = 0; i < 3; i++) {
    const { weekend } = istClock(now + offset * 86_400_000);
    if (!weekend) break;
    offset -= 1;
  }
  return isoDateIST(offset, now);
}
