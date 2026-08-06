import { useEffect, useState } from 'react';
import { istClock, type IstClock } from '$shared/formatting/ist-clock';
import { cx } from '$shared/ui/cx';
import s from './MarketPhase.module.css';

/**
 * Which NSE session phase the exchange is in right now.
 *
 * Boundaries are the timings effective 3 August 2026: the closing auction takes
 * F&O-eligible cash stocks out of continuous trading at 15:15, and equity
 * derivatives run ten minutes past the 15:30 cash close to 15:40.
 */

type Tone = 'open' | 'pre' | 'auction' | 'closed';

interface Phase {
  label: string;
  window: string;
  tone: Tone;
}

/** Minutes past IST midnight. */
const PRE_OPEN_ENTRY = 9 * 60; // 09:00
const PRE_OPEN_MATCH = 9 * 60 + 7; // 09:07
const OPEN = 9 * 60 + 15; // 09:15
const AUCTION = 15 * 60 + 15; // 15:15 — continuous trading freezes
const AUCTION_END = 15 * 60 + 35; // 15:35 — closing price discovered
const FNO_CLOSE = 15 * 60 + 40; // 15:40 — derivatives close

const CLOSED: Phase = { label: 'Market closed', window: 'Opens 9:00 am', tone: 'closed' };

function phaseAt(minutes: number, weekend: boolean): Phase {
  if (weekend) return { label: 'Market closed', window: 'Weekend', tone: 'closed' };
  if (minutes < PRE_OPEN_ENTRY) return CLOSED;
  if (minutes < PRE_OPEN_MATCH) {
    return { label: 'Pre-open · order entry', window: '9:00 – 9:07 am', tone: 'pre' };
  }
  if (minutes < OPEN) {
    return { label: 'Pre-open · matching', window: '9:07 – 9:15 am', tone: 'pre' };
  }
  if (minutes < AUCTION) {
    return { label: 'Market open', window: '9:15 am – 3:15 pm', tone: 'open' };
  }
  if (minutes < AUCTION_END) {
    return { label: 'Closing auction (CAS)', window: '3:15 – 3:35 pm', tone: 'auction' };
  }
  if (minutes < FNO_CLOSE) {
    return { label: 'F&O extended close', window: '3:35 – 3:40 pm', tone: 'auction' };
  }
  return { label: 'Market closed', window: 'F&O closed 3:40 pm', tone: 'closed' };
}

const TONE: Record<Tone, string | undefined> = {
  open: s.toneOpen,
  pre: s.tonePre,
  auction: s.toneAuction,
  closed: s.toneClosed
};

export default function MarketPhase() {
  const [clock, setClock] = useState<IstClock>(() => istClock(Date.now()));

  useEffect(() => {
    // Ticks every second so a boundary is never more than a second stale, but
    // returns the previous object when the minute has not turned — React bails
    // out of the re-render, so this costs one comparison a second.
    const timer = window.setInterval(() => {
      const next = istClock(Date.now());
      setClock((prev) =>
        prev.minutes === next.minutes && prev.weekend === next.weekend ? prev : next
      );
    }, 1000);
    return () => window.clearInterval(timer);
  }, []);

  const phase = phaseAt(clock.minutes, clock.weekend);

  return (
    <div className={cx(s.strip, TONE[phase.tone])} role="status">
      <span className={s.dot} aria-hidden="true" />
      <span className={s.label}>{phase.label}</span>
      <span className={s.window}>{phase.window}</span>
    </div>
  );
}
