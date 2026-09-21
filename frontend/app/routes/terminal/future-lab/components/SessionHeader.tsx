import { useEffect, useState, type CSSProperties } from 'react';
import { cx } from '$shared/ui/cx';
import IconClock from '$shared/ui/icons/IconClock';
import { clockLabel } from '../heatmap-data';
import s from './SessionHeader.module.css';

/**
 * The three pieces of header furniture the Future Lab pages share: the
 * exchange clock, the refresh countdown ring, and the replay switch.
 *
 * Extracted from the heatmap page once Price vs OI needed the same three. They
 * live together because they are one visual group at the top-right of every
 * page in the section, and three separate files would drift apart.
 */

/** The exchange-local wall clock. */
export function SessionClock({ now }: { now?: Date }) {
  const [tick, setTick] = useState(() => new Date());
  useEffect(() => {
    if (now) return;
    const timer = setInterval(() => setTick(new Date()), 1000);
    return () => clearInterval(timer);
  }, [now]);

  return (
    <span className={s.clock}>
      <span aria-hidden="true" className={s.clockIco}>
        <IconClock />
      </span>
      {clockLabel(now ?? tick)}
    </span>
  );
}

/**
 * Seconds until the next poll.
 *
 * A board that silently reloads looks static; the ring is what tells you the
 * numbers are on a clock rather than frozen. Paused rather than hidden when
 * the page is not polling, so the control does not shift about.
 */
export function RefreshRing({ seconds, active }: { seconds: number; active: boolean }) {
  const [left, setLeft] = useState(seconds);

  useEffect(() => {
    if (!active) {
      setLeft(seconds);
      return;
    }
    const timer = setInterval(() => setLeft((prev) => (prev <= 1 ? seconds : prev - 1)), 1000);
    return () => clearInterval(timer);
  }, [active, seconds]);

  const progress = ((seconds - left) / seconds) * 100;

  return (
    <span
      className={s.countdown}
      style={{ '--mc-progress': `${progress}%` } as CSSProperties}
      title={active ? `Refreshes every ${seconds}s` : 'Not refreshing'}
    >
      {left}
    </span>
  );
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
