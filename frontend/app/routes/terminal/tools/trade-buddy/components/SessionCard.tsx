import { cx } from '$shared/ui/cx';
import {
  FEED_COPY,
  formatTime,
  secondsSince,
  type EngineState,
  type FeedVerdict
} from '../trade-buddy-data';
import s from './SessionCard.module.css';

/**
 * Is the watch actually running? The page's first sentence.
 *
 * Silence from a dead watcher and silence from a quiet market look identical
 * from the outside — that is the premise the whole feature rests on — so this
 * sits beside the title rather than below the fold, and states the verdict in
 * words. The dot only tints it: the status survives greyscale, colour-vision
 * deficiency and forced-colours because the label is always there.
 *
 * When live, the detail line becomes the tick age instead of the generic
 * reassurance. "Ticks are arriving" is worth saying once; after that the
 * useful form is "last tick 3s ago", which is the number that turns into a
 * warning on its own as it grows.
 */
interface Props {
  verdict: FeedVerdict;
  state: EngineState | undefined;
  /** Re-rendered every second by the page, so the age ages. */
  now: number;
}

export default function SessionCard({ verdict, state, now }: Props) {
  const silence = secondsSince(state?.last_tick_at ?? null, now);
  const detail =
    verdict === 'live' && state?.last_tick_at
      ? `Last tick ${formatTime(state.last_tick_at)} IST${silence !== null ? ` · ${silence}s ago` : ''}`
      : FEED_COPY[verdict].detail;

  return (
    <section className={cx(s.card, s[`is_${verdict}`])} aria-label="Watcher status">
      <span className={s.dot} aria-hidden="true" />
      <div className={s.body}>
        <p className={s.label}>{FEED_COPY[verdict].label}</p>
        <p className={s.detail}>{detail}</p>
      </div>
    </section>
  );
}
