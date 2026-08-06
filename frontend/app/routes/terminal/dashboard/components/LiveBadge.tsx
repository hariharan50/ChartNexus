import { useEffect, useState } from 'react';
import { istTimeLabel } from '$shared/formatting/ist-clock';
import { cx } from '$shared/ui/cx';
import s from './LiveBadge.module.css';

interface Props {
  live?: boolean;
}

/**
 * Session state, with a live IST clock.
 *
 * The clock ticks from the browser rather than echoing `MarketStatus.time_ist`:
 * that field only advances when the 15s status poll returns, so it visibly
 * stalls, and it goes stale entirely if the API is unreachable or serving an
 * older build. `live` still comes from the backend — whether the exchange is
 * open is a server fact, unlike what time it is.
 */
export default function LiveBadge({ live = true }: Props) {
  const [time, setTime] = useState(() => istTimeLabel(Date.now()));

  useEffect(() => {
    const timer = window.setInterval(() => setTime(istTimeLabel(Date.now())), 1000);
    return () => window.clearInterval(timer);
  }, []);

  return (
    <span className={cx(s.badge, live && s.live)}>
      <span className={s.dot} aria-hidden="true" />
      {live ? 'Live' : 'Delayed'} — {time} IST
    </span>
  );
}
