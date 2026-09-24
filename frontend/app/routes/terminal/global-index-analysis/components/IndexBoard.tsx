import type { MarketRow, RegionRow } from '$contexts/global-markets/types';
import { cx } from '$shared/ui/cx';
import { byRegion, fmtChange, fmtLevel, fmtPercent, sparkPath, tone } from '../gia-data';
import s from './IndexBoard.module.css';

interface Props {
  markets: MarketRow[];
  regions: RegionRow[];
  labels: Record<string, string>;
}

/**
 * The world board, grouped by region.
 *
 * The reference layout is a flat list of nine rows in no particular order.
 * Grouping by region with an aggregate per group is what turns it into a
 * reading: "Asia up, Europe flat, America down" is the handoff story in three
 * lines, and the individual rows are there to check it against.
 *
 * Each row also carries its IST session window, because "the Nikkei is up
 * 1.3%" means something different at 08:00 (still trading, could reverse) than
 * at 13:00 (settled, that is the number India inherits).
 */
export default function IndexBoard({ markets, regions, labels }: Props) {
  const groups = byRegion(markets.filter((row) => !row.macro));
  const aggregate = new Map(regions.map((row) => [row.region, row]));

  return (
    <section className={s.wrap} aria-label="World index board">
      <header className={s.head}>
        <h2 className={s.title}>Major Indexes</h2>
        <p className={s.sub}>Grouped in handoff order — Asia, Europe, then the Americas</p>
      </header>

      <div className={s.scroller}>
        <table className={s.table}>
          <thead>
            <tr>
              <th scope="col">Name</th>
              <th scope="col" className={s.num}>
                Last
              </th>
              <th scope="col" className={s.num}>
                Chg
              </th>
              <th scope="col" className={s.num}>
                % Chg
              </th>
              <th scope="col" className={s.trend}>
                5d
              </th>
              <th scope="col" className={s.hours}>
                IST session
              </th>
            </tr>
          </thead>

          {groups.map((group) => {
            const roll = aggregate.get(group.region);
            return (
              <tbody key={group.region}>
                <tr className={s.groupRow}>
                  <th scope="rowgroup" colSpan={3}>
                    {labels[group.region] ?? group.region}
                  </th>
                  <td
                    className={cx(
                      s.num,
                      'mc-numeric',
                      s[tone(roll?.change_percent ?? null) ?? 'none']
                    )}
                  >
                    {fmtPercent(roll?.change_percent ?? null)}
                  </td>
                  <td colSpan={2} className={s.groupNote}>
                    {roll ? `mean of ${roll.members}` : ''}
                  </td>
                </tr>

                {group.rows.map((row) => {
                  const t = tone(row.change_percent);
                  const path = sparkPath(row.spark);
                  return (
                    <tr key={row.key}>
                      <th scope="row" className={s.name}>
                        {row.label}
                      </th>
                      <td className={cx(s.num, 'mc-numeric')}>{fmtLevel(row.price)}</td>
                      <td className={cx(s.num, 'mc-numeric', s[t ?? 'none'])}>
                        {fmtChange(row.change)}
                      </td>
                      <td className={cx(s.num, 'mc-numeric', s[t ?? 'none'])}>
                        {fmtPercent(row.change_percent)}
                      </td>
                      <td className={s.trend}>
                        {path ? (
                          <svg
                            className={cx(s.spark, s[t ?? 'none'])}
                            viewBox="0 0 100 100"
                            preserveAspectRatio="none"
                            aria-hidden="true"
                          >
                            <path d={path} fill="none" stroke="currentColor" strokeWidth="6" />
                          </svg>
                        ) : (
                          <span className={s.noSpark}>—</span>
                        )}
                      </td>
                      <td className={cx(s.hours, 'mc-numeric')}>
                        {row.opens_ist === '24h' ? '24h' : `${row.opens_ist}–${row.closes_ist}`}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            );
          })}
        </table>
      </div>
    </section>
  );
}
