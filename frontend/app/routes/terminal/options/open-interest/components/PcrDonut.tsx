import { cx } from '$shared/ui/cx';
import s from './PcrDonut.module.css';

interface Props {
  pcr: number;
  callNow: number;
  putNow: number;
}

const R = 58;
const CIRC = 2 * Math.PI * R;

export default function PcrDonut({ pcr, callNow, putNow }: Props) {
  const total = Math.max(1, callNow + putNow);
  const callPct = Math.round((callNow / total) * 100);
  const putPct = 100 - callPct;

  // Call arc drawn over the full put ring; which hue each is comes from the
  // tokens, so the preference flips both together.
  const dash = `${(callPct / 100) * CIRC} ${CIRC}`;

  return (
    <div className={s.wrap}>
      <span className={cx(s.side, s.call)}>{callPct}% Call OI</span>
      <div className={s.donut}>
        <svg viewBox="0 0 140 140" width="140" height="140" className={s.ring} aria-hidden="true">
          <circle cx="70" cy="70" r={R} fill="none" className={s.arcPut} strokeWidth="14" />
          <circle
            cx="70"
            cy="70"
            r={R}
            fill="none"
            className={s.arcCall}
            strokeWidth="14"
            strokeDasharray={dash}
          />
        </svg>
        <div className={s.center}>
          <span className={s.k}>PCR</span>
          <span className={s.v}>{pcr.toFixed(2)}</span>
        </div>
      </div>
      <span className={cx(s.side, s.put)}>{putPct}% Put OI</span>
    </div>
  );
}
