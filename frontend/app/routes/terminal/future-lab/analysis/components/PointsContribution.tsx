import { useMemo } from 'react';
import type { Contribution } from '$contexts/market-breadth/types';
import { cx } from '$shared/ui/cx';
import { fmtPercent, fmtPoints, fmtShare, toNumber } from '../analysis-data';
import DivergingBoard, { type BoardRow } from './DivergingBoard';
import s from './PointsContribution.module.css';

interface Props {
  /** The index as the picker names it — "NIFTY 50", "BANK NIFTY". */
  label: string;
  /** Every member with a positive contribution, biggest first. */
  gainers: Contribution[];
  /** Every member with a negative contribution, most negative first. */
  losers: Contribution[];
}

/**
 * What is holding the index up, what is dragging it down, and which side wins.
 *
 * The measure is **index points** — `weight/100 × change%/100 × previous
 * level` — so a heavyweight moving a little outranks a minnow moving a lot.
 * That is the whole reason this is not the change-% board of the same shape on
 * Advance/Decline: same picture, different question.
 *
 * The geometry lives in `DivergingBoard`. This supplies the rows and the two
 * totals, which are the comparison the card exists to make.
 */
export default function PointsContribution({ label, gainers, losers }: Props) {
  const up = useMemo(() => gainers.map(toRow), [gainers]);
  const down = useMemo(() => losers.map(toRow), [losers]);
  const pushed = useMemo(() => total(gainers), [gainers]);
  const dragged = useMemo(() => total(losers), [losers]);

  return (
    <DivergingBoard
      title={`${label} Points Contribution`}
      totals={
        <>
          <span className={s.totalLabel}>Pushed</span>
          <span className={cx(s.total, s.up)}>{fmtPoints(pushed)}</span>
          <span className={s.totalLabel}>Dragged</span>
          <span className={cx(s.total, s.down)}>{fmtPoints(dragged)}</span>
        </>
      }
      note={`Net ${fmtPoints(pushed + dragged)} pts`}
      hint="Every member, with its price and its own move, is in the two lists either side."
      up={up}
      down={down}
      format={(value) => fmtPoints(value)}
    />
  );
}

function toRow(row: Contribution): BoardRow {
  const points = toNumber(row.points) ?? 0;
  return {
    symbol: row.symbol,
    value: points,
    hover: [
      row.name ?? row.symbol,
      `${fmtPoints(points)} pts`,
      fmtPercent(row.change_percent),
      `${fmtShare(row.weight_percent)} weight`
    ].join(' · ')
  };
}

function total(rows: Contribution[]): number {
  return rows.reduce((sum, row) => sum + (toNumber(row.points) ?? 0), 0);
}
