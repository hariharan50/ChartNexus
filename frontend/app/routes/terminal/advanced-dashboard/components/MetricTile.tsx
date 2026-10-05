import { cx } from '$shared/ui/cx';
import s from './MetricTile.module.css';

interface Props {
  label: string;
  value: string;
  tone?: 'default' | 'bullish' | 'bearish' | 'warning' | 'accent';
}

export default function MetricTile({ label, value, tone = 'default' }: Props) {
  return (
    <div className={s.tile}>
      <span className={s.label}>{label}</span>
      <span className={cx(s.value, 'cn-numeric', s[tone])}>{value}</span>
    </div>
  );
}
