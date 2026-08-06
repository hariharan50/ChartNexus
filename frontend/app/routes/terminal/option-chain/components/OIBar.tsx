import { cx } from '$shared/ui/cx';
import type { Side } from '../chain-model';
import s from './OIBar.module.css';

interface Props {
  value?: number | undefined;
  max: number;
  side: Side;
  /**
   * Applied to the track.
   *
   * The page tints the bar per column with `td.ce.oi :global(.track)` in Svelte;
   * CSS Modules hashes that class, so the override comes in through here.
   */
  className?: string | undefined;
}

export default function OIBar({ value, max, side, className }: Props) {
  // Calls fill from the right (reading inward toward the strike), puts from the
  // left. Clamp so a rounding overshoot never spills past the track.
  const pct = value != null && max > 0 ? Math.min(100, (value / max) * 100) : 0;

  return (
    <span className={cx(s.track, className)}>
      <span className={cx(s.fill, s[side])} style={{ width: `${pct}%` }} />
    </span>
  );
}
