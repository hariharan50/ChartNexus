import Button from '$shared/ui/Button';
import { formatSessionDate } from '../trade-buddy-data';
import s from './StaleBanner.module.css';

/**
 * Stale levels, and the two ways out of it.
 *
 * This is the one state in which a quiet phone is correct behaviour rather
 * than a fault: the marks belong to an earlier session, so nothing is being
 * compared against them and nothing will be sent. The old banner said exactly
 * that and stopped, which left the reader to work out that the fix was to
 * retype six numbers they had not changed their mind about.
 *
 * So the fix is here, as two buttons that mean different things. "Carry
 * forward" re-saves the same marks against today's session — the common case,
 * because yesterday's pivots are often still the levels you care about, and it
 * needs no backend change since saving always stamps the current session.
 * "Re-mark" clears the form and puts the cursor in it, for the morning when
 * the numbers really have moved.
 *
 * Amber rather than red. Red is for something broken; this is recoverable in
 * one click, and a page that shouts the same way about both teaches the reader
 * to discount the shout.
 */
interface Props {
  symbol: string;
  markedOn: string | null | undefined;
  onCarryForward: () => void;
  onRemark: () => void;
  carrying: boolean;
  /** False when there are no marks to carry — then re-marking is the only way. */
  canCarry: boolean;
}

export default function StaleBanner({
  symbol,
  markedOn,
  onCarryForward,
  onRemark,
  carrying,
  canCarry
}: Props) {
  return (
    <section className={s.banner} role="status" aria-label="Stale levels">
      <svg className={s.icon} viewBox="0 0 24 24" aria-hidden="true">
        <path
          d="M12 3.8 2.6 20h18.8L12 3.8Z"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinejoin="round"
        />
        <path d="M12 9.5v4.4" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
        <circle cx="12" cy="16.9" r="1.05" fill="currentColor" />
      </svg>

      <div className={s.body}>
        <p className={s.title}>
          These {symbol} levels are from {formatSessionDate(markedOn)}
        </p>
        <p className={s.detail}>No alerts fire for {symbol} until you confirm levels for today.</p>
      </div>

      <div className={s.actions}>
        <Button onClick={onCarryForward} loading={carrying} disabled={!canCarry}>
          Carry forward to today
        </Button>
        <Button variant="ghost" onClick={onRemark}>
          Re-mark levels
        </Button>
      </div>
    </section>
  );
}
