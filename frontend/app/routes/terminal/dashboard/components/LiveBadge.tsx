import { cx } from '$shared/ui/cx';
import s from './LiveBadge.module.css';

interface Props {
  /** Local clock string, e.g. "10:46:46 IST". */
  time: string;
  live?: boolean;
}

export default function LiveBadge({ time, live = true }: Props) {
  return (
    <span className={cx(s.badge, live && s.live)}>
      <span className={s.dot} aria-hidden="true" />
      {live ? 'Live' : 'Delayed'} — {time}
    </span>
  );
}
