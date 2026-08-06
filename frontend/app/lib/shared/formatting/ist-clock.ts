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
