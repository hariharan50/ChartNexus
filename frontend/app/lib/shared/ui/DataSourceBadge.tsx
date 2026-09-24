import type { DataSourceName } from '$contexts/broker-connections/types';
import { cx } from './cx';
import s from './DataSourceBadge.module.css';

/**
 * States where a number came from.
 *
 * A "connected" indicator elsewhere must not be read as "this price is live" —
 * a cached or simulated figure looks identical on a chart, and only this badge
 * distinguishes them.
 */

interface Props {
  source: DataSourceName;
  ageSeconds?: number | undefined;
  compact?: boolean | undefined;
  /**
   * Drop the pill — just the dot and the coloured word.
   *
   * For places where the badge sits alone in a panel and the enclosing card is
   * already doing the framing, so the pill reads as an empty box around two
   * words. The colour still carries the whole meaning, which is the only part
   * that matters.
   */
  plain?: boolean | undefined;
}

const LABELS: Record<string, string> = { live: 'Live', cached: 'Cached', mock: 'Simulated' };

export default function DataSourceBadge({
  source,
  ageSeconds = 0,
  compact = false,
  plain = false
}: Props) {
  const label = LABELS[source] ?? source;
  const detail =
    source === 'live' ? '' : source === 'cached' ? formatAge(ageSeconds) : 'not real data';

  return (
    <span
      className={cx(s.badge, s[source], compact && s.compact, plain && s.plain)}
      title={detail || undefined}
    >
      <span className={s.dot} aria-hidden="true" />
      {label}
      {detail && !compact ? <span className={s.detail}>· {detail}</span> : null}
    </span>
  );
}

function formatAge(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)}s old`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m old`;
  return `${Math.round(seconds / 3600)}h old`;
}
