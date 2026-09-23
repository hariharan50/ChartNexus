import { useEffect, useState } from 'react';
import { cx } from '$shared/ui/cx';
import { sessionClockLabel } from '../heatmap-data';
import s from './SessionHeader.module.css';

/**
 * The header furniture the Future Lab pages share: the live status strip and
 * the replay switch.
 *
 * They live together because they are one visual group at the top-right of
 * every page in the section, and separate files would drift apart.
 */

interface StatusProps {
  /** Poll interval, printed as "15s". */
  intervalSeconds: number;
  /** Whether the page is actually polling. A paused page says so. */
  active: boolean;
  /**
   * When the data on screen arrived — react-query's `dataUpdatedAt`.
   * `undefined` or 0 means nothing has landed yet.
   */
  updatedAt?: number | undefined;
  /** Replaces the live clock, e.g. "Archived · 2026-09-22". */
  label?: string | undefined;
}

/**
 * Whether what you are looking at is current, in words.
 *
 * Replaces the countdown ring this section used to carry. A ring answers
 * "how long until the next poll", which is the one question a reader does not
 * have; the questions they do have are *when was this taken* and *is it still
 * arriving*, and neither is answerable from a shrinking arc. So: a live dot,
 * the exchange clock, the cadence, and how old the numbers on screen actually
 * are.
 *
 * **The age is of the data, not of the request.** It is measured from the
 * moment the payload landed, so a poll that fails leaves the figure climbing —
 * which is exactly the signal a frozen board should give and the ring never
 * did, because it kept sweeping regardless.
 */
export function SessionStatus({ intervalSeconds, active, updatedAt, label }: StatusProps) {
  const [tick, setTick] = useState(() => Date.now());

  useEffect(() => {
    // One timer drives both the clock and the age; they are read together and
    // must never disagree by a second.
    const timer = setInterval(() => setTick(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);

  const age = updatedAt ? tick - updatedAt : null;
  const stale = age !== null && age > intervalSeconds * 1000 * STALE_INTERVALS;

  return (
    <span
      className={cx(s.status, stale && s.stale)}
      title={active ? `Refreshes every ${intervalSeconds}s` : 'Not refreshing'}
    >
      <span className={cx(s.dot, active && s.pulse, stale && s.dotStale)} aria-hidden="true" />
      <span>{label ?? sessionClockLabel(new Date(tick))}</span>
      <span className={s.interval}>{cadenceLabel(intervalSeconds)}</span>
      <span className={s.age}>{age === null ? 'no data yet' : `updated ${agoLabel(age)}`}</span>
    </span>
  );
}

/**
 * How many poll intervals may pass before the reading counts as stale.
 *
 * Two, not one: a single missed beat is ordinary jitter — a slow response, a
 * backgrounded tab — and colouring the strip red for it would teach the reader
 * to ignore red.
 */
const STALE_INTERVALS = 2;

/**
 * `15s`, `5m` — the poll cadence.
 *
 * Rolled into minutes past sixty seconds: the FII/DII pages poll every five
 * minutes, and "300s" is a number the reader has to divide before it means
 * anything.
 */
function cadenceLabel(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.round(seconds / 60);
  return `${minutes}m`;
}

/** `5s ago`, `2m ago`, `1h 12m ago`. */
function agoLabel(ageMs: number): string {
  const seconds = Math.max(Math.floor(ageMs / 1000), 0);
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  return `${Math.floor(minutes / 60)}h ${minutes % 60}m ago`;
}

/**
 * The replay switch.
 *
 * `disabled` with a `reason` is a real state, not a placeholder: a page whose
 * history is not captured still shows the control so the gap reads as a
 * roadmap item rather than a missing feature.
 */
export function ReplayToggle({
  on,
  onToggle,
  disabled,
  reason
}: {
  on: boolean;
  onToggle?: (() => void) | undefined;
  disabled?: boolean | undefined;
  reason?: string | undefined;
}) {
  return (
    <button
      type="button"
      className={cx(s.replay, on && s.on)}
      aria-pressed={on}
      disabled={disabled ?? false}
      title={reason ?? undefined}
      onClick={() => onToggle?.()}
    >
      Replay
      <span className={s.switch} aria-hidden="true" />
    </button>
  );
}
