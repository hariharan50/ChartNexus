import s from './SentimentDonut.module.css';

interface Props {
  label: string;
  percent: number;
}

const R = 58;
const CIRC = 2 * Math.PI * R;

export default function SentimentDonut({ label, percent }: Props) {
  const color = label === 'Bullish' ? '#16a34a' : label === 'Bearish' ? '#ef4444' : '#f59e0b';
  const dash = `${(Math.min(100, Math.max(0, percent)) / 100) * CIRC} ${CIRC}`;

  return (
    <div className={s.donut}>
      <svg viewBox="0 0 140 140" width="140" height="140" className={s.ring} aria-hidden="true">
        <circle cx="70" cy="70" r={R} fill="none" stroke="var(--mc-border)" strokeWidth="14" />
        <circle
          cx="70"
          cy="70"
          r={R}
          fill="none"
          stroke={color}
          strokeWidth="14"
          strokeLinecap="round"
          strokeDasharray={dash}
        />
      </svg>
      <div className={s.center}>
        <span className={s.label} style={{ color }}>
          {label}
        </span>
        <span className={s.sub}>{label} market conditions</span>
        <span className={s.pct}>{percent}%</span>
      </div>
    </div>
  );
}
