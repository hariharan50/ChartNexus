import { cx } from '$shared/ui/cx';
import s from './BarPair.module.css';

interface Props {
  callValue: number;
  putValue: number;
  callLabel: string;
  putLabel: string;
}

export default function BarPair({ callValue, putValue, callLabel, putLabel }: Props) {
  // Heights normalise to the larger magnitude so the taller bar fills the box.
  const max = Math.max(1, Math.abs(callValue), Math.abs(putValue));
  const callH = `${(Math.abs(callValue) / max) * 100}%`;
  const putH = `${(Math.abs(putValue) / max) * 100}%`;

  return (
    <div className={s.pair}>
      <div className={s.col}>
        <span className={cx(s.val, s.call)}>{callLabel}</span>
        <div className={s.track}>
          <div className={cx(s.bar, s.call)} style={{ height: callH }} />
        </div>
        <span className={s.k}>CALL</span>
      </div>
      <div className={s.col}>
        <span className={cx(s.val, s.put)}>{putLabel}</span>
        <div className={s.track}>
          <div className={cx(s.bar, s.put)} style={{ height: putH }} />
        </div>
        <span className={s.k}>PUT</span>
      </div>
    </div>
  );
}
