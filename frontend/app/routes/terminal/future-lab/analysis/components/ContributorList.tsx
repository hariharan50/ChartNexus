import type { Contribution } from '$contexts/market-breadth/types';
import SymbolCell from '$shared/ui/SymbolCell';
import { cx } from '$shared/ui/cx';
import { fmtPercent, fmtPrice, toNumber } from '../analysis-data';
import s from './ContributorList.module.css';

interface Props {
  title: string;
  rows: Contribution[];
  /** Which way this list moved the index — it colours the heading and count. */
  side: 'up' | 'down';
}

/**
 * One side of the index, as a list you can scan for a name.
 *
 * The flanking panels either side of the contribution board. They answer a
 * different question from it: the board ranks *how much* each member moved the
 * index, this says *where the member itself is* — its price and its own move —
 * which is what you want the moment a ticker on the board surprises you.
 *
 * Three columns, not five. The index points are the board's whole subject and
 * repeating them here would be noise; weight is left to the reader who needs
 * it, because a five-column table in a column this narrow is unreadable and an
 * unreadable table is worse than a missing one.
 */
export default function ContributorList({ title, rows, side }: Props) {
  return (
    <section className={s.card}>
      <div className={s.head}>
        <h2 className={cx(s.title, s[side])}>{title}</h2>
        <span className={cx(s.count, s[side])}>{rows.length}</span>
      </div>

      <div className={s.scroller}>
        <table className={s.table}>
          <thead>
            <tr>
              <th scope="col">Symbol</th>
              <th scope="col" className={s.numeric}>
                Price
              </th>
              <th scope="col" className={s.numeric}>
                Chg%
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.symbol}>
                <td>
                  <SymbolCell symbol={row.symbol} />
                </td>
                <td className={s.numeric}>{fmtPrice(row.last)}</td>
                <td className={cx(s.numeric, tone(toNumber(row.change_percent)))}>
                  {fmtPercent(row.change_percent)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        {rows.length === 0 ? (
          <p className={s.empty}>
            No member moved the index {side === 'up' ? 'up' : 'down'} today.
          </p>
        ) : null}
      </div>
    </section>
  );
}

function tone(value: number | null): string | undefined {
  if (value === null || value === 0) return undefined;
  return value > 0 ? s.up : s.down;
}
