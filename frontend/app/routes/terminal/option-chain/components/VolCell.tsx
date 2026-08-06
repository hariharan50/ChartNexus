import { cx } from '$shared/ui/cx';
import { compactIndian, ordinal, type Side } from '../chain-model';
import s from './VolCell.module.css';

interface Props {
  value?: number | undefined;
  /** 1-based volume rank on this side, or undefined when no volume. */
  rank?: number | undefined;
  /** The #1 volume on this side — denominator for "% of highest". */
  top: number;
  side: Side;
}

export default function VolCell({ value, rank, top, side }: Props) {
  const inTop3 = rank != null && rank <= 3;
  const pctOfTop = value != null && top > 0 ? Math.round((value / top) * 100) : undefined;

  return (
    <td className={cx(s.vol, s[side])}>
      <span className={s.wrap}>
        <span className={cx(s.chip, inTop3 && s.top3)}>{compactIndian(value)}</span>{' '}
        {rank != null && pctOfTop != null ? (
          <span className={s.tip} role="tooltip">
            <span className={s.tipLine}>Volume Rank: {ordinal(rank)}</span>{' '}
            <span className={s.tipSub}>
              {pctOfTop}% of {ordinal(1)} highest
            </span>
          </span>
        ) : null}
      </span>
    </td>
  );
}
