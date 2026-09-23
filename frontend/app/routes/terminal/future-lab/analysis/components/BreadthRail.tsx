import { INDICES, type IndexId } from '$contexts/market-breadth/api';
import type { IndexHeader, SectorRow } from '$contexts/market-breadth/types';
import { cx } from '$shared/ui/cx';
import { fmtPercent, fmtPrice, toNumber } from '../analysis-data';
import s from './BreadthRail.module.css';

/** What the page is currently scoped to. */
export interface Scope {
  index: IndexId;
  /** `null` means the index itself. */
  sector: string | null;
}

interface Props {
  scope: Scope;
  onScope: (scope: Scope) => void;
  sectors: SectorRow[];
  /** The selected index's own header, for the level beside its row. */
  header: IndexHeader | undefined;
  loading: boolean;
}

/**
 * What you can point this page at.
 *
 * Two groups, and they are two different universes — which the headings say,
 * because the numbers are not comparable. An **index** row counts the fifty
 * names of a published index against their weights. A **sector** row counts
 * every F&O name the catalog classifies there, most of which sit in no index
 * at all.
 *
 * **A sector has no price, and none is invented.** There is no NIFTY IT in
 * this application — no membership, no level, no weights — so where an index
 * shows its level a sector shows the one thing it genuinely has: how many of
 * its names are up against how many are down.
 */
export default function BreadthRail({ scope, onScope, sectors, header, loading }: Props) {
  return (
    <section className={s.card}>
      <div className={s.scroller}>
        <table className={s.table}>
          <thead>
            <tr>
              <th scope="col">Index</th>
              <th scope="col" className={s.numeric}>
                Level
              </th>
              <th scope="col" className={s.numeric}>
                Chg%
              </th>
            </tr>
          </thead>
          <tbody>
            {INDICES.map((entry) => {
              const selected = scope.index === entry.id && scope.sector === null;
              const own = selected || scope.index === entry.id ? header : undefined;
              return (
                <tr key={entry.id} className={cx(selected && s.selected)}>
                  <td>
                    <button
                      type="button"
                      className={s.pick}
                      aria-pressed={selected}
                      onClick={() => onScope({ index: entry.id, sector: null })}
                    >
                      {entry.label}
                    </button>
                  </td>
                  <td className={s.numeric}>{own ? fmtPrice(own.level) : '—'}</td>
                  <td className={cx(s.numeric, own && tone(toNumber(own.change_percent)))}>
                    {own ? fmtPercent(own.change_percent) : '—'}
                  </td>
                </tr>
              );
            })}
          </tbody>

          <thead>
            <tr>
              <th scope="col">
                Sector
                <span className={s.universe}>F&amp;O</span>
              </th>
              <th scope="col" className={s.numeric}>
                Breadth
              </th>
              <th scope="col" className={s.numeric}>
                Chg%
              </th>
            </tr>
          </thead>
          <tbody>
            {sectors.map((row) => {
              const selected = scope.sector === row.sector;
              return (
                <tr key={row.sector} className={cx(selected && s.selected)}>
                  <td>
                    <button
                      type="button"
                      className={s.pick}
                      aria-pressed={selected}
                      onClick={() => onScope({ index: scope.index, sector: row.sector })}
                    >
                      {row.sector}
                    </button>
                  </td>
                  {/* Where an index shows a level. A sector has no index and
                      no level, so this is its advance/decline split instead —
                      the column earns its place on every row. */}
                  <td className={cx(s.numeric, s.breadth)}>
                    <span className={s.up}>{row.count.advancing}</span>
                    <span className={s.slash}>/</span>
                    <span className={s.down}>{row.count.declining}</span>
                  </td>
                  <td className={cx(s.numeric, tone(toNumber(row.mean_change_percent)))}>
                    {fmtPercent(row.mean_change_percent)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>

        {sectors.length === 0 ? (
          <p className={s.empty}>{loading ? 'Loading the board…' : 'No sector could be priced.'}</p>
        ) : null}
      </div>

      <p className={s.footnote}>
        Sector moves are an unweighted mean — these names carry no index weight.
      </p>
    </section>
  );
}

function tone(value: number | null): string | undefined {
  if (value === null || value === 0) return undefined;
  return value > 0 ? s.up : s.down;
}
