import type { CSSProperties } from 'react';
import { cx } from './cx';
import s from './Skeleton.module.css';

interface Props {
  /** Any CSS length. Defaults to the full width of its container. */
  width?: string | number | undefined;
  /** Any CSS length. Size it to the content it stands in for, so nothing
   *  shifts when the data lands. */
  height?: string | number | undefined;
  /** `text` matches one line of body copy; `circle` an avatar or dot. */
  shape?: 'block' | 'text' | 'circle' | undefined;
  className?: string | undefined;
  style?: CSSProperties | undefined;
}

/**
 * A loading placeholder: a soft background pulse (the global `cn-skeleton`
 * keyframe), sized to the content it stands in for so the swap to real data
 * costs zero layout shift.
 *
 * Decorative only — pair it with an `aria-busy` region or a visually hidden
 * "Loading…" so assistive tech still hears that something is coming.
 */
export function Skeleton({ width, height, shape = 'block', className, style }: Props) {
  return (
    <span
      aria-hidden="true"
      className={cx('cn-skeleton', s.skeleton, s[shape], className)}
      style={{ width, height, ...style }}
    />
  );
}

/** `count` stacked rows — the common "table loading" case. */
export function SkeletonRows({
  count,
  height = '2.25rem',
  gap = 'var(--cn-space-2)',
  className
}: {
  count: number;
  height?: string | undefined;
  gap?: string | undefined;
  className?: string | undefined;
}) {
  return (
    <div aria-hidden="true" className={cx(s.rows, className)} style={{ gap }}>
      {Array.from({ length: count }, (_, i) => (
        <Skeleton key={i} height={height} />
      ))}
    </div>
  );
}

export default Skeleton;
