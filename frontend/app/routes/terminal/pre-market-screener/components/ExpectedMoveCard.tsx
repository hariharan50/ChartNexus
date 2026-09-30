import type { ExpectedMove, MoveEstimate } from '$contexts/pre-market/types';
import { cx } from '$shared/ui/cx';
import { MOVE_LABELS, fmtLevel, fmtPercent } from '../pms-data';
import s from './ExpectedMoveCard.module.css';

interface Props {
  move: ExpectedMove;
}

const ORDER: Array<keyof Pick<ExpectedMove, 'straddle' | 'vix' | 'atr'>> = [
  'straddle',
  'vix',
  'atr'
];

/**
 * How far the index can plausibly travel, by three measures, never blended.
 *
 * They are not three estimates of one quantity. The straddle is what the
 * option market is *charging* between now and expiry; India VIX is an
 * annualised thirty-day implied volatility scaled to a session; ATR is what
 * the index has *actually* been travelling. Averaging them yields a number
 * with no definition — neither what the market charges nor what the index
 * does.
 *
 * And the disagreement is the useful part: a straddle well above ATR means
 * options are pricing an event, well below means complacency. A blend destroys
 * exactly the signal a pre-market reader wants, which is why `note` is
 * rendered rather than resolved.
 */
export default function ExpectedMoveCard({ move }: Props) {
  const rows = ORDER.map((key) => [key, move[key]] as const).filter(
    (entry): entry is readonly [(typeof entry)[0], MoveEstimate] => entry[1] !== null
  );

  if (!rows.length) {
    return <p className={s.empty}>No measure of the expected move could be computed.</p>;
  }

  return (
    <div className={s.wrap}>
      <ul className={s.rows}>
        {rows.map(([key, estimate]) => (
          <li key={key} className={s.row}>
            <span className={s.label}>{MOVE_LABELS[key]}</span>
            <span className={cx(s.band, 'mc-numeric')}>
              {fmtLevel(estimate.lower)} — {fmtLevel(estimate.upper)}
            </span>
            <span className={cx(s.size, 'mc-numeric')}>
              ±{fmtLevel(estimate.points)} ({fmtPercent(estimate.percent)})
            </span>
          </li>
        ))}
      </ul>

      {move.days_to_expiry !== null ? (
        <p className={s.horizon}>
          The straddle covers {move.days_to_expiry}{' '}
          {move.days_to_expiry === 1 ? 'session' : 'sessions'} to expiry, not today alone.
        </p>
      ) : null}

      {move.note ? <p className={s.note}>{move.note}</p> : null}

      <p className={s.caveat}>
        Three different measures over three different horizons. They are shown side by side
        deliberately — an average of them would have no meaning.
      </p>
    </div>
  );
}
