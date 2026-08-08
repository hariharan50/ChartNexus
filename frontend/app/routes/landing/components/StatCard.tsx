import { cx } from '$shared/ui/cx';
import s from './StatCard.module.css';

interface Props {
  label: string;
  value: string;
}

/**
 * The small orange-tinted cards that overlap the hero graphic.
 *
 * Decorative framing for a figure that is already true elsewhere on the page —
 * they never carry a number the product cannot back up.
 */
export default function StatCard({ label, value }: Props) {
  return (
    <div className={s.card}>
      <span className={s.label}>{label}</span>
      <span className={cx(s.value, 'mc-numeric')}>{value}</span>
    </div>
  );
}
