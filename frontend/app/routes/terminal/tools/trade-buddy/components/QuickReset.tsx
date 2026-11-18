import { useEffect, useRef, useState } from 'react';
import { cx } from '$shared/ui/cx';
import s from './QuickReset.module.css';

/**
 * Quick Reset: clear today's levels and today's alerts for one index, then
 * go straight back to marking new levels.
 *
 * Two clicks, not one. It deletes the day's alert history, which cannot be
 * rebuilt, and it sits a few hundred pixels from Save. The second click is on
 * a button that says exactly what will happen, so it confirms by reading
 * rather than by a modal that hides the levels you were about to replace.
 * An unanswered confirm backs out on its own, and Escape backs out at once.
 */
interface Props {
  symbol: string;
  resetting: boolean;
  onReset: () => void;
}

/** How long the confirm step waits before backing out by itself. */
const CONFIRM_MS = 6_000;

export default function QuickReset({ symbol, resetting, onReset }: Props) {
  const [confirming, setConfirming] = useState(false);
  const confirmRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!confirming) return;
    confirmRef.current?.focus();
    const id = setTimeout(() => setConfirming(false), CONFIRM_MS);
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setConfirming(false);
    };
    window.addEventListener('keydown', onKey);
    return () => {
      clearTimeout(id);
      window.removeEventListener('keydown', onKey);
    };
  }, [confirming]);

  // Switching index mid-confirm must not carry the confirm to the other one.
  useEffect(() => setConfirming(false), [symbol]);

  if (!confirming) {
    return (
      <button
        type="button"
        className={s.reset}
        onClick={() => setConfirming(true)}
        disabled={resetting}
        aria-busy={resetting}
        title={`Clear ${symbol}'s levels and today's alerts`}
      >
        <svg className={s.icon} viewBox="0 0 24 24" aria-hidden="true">
          <path
            d="M3 12a9 9 0 1 0 3-6.7M3 4v5h5"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
        {resetting ? 'Resetting…' : 'Quick Reset'}
      </button>
    );
  }

  return (
    <span className={s.confirm} role="group" aria-label="Confirm Quick Reset">
      <span className={s.question}>Clear {symbol} levels and today&apos;s alerts?</span>
      <button
        ref={confirmRef}
        type="button"
        className={cx(s.reset, s.solid)}
        onClick={() => {
          setConfirming(false);
          onReset();
        }}
      >
        Yes, reset {symbol}
      </button>
      <button type="button" className={s.cancel} onClick={() => setConfirming(false)}>
        Cancel
      </button>
    </span>
  );
}
