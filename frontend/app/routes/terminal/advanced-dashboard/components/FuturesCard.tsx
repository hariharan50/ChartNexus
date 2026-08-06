import { direction, formatInt, formatPrice, formatSignedPercent } from '$shared/formatting/numbers';
import { cx } from '$shared/ui/cx';
import s from './FuturesCard.module.css';

interface Props {
  label: string;
  /** Future last price; undefined renders a pending zero. */
  value?: number | undefined;
  changePercent?: number | undefined;
  volume?: number | undefined;
  contract?: string | undefined;
  dayHigh?: number | undefined;
  dayLow?: number | undefined;
}

const dash = (v: number | undefined) => (v != null ? formatPrice(v) : '—');

export default function FuturesCard({
  label,
  value,
  changePercent,
  volume,
  contract,
  dayHigh,
  dayLow
}: Props) {
  const dir = changePercent !== undefined ? direction(changePercent) : 'flat';

  return (
    <div className={s.card}>
      <div className={s.head}>
        <span className={s.label}>{label}</span>
        <span className={s.tag}>FUT</span>
      </div>

      <span className={cx(s.value, 'mc-numeric')}>
        {value != null ? formatPrice(value) : '0.00'}
      </span>
      <span className={cx(s.pill, s[dir])}>{formatSignedPercent(changePercent ?? 0)}</span>

      <div className={s.grid}>
        <div className={s.cell}>
          <span className={s.k}>Volume</span>
          <span className={cx(s.v, 'mc-numeric')}>{volume != null ? formatInt(volume) : '0'}</span>
        </div>
        <div className={s.cell}>
          <span className={s.k}>Contract</span>
          <span className={cx(s.v, s.contract)}>{contract ?? '—'}</span>
        </div>
        <div className={s.cell}>
          <span className={s.k}>Day High</span>
          <span className={cx(s.v, 'mc-numeric')}>{dash(dayHigh)}</span>
        </div>
        <div className={s.cell}>
          <span className={s.k}>Day Low</span>
          <span className={cx(s.v, 'mc-numeric')}>{dash(dayLow)}</span>
        </div>
      </div>

      <span className={s.accent} aria-hidden="true" />
    </div>
  );
}
